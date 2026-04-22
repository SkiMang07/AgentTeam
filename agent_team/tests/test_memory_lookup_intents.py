import unittest

from agent_team.agents.chief_of_staff import ChiefOfStaffAgent
from agent_team.agents.writer import WriterAgent
from agent_team.app.graph import build_graph
from agent_team.app.state import get_memory_lookup_fields


class _NoopModelClient:
    def ask(self, system_prompt: str, user_prompt: str) -> str:
        return ""


class _ChiefMemoryLookupStub:
    def run(self, state):
        return {
            **state,
            "route": "memory_lookup",
            "memory_lookup_requested": True,
            "work_order": {
                "objective": "Inspect memory",
                "deliverable_type": "memory_lookup",
                "success_criteria": ["Return requested stored fields"],
                "research_needed": False,
                "open_questions": [],
                "jt_requested": False,
            },
            "status": "routed",
        }

    def final_pass(self, state):
        return state


class _NoopAgent:
    def run(self, state):
        return state


class MemoryLookupIntentTests(unittest.TestCase):
    def test_get_memory_lookup_fields_supports_objective_and_deliverable_type(self) -> None:
        task = "What objective and deliverable type are currently stored in project memory?"
        fields = get_memory_lookup_fields(task)
        self.assertEqual(fields, ["current_objective", "active_deliverable_type"])

    def test_chief_memory_lookup_detection_excludes_transformational_requests(self) -> None:
        self.assertTrue(
            ChiefOfStaffAgent._is_memory_lookup_request(
                "What objective and deliverable type are currently stored in project memory?"
            )
        )
        self.assertFalse(
            ChiefOfStaffAgent._is_memory_lookup_request(
                "Rewrite the latest approved output from session memory into a short email."
            )
        )

    def test_memory_lookup_graph_returns_requested_fields_not_latest_output(self) -> None:
        graph = build_graph(
            _ChiefMemoryLookupStub(),
            _NoopAgent(),
            _NoopAgent(),
            _NoopAgent(),
            WriterAgent(_NoopModelClient()),
        )

        result = graph.invoke(
            {
                "user_task": "What objective and deliverable type are currently stored in project memory?",
                "dry_run": True,
                "project_memory": {
                    "current_objective": "Ship onboarding brief",
                    "active_deliverable_type": "status_update",
                    "open_questions": [],
                    "latest_draft": "draft text",
                    "latest_approved_output": "approved artifact text",
                },
                "model_metadata": {},
            }
        )

        final_output = result.get("final_output", "")
        self.assertIn("current_objective: Ship onboarding brief", final_output)
        self.assertIn("active_deliverable_type: status_update", final_output)
        self.assertNotIn("latest_approved_output: approved artifact text", final_output)

    def test_memory_lookup_graph_returns_latest_approved_output_when_requested(self) -> None:
        graph = build_graph(
            _ChiefMemoryLookupStub(),
            _NoopAgent(),
            _NoopAgent(),
            _NoopAgent(),
            WriterAgent(_NoopModelClient()),
        )

        result = graph.invoke(
            {
                "user_task": "What is the latest approved output currently stored in session memory?",
                "dry_run": True,
                "project_memory": {
                    "current_objective": "Ship onboarding brief",
                    "active_deliverable_type": "status_update",
                    "open_questions": [],
                    "latest_draft": "draft text",
                    "latest_approved_output": "approved artifact text",
                },
                "model_metadata": {},
            }
        )

        final_output = result.get("final_output", "")
        self.assertIn("latest_approved_output: approved artifact text", final_output)


if __name__ == "__main__":
    unittest.main()
