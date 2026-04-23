from __future__ import annotations

from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "backend.md"


class BackendAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        work_order = state.get("work_order", {})
        pod_task_brief = state.get("pod_task_brief", "")

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                f"Task:\n{state['user_task']}\n\n"
                f"Work order objective:\n{work_order.get('objective', '')}\n\n"
                f"Pod task brief:\n{pod_task_brief or '(none provided)'}"
            ),
        )

        pod_artifacts = dict(state.get("pod_artifacts") or {})
        pod_artifacts["backend"] = raw

        return {
            **state,
            "pod_artifacts": pod_artifacts,
            "status": "backend_drafted",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "backend_raw": raw,
            },
        }
