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
        route = data["route"]
        approved_facts = state.get("approved_facts", [])
        if self._is_jt_commenter_mode(state):
            approved_facts = [
                *approved_facts,
                (
                    "Chief JT commenter standard: keep rewrite materially faithful to source intent; "
                    "do not add urgency, ownership, commitments, priorities, or risk framing not present in source text."
                ),
            ]
        return {
            **state,
            "route": route,
            "approved_facts": approved_facts,
            "jt_requested": state.get("jt_requested", False),
            "jt_mode": state.get("jt_mode"),
            "status": "routed",
            "model_metadata": {"chief_of_staff_raw": raw},
        }

    def final_pass(self, state: SharedState) -> SharedState:
        normalized_draft = self._normalize_jt_commenter_draft(
            draft=state.get("draft", ""),
            jt_requested=state.get("jt_requested", False),
            jt_mode=state.get("jt_mode"),
        )
        reviewer_findings = state.get("reviewer_findings")
        review_block = self._format_reviewer_findings_block(reviewer_findings, state)
        jt_findings = state.get("jt_findings")
        jt_block = jt_findings if jt_findings else "(JT not requested or no findings)"
        mode_specific_bar = ""
        if self._is_jt_commenter_mode(state):
            mode_specific_bar = (
                "\n\nJT commenter editorial bar (Chief-owned):\n"
                "- Enforce strict meaning preservation from source text.\n"
                "- Reject added urgency, ownership, commitments, priorities, or risk framing.\n"
                "- Preserve helpful nuance (appreciation/support/caution) when present in source.\n"
                "- If Reviewer approved and two-line contract is intact, default to human_review."
            )

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
                f"Draft:\n{normalized_draft}\n\n"
                f"Reviewer findings (structured):\n{review_block}\n\n"
                f"JT findings:\n{jt_block}"
                f"{mode_specific_bar}"
            ),
        )
        data = self._normalize_final_output(self._safe_parse(raw))
        current_notes = state.get("approved_facts", [])
        chief_notes = data.get("instructions", "")
        chief_validation = {
            "answers_request": data["answers_request"],
            "matches_deliverable_type": data["matches_deliverable_type"],
            "reviewer_findings_addressed": data["reviewer_findings_addressed"],
            "jt_findings_addressed": data["jt_findings_addressed"],
            "obvious_missing_items": data["obvious_missing_items"],
            "rationale": data["rationale"],
            "recommended_action": "redraft" if data["next_step"] == "redraft" else "human_review",
        }
        should_redraft = (
            data["next_step"] == "redraft"
            and state.get("chief_redraft_count", 0) < 1
        )
        reviewer_rejection_blocking = (
            self._is_jt_commenter_mode(state)
            and not state.get("review_approved", False)
            and state.get("auto_redraft_count", 0) >= 1
        )
        # In JT commenter mode, once Reviewer has approved, avoid extra
        # style-only ping-pong from a discretionary Chief final redraft.
        # This preserves safety checks (reviewer gate already passed) while
        # reducing unnecessary loops on simple commenter rewrites.
        if should_redraft and self._is_jt_commenter_mode(state) and state.get("review_approved", False):
            should_redraft = False
        if should_redraft and reviewer_rejection_blocking:
            should_redraft = False

        if should_redraft and chief_notes:
            contract_note = ""
            if self._is_jt_commenter_mode(state):
                contract_note = (
                    " Return exactly two lines in this exact structure: "
                    "'JT Feedback: ...' and 'JT Rewrite: ...'. "
                    "Do not add any other labels, commentary, wrappers, or notes."
                )
            current_notes = [*current_notes, f"Chief final pass note: {chief_notes}{contract_note}"]

        return {
            **state,
            "draft": normalized_draft,
            "approved_facts": current_notes,
            "chief_final_next_step": "writer" if should_redraft else "human_review",
            "chief_final_validation": chief_validation,
            "chief_redraft_count": state.get("chief_redraft_count", 0) + (1 if should_redraft else 0),
            "status": "chief_finalized",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "chief_of_staff_final_raw": raw,
                "chief_final_reviewer_rejection_blocking": reviewer_rejection_blocking,
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
    def _is_jt_commenter_mode(state: SharedState) -> bool:
        return bool(state.get("jt_requested")) and state.get("jt_mode") == "commenter"

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
    def _normalize_jt_commenter_draft(draft: str, jt_requested: bool, jt_mode: str | None) -> str:
        if not jt_requested or jt_mode != "commenter":
            return draft
        return ChiefOfStaffAgent._enforce_jt_commenter_contract(draft)

    @staticmethod
    def _enforce_jt_commenter_contract(text: str) -> str:
        feedback = ""
        rewrite = ""

        feedback_match = re.search(
            r"JT Feedback:\s*(.*?)(?=\n\s*JT Rewrite:|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        rewrite_match = re.search(
            r"JT Rewrite:\s*(.*?)(?=\n\s*[A-Za-z][^:\n]{0,40}:|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if feedback_match:
            feedback = feedback_match.group(1).strip()
        if rewrite_match:
            rewrite = rewrite_match.group(1).strip()

        stripped = text.strip()
        if not feedback and not rewrite and stripped:
            parts = [part.strip() for part in stripped.splitlines() if part.strip()]
            feedback = parts[0] if parts else ""
            rewrite = " ".join(parts[1:]).strip() if len(parts) > 1 else ""

        return f"JT Feedback: {feedback}\nJT Rewrite: {rewrite}".strip()
