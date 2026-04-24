import unittest

from agents.advisor import AdvisorAgent
from agents.advisor_router import AdvisorRouterAgent
from agents.backend import BackendAgent
from agents.chief_of_staff import ChiefOfStaffAgent
from agents.communication_influence_advisor import CommunicationInfluenceAdvisorAgent
from agents.entrepreneur_execution_advisor import EntrepreneurExecutionAdvisorAgent
from agents.frontend import FrontendAgent
from agents.growth_mindset_advisor import GrowthMindsetAdvisorAgent
from agents.jt import JTAgent
from agents.leadership_culture_advisor import LeadershipCultureAdvisorAgent
from agents.qa import QAAgent
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.strategy_systems_advisor import StrategySystemsAdvisorAgent
from agents.writer import WriterAgent
from app.graph import build_graph
from tools.local_file_reader import build_evidence_bundle
from tools.openai_client import DryRunResponsesClient


class _StubClient:
    def __init__(self) -> None:
        self.last_user_prompt = ""

    def ask(self, system_prompt: str, user_prompt: str) -> str:
        self.last_user_prompt = user_prompt
        return '{"facts": ["ok"], "gaps": []}'


class LocalFileEvidenceGroundingTests(unittest.TestCase):
    def test_build_evidence_bundle_extracts_headings_bullets_and_snippets(self) -> None:
        bundle = build_evidence_bundle(
            {
                "README.md": (
                    "# Agent Team\n"
                    "## Current scope\n"
                    "- Keep version one small\n"
                    "* No UI yet\n"
                    "1. CLI based execution\n"
                    "This repository builds a local multi agent scaffold using explicit shared state.\n"
                )
            }
        )

        self.assertEqual(len(bundle), 1)
        points = bundle[0]["evidence_points"]
        self.assertTrue(any(item.startswith("Heading: Agent Team") for item in points))
        self.assertTrue(any(item.startswith("Bullet: Keep version one small") for item in points))
        self.assertTrue(any(item.startswith("Snippet: This repository builds a local multi agent scaffold") for item in points))

    def test_researcher_includes_structured_file_evidence_in_prompt(self) -> None:
        client = _StubClient()
        agent = ResearcherAgent(client)
        state = {
            "user_task": "Summarize project scope from files.",
            "work_order": {
                "objective": "Summarize",
                "deliverable_type": "status",
                "success_criteria": ["Use file context"],
                "open_questions": [],
            },
            "files_read": ["README.md"],
            "model_metadata": {
                "file_contents": {
                    "README.md": "# Agent Team\n- CLI based execution\nNo UI in current scope.\n"
                }
            },
        }

        result = agent.run(state)
        self.assertEqual(result["research_facts"], ["ok"])
        self.assertIn("Local file evidence available: True", client.last_user_prompt)
        self.assertIn("Structured local file evidence:", client.last_user_prompt)
        self.assertIn("- file: README.md", client.last_user_prompt)
        self.assertIn("Bullet: CLI based execution", client.last_user_prompt)

    def test_brainstorm_with_local_files_runs_researcher_before_advisor_pod(self) -> None:
        dry_client = DryRunResponsesClient()
        graph = build_graph(
            ChiefOfStaffAgent(dry_client),
            JTAgent(dry_client),
            ResearcherAgent(dry_client),
            ReviewerAgent(dry_client),
            WriterAgent(dry_client),
            backend=BackendAgent(dry_client),
            frontend=FrontendAgent(dry_client),
            qa=QAAgent(dry_client),
            advisor=AdvisorAgent(dry_client),
            advisor_router=AdvisorRouterAgent(dry_client),
            strategy_systems_advisor=StrategySystemsAdvisorAgent(dry_client),
            leadership_culture_advisor=LeadershipCultureAdvisorAgent(dry_client),
            communication_influence_advisor=CommunicationInfluenceAdvisorAgent(dry_client),
            growth_mindset_advisor=GrowthMindsetAdvisorAgent(dry_client),
            entrepreneur_execution_advisor=EntrepreneurExecutionAdvisorAgent(dry_client),
        )
        test_file = (
            "# Test Context\n\n"
            "Use exactly these three workstreams:\n"
            "1. Alpha Intake\n"
            "2. Beta Build\n"
            "3. Gamma Launch\n\n"
            "Do not rename the workstreams.\n"
        )
        result = graph.invoke(
            {
                "user_task": "What are the three workstreams I should use based on my files included?",
                "advisor_pod_requested": True,
                "dry_run": True,
                "files_read": ["/tmp/test_context.md"],
                "model_metadata": {"file_contents": {"/tmp/test_context.md": test_file}},
            }
        )
        execution_path = result.get("model_metadata", {}).get("execution_path", [])
        self.assertIn("researcher", execution_path)
        self.assertIn("evidence_extract", execution_path)
        self.assertIn("advisor_entry", execution_path)
        self.assertLess(execution_path.index("researcher"), execution_path.index("advisor_entry"))
        self.assertTrue(result.get("brainstorm_file_grounding_used"))
        self.assertIn("Alpha Intake", result.get("advisor_brief", ""))
        self.assertIn("Beta Build", result.get("advisor_brief", ""))
        self.assertIn("Gamma Launch", result.get("advisor_brief", ""))

    def test_brainstorm_without_local_files_skips_researcher(self) -> None:
        dry_client = DryRunResponsesClient()
        graph = build_graph(
            ChiefOfStaffAgent(dry_client),
            JTAgent(dry_client),
            ResearcherAgent(dry_client),
            ReviewerAgent(dry_client),
            WriterAgent(dry_client),
            backend=BackendAgent(dry_client),
            frontend=FrontendAgent(dry_client),
            qa=QAAgent(dry_client),
            advisor=AdvisorAgent(dry_client),
            advisor_router=AdvisorRouterAgent(dry_client),
            strategy_systems_advisor=StrategySystemsAdvisorAgent(dry_client),
            leadership_culture_advisor=LeadershipCultureAdvisorAgent(dry_client),
            communication_influence_advisor=CommunicationInfluenceAdvisorAgent(dry_client),
            growth_mindset_advisor=GrowthMindsetAdvisorAgent(dry_client),
            entrepreneur_execution_advisor=EntrepreneurExecutionAdvisorAgent(dry_client),
        )
        result = graph.invoke(
            {
                "user_task": "Brainstorm a strategy direction for this quarter.",
                "advisor_pod_requested": True,
                "dry_run": True,
                "files_read": [],
                "model_metadata": {"file_contents": {}},
            }
        )
        execution_path = result.get("model_metadata", {}).get("execution_path", [])
        self.assertIn("advisor_entry", execution_path)
        self.assertNotIn("researcher", execution_path)
        self.assertNotIn("evidence_extract", execution_path)


if __name__ == "__main__":
    unittest.main()
