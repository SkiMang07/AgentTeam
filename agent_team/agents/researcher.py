from __future__ import annotations

import json
from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "researcher.md"


class ResearcherAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        user_task = state["user_task"]
        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Extract facts and gaps. Return strict JSON with keys: facts, gaps. "
                "Both must be arrays of short strings.\n\n"
                f"Task:\n{user_task}"
            ),
        )
        data = self._normalize_output(self._safe_parse(raw))
        facts = data["facts"]
        gaps = data["gaps"]

        return {
            **state,
            "research_facts": facts,
            "research_gaps": gaps,
            "approved_facts": facts,
            "status": "researched",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "researcher_raw": raw,
            },
        }

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"facts": [], "gaps": ["Failed to parse researcher output"]}

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        notes: list[str] = []

        facts = data.get("facts")
        if not isinstance(facts, list) or not all(isinstance(item, str) for item in facts):
            facts = []
            notes.append("Validation note: normalized invalid facts to an empty list.")

        gaps = data.get("gaps")
        if not isinstance(gaps, list) or not all(isinstance(item, str) for item in gaps):
            gaps = []
            notes.append("Validation note: normalized invalid gaps to an empty list.")

        if notes:
            gaps = [*gaps, *notes]

        return {**data, "facts": facts, "gaps": gaps}
