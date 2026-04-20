from __future__ import annotations

import json
import re
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
        jt_mode = state.get("jt_mode")

        schema_instruction = (
            "Return strict JSON with keys: verdict, executive_read, fatal_flaws, "
            "fixable_weaknesses, hidden_assumptions, executive_challenges, next_move. "
            "All fields must be short strings except fatal_flaws/fixable_weaknesses/"
            "hidden_assumptions/executive_challenges, which must be arrays of short strings."
            if jt_mode == "full_challenge"
            else "Return strict JSON with key: comments (array of short strings)."
        )

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                f"{schema_instruction} "
                "Comments only; do not rewrite the draft.\n\n"
                f"JT mode: {jt_mode or 'default'}\n\n"
                f"Writer draft:\n{draft}\n\n"
                f"Reviewer findings:\n{review_block}"
            ),
        )
        data = self._normalize_output(self._safe_parse(raw))
        findings = self._format_findings(data, jt_mode)

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
            candidate = JTAgent._extract_json_object(raw)
            if candidate is not None:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
            return {"comments": ["Failed to parse JT output"]}

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        if "comments" not in data:
            comments: list[str] = []
            verdict = data.get("verdict")
            if isinstance(verdict, str):
                comments.append(f"Verdict: {verdict}")
            for key in ["executive_read", "next_move"]:
                value = data.get(key)
                if isinstance(value, str):
                    comments.append(f"{key.replace('_', ' ').title()}: {value}")
            for key in ["fatal_flaws", "fixable_weaknesses", "hidden_assumptions", "executive_challenges"]:
                value = data.get(key)
                if isinstance(value, list):
                    comments.extend(f"{key.replace('_', ' ').title()}: {item}" for item in value if isinstance(item, str))
            if comments:
                return {**data, "comments": comments}

        comments = data.get("comments")
        if not isinstance(comments, list) or not all(isinstance(item, str) for item in comments):
            comments = ["Validation note: normalized invalid JT comments to a default note."]
        return {**data, "comments": comments}

    @staticmethod
    def _extract_json_object(raw: str) -> str | None:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return match.group(0)
        return None

    @staticmethod
    def _format_findings(data: dict, jt_mode: str | None) -> str | None:
        comments = data.get("comments", [])
        if not comments:
            return None
        header = "JT findings (full_challenge):" if jt_mode == "full_challenge" else "JT findings:"
        lines = "\n".join(f"- {item}" for item in comments)
        return f"{header}\n{lines}"
