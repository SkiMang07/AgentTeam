from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.state import (
    ChiefWorkOrder,
    SharedState,
    get_canonical_jt_requested,
    get_memory_lookup_fields,
    normalize_project_memory,
)
from tools.obsidian_context import ObsidianContextTool
from tools.openai_client import ResponsesClient

if TYPE_CHECKING:
    pass

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "chief_of_staff.md"


class ChiefOfStaffAgent:
    def __init__(
        self,
        client: ResponsesClient,
        obsidian_tool: ObsidianContextTool | None = None,
    ) -> None:
        self._client = client
        self._obsidian_tool = obsidian_tool
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        user_task = state["user_task"]
        inferred_jt_requested = state.get("jt_requested", False)
        inferred_dev_pod_requested = state.get("dev_pod_requested", False)
        project_memory = normalize_project_memory(state.get("project_memory"))
        memory_open_questions = project_memory.get("open_questions", [])
        memory_lookup_requested = self._is_memory_lookup_request(user_task)
        memory_turn_type = self._get_memory_turn_type(user_task)

        # Load Obsidian vault context for this task
        obsidian_block = self._load_obsidian_context(user_task)

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Create and route the Chief of Staff work order. Return strict JSON with keys: "
                "work_order, route, rationale. "
                "work_order must include: objective (string), deliverable_type (string), "
                "success_criteria (array of strings), research_needed (boolean), "
                "open_questions (array of strings), jt_requested (boolean), dev_pod_requested (boolean). "
                "When dev_pod_requested is true, also include pod_task_brief as a top-level key (not inside work_order). "
                "route must be 'research', 'write_direct', or 'memory_lookup'. "
                "Use route='memory_lookup' only when the task explicitly asks to inspect stored session/project memory "
                "(for example asking for latest approved output currently stored). "
                "Set work_order.jt_requested from explicit task text only; do not infer hidden intent. "
                "Set work_order.dev_pod_requested=true only when the task is explicitly about writing or implementing code artifacts. "
                "If project memory is provided, use it only as continuity context for planning; "
                "do not treat memory as evidence or claimed facts unless they are present in current task inputs. "
                "Use vault context to extract specific facts, tool descriptions, and current state into success_criteria — "
                "do not treat vault context as approved facts for the Researcher, but do use it to write concrete, falsifiable success_criteria items. "
                "Do not include extra keys.\n\n"
                f"CLI JT requested flag: {inferred_jt_requested}\n"
                f"CLI dev pod requested flag: {inferred_dev_pod_requested}\n\n"
                "Current task:\n"
                f"{user_task}\n\n"
                "Obsidian vault context (use to ground the work order — pull specific facts, tool descriptions, and current state into success_criteria):\n"
                f"{obsidian_block}\n\n"
                "Session project memory (continuity only):\n"
                f"- current_objective: {project_memory.get('current_objective', '')}\n"
                f"- active_deliverable_type: {project_memory.get('active_deliverable_type', '')}\n"
                f"- open_questions: {memory_open_questions}\n"
                f"- latest_draft: {project_memory.get('latest_draft', '')}\n"
                f"- latest_approved_output: {project_memory.get('latest_approved_output', '')}\n\n"
                "Current evidence:\n"
                f"- files_read: {state.get('files_read', [])}\n"
                f"- approved_facts_count: {len(state.get('approved_facts', [])) if isinstance(state.get('approved_facts'), list) else 0}\n"
                f"- explicit memory lookup requested: {memory_lookup_requested}"
            ),
        )
        data = self._normalize_output(
            self._safe_parse(raw),
            inferred_jt_requested=inferred_jt_requested,
            inferred_dev_pod_requested=inferred_dev_pod_requested,
            prior_memory=project_memory,
            user_task=user_task,
        )
        # Override: web_search requires the Researcher to run regardless of CoS routing decision.
        # Also sync research_needed=True so route_after_chief (which checks work_order first) routes
        # correctly — without this sync the route field is silently ignored by the graph.
        if state.get("web_search_enabled") and data["route"] not in {"memory_lookup"}:
            synced_work_order = {**data["work_order"], "research_needed": True}
            data = {**data, "route": "research", "work_order": synced_work_order}

        # Safeguard: if vault context was loaded, research_needed must be True so the Researcher
        # can convert vault content into approved_facts. Vault context in the CoS prompt is a
        # planning aid — it does NOT auto-populate approved_facts for the Writer.
        vault_context_available = bool(
            obsidian_block
            and "(Obsidian vault not configured)" not in obsidian_block
            and "(Obsidian context unavailable" not in obsidian_block
            and len(obsidian_block.strip()) > 50
        )
        if vault_context_available and data["route"] not in {"memory_lookup"}:
            synced_work_order = {**data["work_order"], "research_needed": True}
            data = {**data, "route": "research", "work_order": synced_work_order}
        work_order = data["work_order"]
        updated_project_memory = (
            project_memory
            if memory_turn_type == "memory_inspection"
            else {
                **project_memory,
                "current_objective": work_order["objective"],
                "active_deliverable_type": work_order["deliverable_type"],
                "open_questions": work_order["open_questions"],
            }
        )

        pod_task_brief = data.get("pod_task_brief") or ""
        return {
            **state,
            "work_order": work_order,
            "route": data["route"],
            "jt_requested": work_order["jt_requested"],
            "jt_mode": state.get("jt_mode"),
            "dev_pod_requested": work_order["dev_pod_requested"],
            "pod_task_brief": pod_task_brief,
            "memory_turn_type": memory_turn_type,
            "memory_lookup_requested": memory_lookup_requested,
            "current_run": {
                "objective": work_order["objective"],
                "deliverable_type": work_order["deliverable_type"],
                "open_questions": work_order["open_questions"],
                "latest_draft": state.get("draft", ""),
                "latest_approved_output": state.get("final_output", ""),
            },
            "project_memory": updated_project_memory,
            "status": "routed",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "chief_of_staff_raw": raw,
            },
        }

    def final_pass(self, state: SharedState) -> SharedState:
        work_order = self._get_work_order(state)
        reviewer_findings = state.get("reviewer_findings")
        review_block = self._format_reviewer_findings_block(reviewer_findings, state)
        jt_block = self._format_jt_block(state)

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Run final Chief of Staff pass before human review. "
                "Use the work order as the source-of-truth contract for completeness checks. "
                "This is an alignment/completeness validation, not a rewrite task. "
                "Return strict JSON with keys: next_step, rationale, instructions, "
                "answers_request, matches_deliverable_type, reviewer_findings_addressed, "
                "jt_findings_addressed, obvious_missing_items. "
                "next_step must be 'human_review' or 'redraft'. "
                "Use 'redraft' only when the draft should be revised before human review. "
                "If you request a redraft, instructions must preserve factual scope and forbid adding new specifics not in the draft/review inputs.\n\n"
                f"Work order:\n{self._format_work_order(work_order)}\n\n"
                f"Draft:\n{state.get('draft', '')}\n\n"
                f"Reviewer findings (structured):\n{review_block}\n\n"
                f"JT findings:\n{jt_block}"
            ),
        )
        data = self._normalize_final_output(self._safe_parse(raw))
        current_guidance_notes = state.get("writer_guidance_notes", [])
        current_chief_notes = state.get("chief_notes", [])
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
        auto_redraft_count = state.get("auto_redraft_count", 0)
        if has_critical_reviewer_findings and auto_redraft_count > 0:
            should_redraft = False
        elif has_critical_reviewer_findings and state.get("chief_redraft_count", 0) < 1:
            should_redraft = True

        critical_reviewer_blocking = has_critical_reviewer_findings and not should_redraft

        if should_redraft and chief_notes:
            guidance_note = f"Chief final pass note: {chief_notes}"
            current_guidance_notes = [*current_guidance_notes, guidance_note]
            current_chief_notes = [*current_chief_notes, guidance_note]

        return {
            **state,
            "writer_guidance_notes": current_guidance_notes,
            "chief_notes": current_chief_notes,
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

    def _load_obsidian_context(self, task: str) -> str:
        """Load vault context for the given task; return a prompt-ready block."""
        if self._obsidian_tool is None or not self._obsidian_tool.available:
            return "(Obsidian vault not configured)"
        try:
            context = self._obsidian_tool.load(task)
            from tools.obsidian_context import ObsidianContextTool as _OCT
            return _OCT.render_for_prompt(context)
        except Exception as exc:  # noqa: BLE001
            return f"(Obsidian context unavailable: {exc})"

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
    def _normalize_output(
        data: dict,
        inferred_jt_requested: bool,
        inferred_dev_pod_requested: bool,
        prior_memory: dict,
        user_task: str,
    ) -> dict:
        work_order = ChiefOfStaffAgent._normalize_work_order(
            data.get("work_order"),
            inferred_jt_requested,
            inferred_dev_pod_requested=inferred_dev_pod_requested,
            prior_memory=prior_memory,
        )

        route = data.get("route")
        if route not in {"research", "write_direct", "memory_lookup"}:
            route = "research" if work_order["research_needed"] else "write_direct"
        # If CoS said write_direct but research is needed, honour research_needed
        if route == "write_direct" and work_order["research_needed"]:
            route = "research"
        if ChiefOfStaffAgent._is_memory_lookup_request(user_task):
            route = "memory_lookup"

        pod_task_brief = data.get("pod_task_brief")
        if not isinstance(pod_task_brief, str):
            pod_task_brief = ""

        return {
            **data,
            "route": route,
            "work_order": work_order,
            "pod_task_brief": pod_task_brief,
        }

    @staticmethod
    def _normalize_work_order(
        raw_work_order: Any,
        inferred_jt_requested: bool,
        inferred_dev_pod_requested: bool = False,
        prior_memory: dict | None = None,
    ) -> ChiefWorkOrder:
        if not isinstance(raw_work_order, dict):
            raw_work_order = {}
        memory = normalize_project_memory(prior_memory or {})

        objective = raw_work_order.get("objective")
        if not isinstance(objective, str) or not objective.strip():
            objective = memory.get("current_objective", "") or "Clarify and complete the user request."

        deliverable_type = raw_work_order.get("deliverable_type")
        if not isinstance(deliverable_type, str) or not deliverable_type.strip():
            deliverable_type = memory.get("active_deliverable_type", "") or "general_response"

        success_criteria = raw_work_order.get("success_criteria")
        if not isinstance(success_criteria, list) or not all(isinstance(item, str) for item in success_criteria):
            success_criteria = ["Answer the user task directly and clearly."]

        open_questions = raw_work_order.get("open_questions")
        if not isinstance(open_questions, list) or not all(isinstance(item, str) for item in open_questions):
            open_questions = memory.get("open_questions", [])

        research_needed = raw_work_order.get("research_needed")
        if not isinstance(research_needed, bool):
            research_needed = True

        jt_requested = raw_work_order.get("jt_requested")
        model_jt_requested = jt_requested if isinstance(jt_requested, bool) else False
        jt_requested = bool(inferred_jt_requested) or model_jt_requested

        dev_pod_requested = raw_work_order.get("dev_pod_requested")
        model_dev_pod_requested = dev_pod_requested if isinstance(dev_pod_requested, bool) else False
        dev_pod_requested = bool(inferred_dev_pod_requested) or model_dev_pod_requested

        return {
            "objective": objective.strip(),
            "deliverable_type": deliverable_type.strip(),
            "success_criteria": [item.strip() for item in success_criteria if item.strip()],
            "research_needed": research_needed,
            "open_questions": [item.strip() for item in open_questions if item.strip()],
            "jt_requested": jt_requested,
            "dev_pod_requested": dev_pod_requested,
        }

    @staticmethod
    def _get_work_order(state: SharedState) -> ChiefWorkOrder:
        from app.state import get_canonical_dev_pod_requested
        existing = state.get("work_order")
        if isinstance(existing, dict):
            return ChiefOfStaffAgent._normalize_work_order(
                existing,
                get_canonical_jt_requested(state),
                inferred_dev_pod_requested=get_canonical_dev_pod_requested(state),
                prior_memory=normalize_project_memory(state.get("project_memory")),
            )
        user_task = state.get("user_task", "")
        project_memory = normalize_project_memory(state.get("project_memory"))
        return {
            "objective": user_task.strip()
            or project_memory.get("current_objective", "")
            or "Clarify and complete the user request.",
            "deliverable_type": project_memory.get("active_deliverable_type", "") or "general_response",
            "success_criteria": ["Answer the user task directly and clearly."],
            "research_needed": True,
            "open_questions": project_memory.get("open_questions", []),
            "jt_requested": get_canonical_jt_requested(state),
            "dev_pod_requested": get_canonical_dev_pod_requested(state),
        }

    @staticmethod
    def _format_work_order(work_order: ChiefWorkOrder) -> str:
        success_criteria = "\n".join(f"- {item}" for item in work_order["success_criteria"]) or "- (none)"
        open_questions = "\n".join(f"- {item}" for item in work_order["open_questions"]) or "- (none)"
        return (
            f"objective: {work_order['objective']}\n"
            f"deliverable_type: {work_order['deliverable_type']}\n"
            f"research_needed: {work_order['research_needed']}\n"
            f"jt_requested: {work_order['jt_requested']}\n"
            f"success_criteria:\n{success_criteria}\n"
            f"open_questions:\n{open_questions}"
        )

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
    def _is_memory_lookup_request(task: str) -> bool:
        if not isinstance(task, str):
            return False
        normalized = " ".join(task.lower().split())
        mentions_memory = any(
            phrase in normalized
            for phrase in (
                "session memory",
                "project memory",
                "stored memory",
                "memory currently stored",
                "memory from this session",
                "from session memory",
            )
        )
        mentions_stored_session_context = any(
            phrase in normalized
            for phrase in (
                "from this session",
                "in this session",
                "currently stored",
                "stored output",
                "stored objective",
                "stored deliverable",
            )
        )
        asks_transformational_rewrite = any(
            phrase in normalized
            for phrase in (
                "rewrite",
                "revise",
                "transform",
                "reformat",
                "turn it into",
                "convert",
                "improve",
            )
        )
        requested_fields = get_memory_lookup_fields(task)
        return (mentions_memory or mentions_stored_session_context) and bool(requested_fields) and not asks_transformational_rewrite

    @staticmethod
    def _get_memory_turn_type(task: str) -> str:
        if ChiefOfStaffAgent._is_memory_lookup_request(task):
            return "memory_inspection"
        if not isinstance(task, str):
            return "project_work"
        normalized = " ".join(task.lower().split())
        mentions_memory = any(
            phrase in normalized
            for phrase in (
                "session memory",
                "project memory",
                "stored memory",
                "latest approved output",
                "latest_approved_output",
                "stored output",
                "from this session",
                "in this session",
            )
        )
        asks_transformational_rewrite = any(
            phrase in normalized
            for phrase in (
                "rewrite",
                "revise",
                "transform",
                "reformat",
                "turn it into",
                "convert",
                "improve",
            )
        )
        if mentions_memory and asks_transformational_rewrite:
            return "memory_transform"
        return "project_work"

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
        jt_requested = get_canonical_jt_requested(state)
        if not jt_requested:
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
