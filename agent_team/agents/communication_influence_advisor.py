from __future__ import annotations

from pathlib import Path

from agents.base_sub_advisor import BaseSubAdvisorAgent
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "communication_influence_advisor.md"


class CommunicationInfluenceAdvisorAgent(BaseSubAdvisorAgent):
    """Communication & Influence cluster: Voss, Duhigg, Duarte, Berger, Gladwell."""

    cluster_key = "communication_influence"

    def __init__(self, client: ResponsesClient) -> None:
        super().__init__(client, PROMPT_PATH)
