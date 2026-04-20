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


class DryRunResponsesClient:
    def __init__(self) -> None:
        self._reviewer_calls = 0
        self._chief_final_calls = 0

    def ask(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
        if "Classify and route this task." in user_prompt:
            task = user_prompt.split("Task:\n", maxsplit=1)[-1].lower()
            route = "write_direct" if "write_direct" in task else "research"
            return json.dumps(
                {
                    "route": route,
                    "rationale": "dry-run deterministic routing",
                }
            )

        if "Extract facts and gaps." in user_prompt:
            return json.dumps(
                {
                    "facts": [
                        "Dry-run fact: this output is generated without external API calls.",
                        "Dry-run fact: deterministic researcher output enables repeatable tests.",
                    ],
                    "gaps": [
                        "Dry-run gap: no real external research was performed.",
                    ],
                }
            )

        if "Draft output for the user task" in user_prompt:
            approved_facts = user_prompt.count("\n- ")
            return (
                "DRY RUN DRAFT\n"
                f"Generated with {approved_facts} approved facts. "
                "This draft is deterministic and intended for workflow validation."
            )

        if "Review this draft for quality" in user_prompt:
            self._reviewer_calls += 1
            if self._reviewer_calls == 1:
                return json.dumps(
                    {
                        "approved": False,
                        "feedback": ["Add one revision pass to exercise redraft flow."],
                    }
                )
            return json.dumps({"approved": True, "feedback": []})

        if "Return strict JSON with keys: verdict, executive_read" in user_prompt:
            return json.dumps(
                {
                    "verdict": "Needs revision before confidence is justified.",
                    "executive_read": "Sequence is mostly sensible but has brittle contracts.",
                    "fatal_flaws": ["JT activation and parsing contracts are not yet robust enough."],
                    "fixable_weaknesses": ["Reviewer criteria are too broad for internal planning tasks."],
                    "hidden_assumptions": ["Assumes strict JSON compliance without fallback parsing."],
                    "executive_challenges": ["How do we prove JT path was executed every run?"],
                    "next_move": "Tighten schema handling and add path visibility in CLI output.",
                }
            )

        if "Return strict JSON with key: comments" in user_prompt:
            return json.dumps(
                {
                    "comments": [
                        "JT comment: tighten one claim for precision.",
                        "JT comment: call out one remaining assumption explicitly.",
                    ]
                }
            )

        if "Run final Chief of Staff pass before human review." in user_prompt:
            self._chief_final_calls += 1
            if "JT findings:\n(JT not requested or no findings)" in user_prompt:
                return json.dumps(
                    {
                        "next_step": "human_review",
                        "rationale": "No JT challenge requested.",
                        "instructions": "",
                    }
                )
            if self._chief_final_calls == 1:
                return json.dumps(
                    {
                        "next_step": "redraft",
                        "rationale": "Apply JT feedback once.",
                        "instructions": "Incorporate JT comments without changing scope.",
                    }
                )
            return json.dumps(
                {
                    "next_step": "human_review",
                    "rationale": "One JT-informed redraft completed.",
                    "instructions": "",
                }
            )

        return ""
