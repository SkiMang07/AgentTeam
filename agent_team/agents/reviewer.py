from __future__ import annotations

import json
import re
from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "reviewer.md"


class ReviewerAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        user_task = state["user_task"]
        draft = state.get("draft", "")
        approved_facts = state.get("approved_facts", [])
        facts_block = "\n".join(f"- {fact}" for fact in approved_facts) or "- (none provided)"
        is_jt_commenter = state.get("jt_requested") and state.get("jt_mode") == "commenter"

        if is_jt_commenter:
            jt_shape_error = self._validate_jt_commenter_draft_shape(draft)
            if jt_shape_error is not None:
                return {
                    **state,
                    "review_approved": False,
                    "review_feedback": [jt_shape_error],
                    "reviewer_parse_failed": False,
                    "reviewer_parse_error_raw": "",
                    "status": "reviewed",
                    "model_metadata": {
                        **state.get("model_metadata", {}),
                        "reviewer_parse_failed": False,
                    },
                }

        jt_commenter_check = ""
        if is_jt_commenter:
            jt_commenter_check = (
                "\nFor JT commenter mode, validate the Writer draft shape:"
                " exactly two non-empty lines, line 1 starts with 'JT Feedback:',"
                " and line 2 starts with 'JT Rewrite:'."
            )

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Review this draft for quality and adherence to approved facts. "
                "Treat concrete facts/specs explicitly present in the source task text as approved grounding, "
                "even when they are specific (numbers, percentages, dates, named items, concrete claims). "
                "Reject only if the draft invents, changes, exaggerates, or misstates those source-provided specifics, "
                "or adds specifics not present in source task text or approved facts. "
                "Return ONLY valid JSON (no markdown fences, no commentary before/after) with keys: "
                f"approved (boolean), feedback (array of short strings).{jt_commenter_check}\n\n"
                f"Task:\n{user_task}\n\n"
                f"Approved facts:\n{facts_block}\n\n"
                f"Draft:\n{draft}"
            ),
        )
        parsed = self._safe_parse(raw)
        data = self._normalize_output(parsed)
        parse_failed = bool(parsed.get("_parse_failed", False))

        return {
            **state,
            "review_approved": data["approved"],
            "review_feedback": data["feedback"],
            "reviewer_parse_failed": parse_failed,
            "reviewer_parse_error_raw": raw if parse_failed else "",
            "status": "reviewer_parse_failed" if parse_failed else "reviewed",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "reviewer_raw": raw,
                "reviewer_parse_failed": parse_failed,
            },
        }

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            candidate = ReviewerAgent._extract_json_object(raw)
            if candidate is not None:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
            return {
                "approved": False,
                "feedback": ["Failed to parse reviewer output"],
                "_parse_failed": True,
            }

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        approved = data.get("approved")
        if not isinstance(approved, bool):
            approved = False

        feedback = data.get("feedback")
        if not isinstance(feedback, list) or not all(isinstance(item, str) for item in feedback):
            feedback = ["Validation note: normalized invalid feedback to a default note."]

        return {**data, "approved": approved, "feedback": feedback}

    @staticmethod
    def _extract_json_object(raw: str) -> str | None:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return match.group(0)
        return None

    @staticmethod
    def _validate_jt_commenter_draft_shape(draft: str) -> str | None:
        lines = [line.strip() for line in draft.splitlines() if line.strip()]
        if len(lines) != 2:
            return "JT commenter contract failure: draft must contain exactly two non-empty lines."
        if not lines[0].startswith("JT Feedback:"):
            return "JT commenter contract failure: line 1 must start with 'JT Feedback:'."
        if not lines[1].startswith("JT Rewrite:"):
            return "JT commenter contract failure: line 2 must start with 'JT Rewrite:'."
        return None
