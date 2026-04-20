from __future__ import annotations

import json
from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "jt.md"


class JTAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        draft = state.get("draft", "")
        review_feedback = state.get("review_feedback", [])
        review_block = "\n".join(f"- {item}" for item in review_feedback) or "- (none)"

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Return strict JSON with key: comments (array of short strings). "
                "Comments only; do not rewrite the draft.\n\n"
                f"Writer draft:\n{draft}\n\n"
                f"Reviewer findings:\n{review_block}"
            ),
        )
        data = self._normalize_output(self._safe_parse(raw))
        findings = "\n".join(f"- {item}" for item in data["comments"]) if data["comments"] else None

        return {
            **state,
            "jt_findings": findings,
            "status": "jt_reviewed",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "jt_raw": raw,
            },
        }

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"comments": ["Failed to parse JT output"]}

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        comments = data.get("comments")
        if not isinstance(comments, list) or not all(isinstance(item, str) for item in comments):
            comments = ["Validation note: normalized invalid JT comments to a default note."]
        return {**data, "comments": comments}
