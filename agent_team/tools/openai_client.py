from __future__ import annotations

import json

from openai import OpenAI

from app.config import Settings


class ResponsesClient:
    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.model

    def ask(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.output_text.strip()

    def ask_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,
    ) -> str:
        """
        Like ask(), but passes a tools list to the Responses API.

        For web search pass: tools=[{"type": "web_search_preview"}]
        The model will call the tool automatically and output_text contains
        the final synthesised answer — no extra parsing needed.
        """
        kwargs: dict = {
            "model": self._model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if tools:
            kwargs["tools"] = tools
        response = self._client.responses.create(**kwargs)
        return response.output_text.strip()


class DryRunResponsesClient:
    def __init__(self) -> None:
        self._reviewer_calls = 0
        self._chief_final_calls = 0

    def ask_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,  # noqa: ARG002
    ) -> str:
        """Dry-run variant of ask_with_tools — delegates to ask()."""
        return self.ask(system_prompt, user_prompt)

    def ask(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
        # Obsidian vault navigator folder selection
        if "You are a knowledge navigator for an Obsidian vault." in system_prompt:
            return json.dumps({"relevant_paths": []})

        if "Create and route the Chief of Staff work order." in user_prompt:
            task = user_prompt.split("Task:\n", maxsplit=1)[-1].lower()
            route = "write_direct" if "write_direct" in task else "research"
            work_order = {
                "objective": "Complete the requested task.",
                "deliverable_type": "draft_response",
                "success_criteria": [
                    "Address the user's stated objective.",
                    "Keep the output grounded in approved facts.",
                ],
                "research_needed": route == "research",
                "open_questions": [],
                "jt_requested": "jt" in task,
            }
            return json.dumps(
                {
                    "work_order": work_order,
                    "route": route,
                    "rationale": "dry-run deterministic routing",
                }
            )

        if "Extract facts and gaps for the Chief of Staff work order." in user_prompt:
            return json.dumps(
                {
                    "facts": [
                        "Dry-run fact: this output is generated without external API calls.",
                        "Dry-run fact: deterministic researcher output enables repeatable tests.",
                    ],
                    "gaps": ["Dry-run gap: no real external research was performed."],
                }
            )

        if "Draft output for the Chief of Staff work order" in user_prompt:
            approved_facts = user_prompt.count("\n- ")
            return (
                "DRY RUN DRAFT\n"
                f"Generated with {approved_facts} approved facts. "
                "This draft is deterministic and intended for workflow validation."
            )

        if "Return strict JSON with keys: jt_feedback, jt_rewrite." in user_prompt:
            return json.dumps(
                {
                    "jt_feedback": [
                        "Lead with the key point in the first sentence.",
                        "Remove one repetitive qualifier to tighten flow.",
                    ],
                    "jt_rewrite": "DRY RUN JT REWRITE: tightened draft for deterministic JT-path validation.",
                }
            )

        if "Review this draft for quality" in user_prompt or "Reviewer validator task:" in user_prompt:
            self._reviewer_calls += 1
            task_block = user_prompt.split("Task:\n", maxsplit=1)[-1].lower()
            if "<task>" in user_prompt and "</task>" in user_prompt:
                task_block = user_prompt.split("<task>", maxsplit=1)[-1].split("</task>", maxsplit=1)[0].lower()
            if "simulate reviewer parse failure" in task_block:
                return "not-json-reviewer-output"
            if self._reviewer_calls == 1:
                return json.dumps(
                    {
                        "overall_assessment": "Draft needs one quality-control revision before approval.",
                        "missing_content": ["Add one concrete revision pass note for deterministic flow coverage."],
                        "unsupported_claims": [],
                        "contradictions_or_logic_problems": [],
                        "format_or_structure_issues": [],
                        "recommended_next_action": "revise",
                    }
                )
            return json.dumps(
                {
                    "overall_assessment": "Draft passes quality-control checks.",
                    "missing_content": [],
                    "unsupported_claims": [],
                    "contradictions_or_logic_problems": [],
                    "format_or_structure_issues": [],
                    "recommended_next_action": "approve",
                }
            )

        if "Run final Chief of Staff pass before human review." in user_prompt:
            self._chief_final_calls += 1
            if "JT findings:\n(JT not requested)" in user_prompt:
                return json.dumps(
                    {
                        "next_step": "human_review",
                        "rationale": "No JT challenge requested.",
                        "instructions": "",
                        "answers_request": True,
                        "matches_deliverable_type": True,
                        "reviewer_findings_addressed": True,
                        "jt_findings_addressed": True,
                        "obvious_missing_items": [],
                    }
                )
            if self._chief_final_calls == 1:
                return json.dumps(
                    {
                        "next_step": "redraft",
                        "rationale": "Apply JT feedback once.",
                        "instructions": "Incorporate JT comments without changing scope.",
                        "answers_request": True,
                        "matches_deliverable_type": True,
                        "reviewer_findings_addressed": True,
                        "jt_findings_addressed": False,
                        "obvious_missing_items": ["Address JT precision concerns before human review."],
                    }
                )
            return json.dumps(
                {
                    "next_step": "human_review",
                    "rationale": "One JT-informed redraft completed.",
                    "instructions": "",
                    "answers_request": True,
                    "matches_deliverable_type": True,
                    "reviewer_findings_addressed": True,
                    "jt_findings_addressed": True,
                    "obvious_missing_items": [],
                }
            )

        return ""
