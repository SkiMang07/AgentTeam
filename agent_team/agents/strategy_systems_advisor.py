from __future__ import annotations

from pathlib import Path

from agents.base_sub_advisor import BaseSubAdvisorAgent
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "strategy_systems_advisor.md"


class StrategySystemsAdvisorAgent(BaseSubAdvisorAgent):
    """Strategy & Systems cluster: Dalio, Meadows, Senge, Christensen, Moore, Collins, Kahneman."""

    cluster_key = "strategy_systems"

    def __init__(self, client: ResponsesClient) -> None:
        super().__init__(client, PROMPT_PATH)
