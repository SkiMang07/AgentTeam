from __future__ import annotations

from pathlib import Path

from agents.base_sub_advisor import BaseSubAdvisorAgent
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "growth_mindset_advisor.md"


class GrowthMindsetAdvisorAgent(BaseSubAdvisorAgent):
    """Growth & Mindset cluster: Clear, Manson, Lakhiani, Grant."""

    cluster_key = "growth_mindset"

    def __init__(self, client: ResponsesClient) -> None:
        super().__init__(client, PROMPT_PATH)
