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
        jt_commenter_check = ""
        if state.get("jt_requested") and state.get("jt_mode") == "commenter":
            jt_commenter_check = (
                "\nFor JT commenter mode, enforce output contract strictly: output must contain exactly two lines: "
                "'JT Feedback: ...' and 'JT Rewrite: ...', with no extra headings, wrappers, or commentary."
                " Reject rewrites that add stronger ownership, new urgency/timing, new asks/priorities, "
                "new risk framing, or stronger commitment language than the source text."
            )

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Review this draft for quality and adherence to approved facts. "
                "Treat concrete facts/specs explicitly present in the source task text as approved grounding, "
                "even when they are specific (numbers, percentages, dates, named items, concrete claims). "
                "Reject only if the draft invents, changes, exaggerates, or misstates those source-provided specifics, "
                "or adds specifics not present in source task text or approved facts. "
                f"Return strict JSON with keys: approved (boolean), feedback (array of short strings).{jt_commenter_check}\n\n"
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
