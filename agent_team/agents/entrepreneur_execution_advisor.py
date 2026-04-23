from __future__ import annotations

from pathlib import Path

from agents.base_sub_advisor import BaseSubAdvisorAgent
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "entrepreneur_execution_advisor.md"


class EntrepreneurExecutionAdvisorAgent(BaseSubAdvisorAgent):
    """Entrepreneur & Execution cluster: Horowitz, Bet-David, Lawson."""

    cluster_key = "entrepreneur_execution"

    def __init__(self, client: ResponsesClient) -> None:
        super().__init__(client, PROMPT_PATH)
