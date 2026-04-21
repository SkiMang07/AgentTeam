from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "chief_of_staff.md"


class ChiefOfStaffAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        user_task = state["user_task"]
        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Classify and route this task. Return strict JSON with keys: "
                "route, rationale. "
                "route must be 'research' or 'write_direct'. "
                "Do not include extra keys.\n\n"
                f"Task:\n{user_task}"
            ),
        )
        data = self._normalize_output(self._safe_parse(raw))

        return {
            **state,
            "route": data["route"],
            "jt_requested": state.get("jt_requested", False),
            "jt_mode": state.get("jt_mode"),
            "status": "routed",
            "model_metadata": {"chief_of_staff_raw": raw},
        }

    def final_pass(self, state: SharedState) -> SharedState:
        reviewer_findings = state.get("reviewer_findings")
        review_block = self._format_reviewer_findings_block(reviewer_findings, state)
        jt_block = self._format_jt_block(state)

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Run final Chief of Staff pass before human review. "
                "This is an alignment/completeness validation, not a rewrite task. "
                "Return strict JSON with keys: next_step, rationale, instructions, "
                "answers_request, matches_deliverable_type, reviewer_findings_addressed, "
                "jt_findings_addressed, obvious_missing_items. "
                "next_step must be 'human_review' or 'redraft'. "
                "Use 'redraft' only when the draft should be revised before human review. "
                "If you request a redraft, instructions must preserve factual scope and forbid adding new specifics not in the draft/review inputs.\n\n"
                f"Draft:\n{state.get('draft', '')}\n\n"
                f"Reviewer findings (structured):\n{review_block}\n\n"
                f"JT findings:\n{jt_block}"
            ),
        )
        data = self._normalize_final_output(self._safe_parse(raw))
        current_notes = state.get("approved_facts", [])
        chief_notes = data.get("instructions", "")
        has_critical_reviewer_findings = self._has_critical_reviewer_findings(reviewer_findings)

        chief_validation = {
            "answers_request": data["answers_request"],
            "matches_deliverable_type": data["matches_deliverable_type"],
            "reviewer_findings_addressed": (
                data["reviewer_findings_addressed"] and not has_critical_reviewer_findings
            ),
            "jt_findings_addressed": data["jt_findings_addressed"],
            "obvious_missing_items": data["obvious_missing_items"],
            "rationale": data["rationale"],
            "recommended_action": "redraft" if data["next_step"] == "redraft" else "human_review",
        }
        should_redraft = data["next_step"] == "redraft" and state.get("chief_redraft_count", 0) < 1
        if has_critical_reviewer_findings and state.get("chief_redraft_count", 0) < 1:
            should_redraft = True

        critical_reviewer_blocking = has_critical_reviewer_findings and not should_redraft

        if should_redraft and chief_notes:
            current_notes = [*current_notes, f"Chief final pass note: {chief_notes}"]

        return {
            **state,
            "approved_facts": current_notes,
            "chief_final_next_step": "writer" if should_redraft else "human_review",
            "critical_reviewer_blocking": critical_reviewer_blocking,
            "chief_final_validation": chief_validation,
            "chief_redraft_count": state.get("chief_redraft_count", 0) + (1 if should_redraft else 0),
            "status": "chief_finalized",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "chief_of_staff_final_raw": raw,
                "chief_final_critical_reviewer_findings": has_critical_reviewer_findings,
            },
        }

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            candidate = ChiefOfStaffAgent._extract_json_object(raw)
            if candidate is not None:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
            return {"route": "research", "rationale": "fallback due to parse error"}

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        route = data.get("route")
        if route not in {"research", "write_direct"}:
            route = "research"
        return {
            **data,
            "route": route,
        }

    @staticmethod
    def _normalize_final_output(data: dict) -> dict:
        next_step = data.get("next_step")
        if next_step not in {"human_review", "redraft"}:
            next_step = "human_review"

        rationale = data.get("rationale")
        if not isinstance(rationale, str):
            rationale = ""

        instructions = data.get("instructions")
        if not isinstance(instructions, str):
            instructions = ""

        obvious_missing_items = data.get("obvious_missing_items")
        if (
            not isinstance(obvious_missing_items, list)
            or not all(isinstance(item, str) for item in obvious_missing_items)
        ):
            obvious_missing_items = []

        def _as_bool(key: str, fallback: bool) -> bool:
            value = data.get(key)
            return value if isinstance(value, bool) else fallback

        return {
            **data,
            "next_step": next_step,
            "rationale": rationale,
            "instructions": instructions,
            "answers_request": _as_bool("answers_request", True),
            "matches_deliverable_type": _as_bool("matches_deliverable_type", True),
            "reviewer_findings_addressed": _as_bool("reviewer_findings_addressed", True),
            "jt_findings_addressed": _as_bool("jt_findings_addressed", True),
            "obvious_missing_items": obvious_missing_items,
        }

    @staticmethod
    def _extract_json_object(raw: str) -> str | None:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return match.group(0)
        return None

    @staticmethod
    def _format_reviewer_findings_block(reviewer_findings: Any, state: SharedState) -> str:
        if not isinstance(reviewer_findings, dict):
            review_feedback = state.get("review_feedback", [])
            return "\n".join(f"- {item}" for item in review_feedback) or "- (none)"

        def _render_list(label: str, key: str) -> str:
            items = reviewer_findings.get(key, [])
            if isinstance(items, list) and items:
                joined = "\n".join(f"  - {item}" for item in items if isinstance(item, str))
                if joined:
                    return f"- {label}:\n{joined}"
            return f"- {label}: (none)"

        overall_assessment = reviewer_findings.get("overall_assessment", "")
        if not isinstance(overall_assessment, str):
            overall_assessment = ""
        recommended_next_action = reviewer_findings.get("recommended_next_action", "revise")
        if not isinstance(recommended_next_action, str):
            recommended_next_action = "revise"

        blocks = [
            f"- overall_assessment: {overall_assessment or '(none)'}",
            _render_list("missing_content", "missing_content"),
            _render_list("unsupported_claims", "unsupported_claims"),
            _render_list("contradictions_or_logic_problems", "contradictions_or_logic_problems"),
            _render_list("format_or_structure_issues", "format_or_structure_issues"),
            f"- recommended_next_action: {recommended_next_action}",
        ]
        return "\n".join(blocks)

    @staticmethod
    def _format_jt_block(state: SharedState) -> str:
        if not state.get("jt_requested"):
            return "(JT not requested)"

        feedback = state.get("jt_feedback") or []
        rewrite = state.get("jt_rewrite") or ""
        feedback_block = "\n".join(f"- {item}" for item in feedback) or "- (none)"
        return (
            f"mode: {state.get('jt_mode') or 'default'}\n"
            f"feedback:\n{feedback_block}\n"
            f"rewrite:\n{rewrite}"
        )

    @staticmethod
    def _has_critical_reviewer_findings(reviewer_findings: Any) -> bool:
        if not isinstance(reviewer_findings, dict):
            return False
        unsupported = reviewer_findings.get("unsupported_claims", [])
        contradictions = reviewer_findings.get("contradictions_or_logic_problems", [])
        return bool(unsupported) or bool(contradictions)
