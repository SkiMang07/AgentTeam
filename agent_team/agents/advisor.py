from __future__ import annotations

from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "advisor.md"


class AdvisorAgent:
    """Chief Advisor — synthesizes selected cluster outputs into a single advisory draft."""

    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def synthesize(self, state: SharedState) -> SharedState:
        task = state.get("user_task", "")
        brief = state.get("advisor_brief", "")
        outputs: dict[str, str] = state.get("advisor_outputs") or {}

        cluster_block = self._format_cluster_outputs(outputs)

        user_prompt = (
            f"Task: {task}\n\n"
            f"Advisor Brief: {brief}\n\n"
            f"--- Cluster Advisor Outputs ---\n\n"
            f"{cluster_block}"
        )

        synthesis = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=user_prompt,
        )

        return {
            **state,
            "draft": synthesis,
            "advisor_synthesis": synthesis,
            "status": "advisor_assembled",
        }

    @staticmethod
    def _format_cluster_outputs(outputs: dict[str, str]) -> str:
        if not outputs:
            return "(no cluster outputs available)"
        sections: list[str] = []
        labels = {
            "strategy_systems": "Strategy & Systems",
            "leadership_culture": "Leadership & Culture",
            "communication_influence": "Communication & Influence",
            "growth_mindset": "Growth & Mindset",
            "entrepreneur_execution": "Entrepreneur & Execution",
        }
        for key, label in labels.items():
            content = outputs.get(key, "").strip()
            if content:
                sections.append(f"### {label}\n\n{content}")
        return "\n\n---\n\n".join(sections) if sections else "(no cluster outputs available)"
