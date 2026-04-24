from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Mapping, cast

from app.advisor_registry import ADVISOR_IDS, ADVISOR_ROSTER
from app.state import AdvisorRouteResult, SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "advisor_router.md"


class AdvisorRouterAgent:
    """Selects a minimal advisor subset for advisor-pod tasks."""

    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        task = state.get("user_task", "")
        work_order = state.get("work_order") or {}
        advisor_brief = state.get("advisor_brief", "")
        approved_facts = [fact for fact in state.get("approved_facts", []) if isinstance(fact, str)]
        files_read = state.get("files_read", [])
        deterministic = self._deterministic_selection(task, work_order)
        if deterministic is not None:
            route = deterministic
        else:
            route = self._model_selection(
                task,
                work_order,
                advisor_brief=advisor_brief if isinstance(advisor_brief, str) else "",
                approved_facts=approved_facts,
                files_read=files_read if isinstance(files_read, list) else [],
            )

        selected = route["selected_advisors"]
        if selected:
            print(f"[advisor_router] selected advisors: {', '.join(selected)}")
            for advisor_id in selected:
                print(f"[advisor_router] reason[{advisor_id}]: {route['selection_reason'].get(advisor_id, '(no reason provided)')}")
        else:
            print("[advisor_router] selected advisors: (none)")
        for advisor_id in ADVISOR_IDS:
            if advisor_id not in selected:
                print(
                    f"[advisor_router] skipped[{advisor_id}]: "
                    f"{route['skipped_advisors'].get(advisor_id, 'Not selected for this task.')}"
                )

        return {
            **state,
            "advisor_route": route,
            "advisor_selected_advisors": selected,
            "advisor_invoked_advisors": [],
            "status": "advisor_routed",
        }

    def _model_selection(
        self,
        task: str,
        work_order: Mapping[str, Any],
        *,
        advisor_brief: str,
        approved_facts: list[str],
        files_read: list[str],
    ) -> AdvisorRouteResult:
        roster_block = "\n".join(
            [
                (
                    f"- id: {advisor['id']}\n"
                    f"  name: {advisor['name']}\n"
                    f"  when_to_use: {advisor['when_to_use']}\n"
                    f"  when_not_to_use: {advisor['when_not_to_use']}\n"
                    f"  expected_input_needs: {advisor['expected_input_needs']}"
                )
                for advisor in ADVISOR_ROSTER
            ]
        )

        user_prompt = (
            "Task:\n"
            f"{task}\n\n"
            "Work order:\n"
            f"- objective: {work_order.get('objective', '')}\n"
            f"- deliverable_type: {work_order.get('deliverable_type', '')}\n"
            f"- success_criteria: {work_order.get('success_criteria', [])}\n"
            f"- open_questions: {work_order.get('open_questions', [])}\n\n"
            f"Advisor brief:\n{advisor_brief or '(none)'}\n\n"
            "Grounding signals:\n"
            f"- files_read: {files_read}\n"
            f"- approved_facts: {approved_facts}\n\n"
            "Advisor roster:\n"
            f"{roster_block}\n"
        )

        raw = self._client.ask(system_prompt=self._prompt, user_prompt=user_prompt)
        parsed = self._safe_parse(raw)
        return self._normalize_route(parsed, task=task, work_order=work_order)

    def _deterministic_selection(self, task: str, work_order: Mapping[str, Any]) -> AdvisorRouteResult | None:
        normalized_task = task.lower()
        deliverable_type = str(work_order.get("deliverable_type", "")).lower()

        if self._looks_like_simple_rewrite(normalized_task, deliverable_type):
            return self._build_route(
                selected=[],
                reason={},
                skipped_defaults={
                    advisor_id: "Simple rewrite/editing request; specialist advisor input is unnecessary."
                    for advisor_id in ADVISOR_IDS
                },
                confidence="high",
            )

        deterministic_hits: dict[str, str] = {}
        if "ui" in normalized_task or "ux" in normalized_task or "user flow" in normalized_task:
            deterministic_hits["communication_influence"] = "Task explicitly references UI/UX/user flow clarity and messaging."
        if any(token in normalized_task for token in ("implementation plan", "langgraph", "architecture", "technical")):
            deterministic_hits["entrepreneur_execution"] = "Task is implementation-focused and needs execution sequencing."
        if any(token in normalized_task for token in ("strategy", "portfolio", "tradeoff", "cross functional")):
            deterministic_hits["strategy_systems"] = "Task requires strategy/system tradeoff framing."

        if deterministic_hits:
            selected = list(deterministic_hits.keys())[:2]
            return self._build_route(
                selected=selected,
                reason={advisor_id: deterministic_hits[advisor_id] for advisor_id in selected},
                skipped_defaults={
                    advisor_id: "Not selected by deterministic routing signals for this task."
                    for advisor_id in ADVISOR_IDS
                },
                confidence="high" if len(selected) == 1 else "medium",
            )

        return None

    @staticmethod
    def _looks_like_simple_rewrite(task: str, deliverable_type: str) -> bool:
        rewrite_terms = ("rewrite", "rephrase", "clarer", "clearer", "grammar", "proofread", "edit")
        has_rewrite_term = any(term in task for term in rewrite_terms)
        non_strategy_terms = ("sentence", "paragraph", "wording")
        narrow_shape = any(term in task for term in non_strategy_terms)
        return has_rewrite_term and (narrow_shape or deliverable_type in {"draft_response", ""})

    def _normalize_route(
        self,
        payload: Mapping[str, Any],
        *,
        task: str,
        work_order: Mapping[str, Any],
    ) -> AdvisorRouteResult:
        selected_raw = payload.get("selected_advisors", [])
        selected = [item for item in selected_raw if isinstance(item, str) and item in ADVISOR_IDS] if isinstance(selected_raw, list) else []

        confidence_raw = payload.get("advisor_route_confidence", "low")
        confidence: Literal["low", "medium", "high"] = (
            cast(Literal["low", "medium", "high"], confidence_raw)
            if confidence_raw in {"low", "medium", "high"}
            else "low"
        )

        complexity = self._is_clearly_complex(task, work_order)
        max_allowed = 3 if complexity else 2
        selected = selected[:max_allowed]

        reason_raw = payload.get("selection_reason", {})
        selection_reason = {
            advisor_id: value.strip()
            for advisor_id, value in (reason_raw.items() if isinstance(reason_raw, dict) else [])
            if advisor_id in selected and isinstance(value, str) and value.strip()
        }

        skipped_raw = payload.get("skipped_advisors", {})
        skipped_advisors = {
            advisor_id: value.strip()
            for advisor_id, value in (skipped_raw.items() if isinstance(skipped_raw, dict) else [])
            if advisor_id in ADVISOR_IDS and isinstance(value, str) and value.strip()
        }

        return self._build_route(
            selected=selected,
            reason=selection_reason,
            skipped_defaults=skipped_advisors,
            confidence=confidence,
        )

    @staticmethod
    def _is_clearly_complex(task: str, work_order: Mapping[str, Any]) -> bool:
        normalized = task.lower()
        has_cross_functional_signal = any(
            phrase in normalized
            for phrase in (
                "cross functional",
                "cross-functional",
                "customer facing",
                "internal strategy",
                "technical implementation",
            )
        )
        open_questions = work_order.get("open_questions", [])
        return has_cross_functional_signal or (isinstance(open_questions, list) and len(open_questions) >= 3)

    @staticmethod
    def _build_route(
        *,
        selected: list[str],
        reason: Mapping[str, str],
        skipped_defaults: Mapping[str, str],
        confidence: Literal["low", "medium", "high"],
    ) -> AdvisorRouteResult:
        safe_selected = [advisor_id for advisor_id in selected if advisor_id in ADVISOR_IDS]
        selection_reason = {
            advisor_id: reason.get(advisor_id, "Selected for relevance to the task scope.")
            for advisor_id in safe_selected
        }
        skipped_advisors = {
            advisor_id: skipped_defaults.get(advisor_id, "Not selected for this task.")
            for advisor_id in ADVISOR_IDS
            if advisor_id not in safe_selected
        }
        return {
            "selected_advisors": safe_selected,
            "selection_reason": selection_reason,
            "skipped_advisors": skipped_advisors,
            "advisor_route_confidence": confidence,
        }

    @staticmethod
    def _safe_parse(raw: str) -> Mapping[str, Any]:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
