from __future__ import annotations

from pathlib import Path

from agents.base_sub_advisor import BaseSubAdvisorAgent
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "leadership_culture_advisor.md"


class LeadershipCultureAdvisorAgent(BaseSubAdvisorAgent):
    """Leadership & Culture cluster: Sinek, Brown, Lencioni, Scott, Meyer, HBR."""

    cluster_key = "leadership_culture"

    def __init__(self, client: ResponsesClient) -> None:
        super().__init__(client, PROMPT_PATH)
