import unittest

from agent_team.agents.reviewer import ReviewerAgent


class ConstrainedRewriteGroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user_task = (
            'Rewrite this draft for clarity without adding any new facts: '
            '"response times improved by 18 percent"'
        )

    def test_faithful_source_grounded_rewrite_passes(self) -> None:
        findings = ReviewerAgent._default_findings(
            overall_assessment="Needs revision.",
            unsupported_claims=[
                "Unsupported claim: 'response times improved by 18 percent' is not grounded in source."
            ],
            recommended_next_action="revise",
        )

        updated = ReviewerAgent._enforce_constrained_rewrite_contract(
            findings=findings,
            user_task=self.user_task,
            approved_facts=[],
            draft="response times improved by 18 percent",
        )

        self.assertEqual(updated["unsupported_claims"], [])
        self.assertEqual(updated["missing_content"], [])
        self.assertEqual(updated["recommended_next_action"], "approve")

    def test_changed_subject_with_same_number_stays_unsupported(self) -> None:
        findings = ReviewerAgent._default_findings(
            overall_assessment="Needs revision.",
            unsupported_claims=[
                "Unsupported claim: 'revenue improved by 18 percent' is not grounded in source."
            ],
            recommended_next_action="revise",
        )

        updated = ReviewerAgent._enforce_constrained_rewrite_contract(
            findings=findings,
            user_task=self.user_task,
            approved_facts=[],
            draft="revenue improved by 18 percent",
        )

        self.assertEqual(len(updated["unsupported_claims"]), 1)
        self.assertIn("revenue improved by 18 percent", updated["unsupported_claims"][0])

    def test_dropped_source_number_is_flagged(self) -> None:
        findings = ReviewerAgent._default_findings(
            overall_assessment="Looks good.",
            recommended_next_action="approve",
        )

        updated = ReviewerAgent._enforce_constrained_rewrite_contract(
            findings=findings,
            user_task=self.user_task,
            approved_facts=[],
            draft="response times improved significantly",
        )

        self.assertTrue(
            any("dropped source-provided specific '18'" in item for item in updated["missing_content"])
        )
        self.assertEqual(updated["recommended_next_action"], "revise")

    def test_new_number_is_flagged(self) -> None:
        findings = ReviewerAgent._default_findings(
            overall_assessment="Looks good.",
            recommended_next_action="approve",
        )

        updated = ReviewerAgent._enforce_constrained_rewrite_contract(
            findings=findings,
            user_task=self.user_task,
            approved_facts=[],
            draft="response times improved by 22 percent",
        )

        self.assertTrue(
            any("added new specific '22'" in item for item in updated["unsupported_claims"])
        )
        self.assertEqual(updated["recommended_next_action"], "revise")


if __name__ == "__main__":
    unittest.main()
