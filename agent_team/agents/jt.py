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
        writer_draft = state.get("draft", "")
        approved_facts = state.get("approved_facts", [])
        facts_block = "\n".join(f"- {fact}" for fact in approved_facts) or "- (none provided)"
        jt_mode = state.get("jt_mode")

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Return strict JSON with keys: jt_feedback, jt_rewrite. "
                "jt_feedback must be an array of short strings. "
                "jt_rewrite must be a single string.\n\n"
                f"JT mode: {jt_mode or 'default'}\n\n"
                f"Task:\n{state['user_task']}\n\n"
                f"Approved facts:\n{facts_block}\n\n"
                f"Writer draft to challenge and rewrite:\n{writer_draft}"
            ),
        )

        data = self._normalize_output(self._safe_parse(raw), fallback_rewrite=writer_draft)
        jt_feedback = data["jt_feedback"]
        jt_rewrite = data["jt_rewrite"]

        return {
            **state,
            "jt_input": {
                "writer_draft": writer_draft,
                "user_task": state["user_task"],
                "approved_facts": approved_facts,
                "jt_mode": jt_mode,
            },
            "jt_feedback": jt_feedback,
            "jt_rewrite": jt_rewrite,
            "jt_findings": self._format_findings(jt_feedback),
            "draft": jt_rewrite,
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
            return {}

    @staticmethod
    def _normalize_output(data: dict, fallback_rewrite: str) -> dict:
        jt_feedback = data.get("jt_feedback")
        if not isinstance(jt_feedback, list) or not all(isinstance(item, str) for item in jt_feedback):
            jt_feedback = ["JT output normalization note: feedback did not match the required schema."]

        jt_rewrite = data.get("jt_rewrite")
        if not isinstance(jt_rewrite, str) or not jt_rewrite.strip():
            jt_rewrite = fallback_rewrite
            jt_feedback = [
                *jt_feedback,
                "JT output normalization note: rewrite was empty or invalid, so writer draft was reused.",
            ]

        return {
            "jt_feedback": jt_feedback,
            "jt_rewrite": jt_rewrite.strip(),
        }

    @staticmethod
    def _extract_json_object(raw: str) -> str | None:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return match.group(0)
        return None

    @staticmethod
    def _format_findings(feedback: list[str]) -> str | None:
        if not feedback:
            return None
        lines = "\n".join(f"- {item}" for item in feedback)
        return f"JT findings:\n{lines}"
