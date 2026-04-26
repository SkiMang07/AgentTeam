from __future__ import annotations

from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient


class BaseSubAdvisorAgent:
    """Shared base class for all five advisor cluster agents."""

    cluster_key: str  # override in each subclass, e.g. "strategy_systems"

    def __init__(self, client: ResponsesClient, prompt_path: Path) -> None:
        self._client = client
        self._prompt = prompt_path.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        task = state.get("user_task", "")
        brief = state.get("advisor_brief", "")

        user_prompt = (
            f"Task: {task}\n\n"
            f"Advisor Brief: {brief}\n\n"
            "Apply your cluster's frameworks to the task above. Be specific, direct, and "
            "grounded in the thinkers' actual models. Avoid generic advice. "
            "When the advisor brief includes local file evidence, treat those file-derived names, "
            "labels, constraints, and structures as binding context. You may critique or refine them, "
            "but do not silently rename or replace them with generic frameworks.\n\n"
            "Close your response with the required [CLUSTER SIGNAL] block as specified in your "
            "system prompt. The Stance, Top Priority, and Disagrees With fields are mandatory — "
            "be direct and honest, do not soften into false consensus."
        )

        response = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=user_prompt,
        )

        current_outputs: dict[str, str] = dict(state.get("advisor_outputs") or {})
        current_outputs[self.cluster_key] = response

        return {
            **state,
            "advisor_outputs": current_outputs,
            "status": f"advisor_{self.cluster_key}_done",
        }
