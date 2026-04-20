from __future__ import annotations

import json
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
                "route, rationale. route must be 'research' or 'write_direct'.\n\n"
                f"Task:\n{user_task}"
            ),
        )
        data = self._normalize_output(self._safe_parse(raw))
        route = data["route"]
        return {
            **state,
            "route": route,
            "status": "routed",
            "model_metadata": {"chief_of_staff_raw": raw},
        }

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"route": "research", "rationale": "fallback due to parse error"}

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        route = data.get("route")
        if route not in {"research", "write_direct"}:
            route = "research"
        return {**data, "route": route}
