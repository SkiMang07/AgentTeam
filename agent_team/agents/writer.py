from __future__ import annotations

from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "writer.md"


class WriterAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        approved_facts = state.get("approved_facts", [])
        facts_block = "\n".join(f"- {fact}" for fact in approved_facts)
        user_task = state["user_task"]

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Draft output for the user task using only approved facts. "
                "If facts are missing, state assumptions and limits clearly. "
                "Do not introduce new factual specifics beyond the source task text and approved facts.\n\n"
                f"Task:\n{user_task}\n\n"
                f"Approved facts:\n{facts_block if facts_block else '- (none provided)'}"
            ),
        )

        return {
            **state,
            "draft": raw,
            "status": "drafted",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "writer_raw": raw,
            },
        }
