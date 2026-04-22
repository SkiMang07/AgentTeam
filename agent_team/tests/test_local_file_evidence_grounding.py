import unittest

from agent_team.agents.researcher import ResearcherAgent
from agent_team.tools.local_file_reader import build_evidence_bundle


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


if __name__ == "__main__":
    unittest.main()
