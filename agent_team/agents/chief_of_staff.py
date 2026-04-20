from __future__ import annotations

import json
import re
from pathlib import Path

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
        return {
            **state,
            "route": route,
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
        review_feedback = state.get("review_feedback", [])
        review_block = "\n".join(f"- {item}" for item in review_feedback) or "- (none)"
        jt_findings = state.get("jt_findings")
        jt_block = jt_findings if jt_findings else "(JT not requested or no findings)"

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Run final Chief of Staff pass before human review. "
                "Return strict JSON with keys: next_step, rationale, instructions. "
                "next_step must be 'human_review' or 'redraft'. "
                "Use 'redraft' only when the draft should be revised before human review. "
                "If you request a redraft, instructions must preserve factual scope and forbid adding new specifics not in the draft/review inputs.\n\n"
                f"Draft:\n{normalized_draft}\n\n"
                f"Reviewer findings:\n{review_block}\n\n"
                f"JT findings:\n{jt_block}"
            ),
        )
        data = self._normalize_final_output(self._safe_parse(raw))
        current_notes = state.get("approved_facts", [])
        chief_notes = data.get("instructions", "")
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

        instructions = data.get("instructions")
        if not isinstance(instructions, str):
            instructions = ""

        return {
            **data,
            "next_step": next_step,
            "instructions": instructions,
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
