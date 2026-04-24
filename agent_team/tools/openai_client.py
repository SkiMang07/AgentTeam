from __future__ import annotations

import json
import logging
from typing import Any, Callable

from openai import OpenAI

from app.config import Settings

log = logging.getLogger(__name__)


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

    def ask_with_function_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict],
        tool_handlers: dict[str, Callable[..., Any]],
        max_rounds: int = 5,
    ) -> tuple[str, list[dict]]:
        """Execute a conversation with custom function tools, handling the call loop.

        Unlike ``ask_with_tools`` (which passes hosted tools like
        ``web_search_preview`` that OpenAI executes automatically),
        this method handles **custom function tools** by:
          1. Calling the model.
          2. Detecting ``function_call`` items in the response output.
          3. Executing each via the matching handler in *tool_handlers*.
          4. Feeding the results back using ``previous_response_id``.
          5. Repeating until no more function calls are returned (or *max_rounds*
             is exhausted).

        Args:
            system_prompt: Agent system prompt.
            user_prompt: User / task prompt.
            tools: List of OpenAI function tool schemas (``{"type": "function", ...}``).
            tool_handlers: Mapping of tool name → callable that executes the tool
                and returns a string result.
            max_rounds: Maximum tool-call iterations before returning.

        Returns:
            Tuple of (final_text, tool_calls_log) where tool_calls_log is a list
            of dicts with keys ``tool``, ``arguments``, and ``result``.
        """
        tool_calls_log: list[dict] = []

        # Initial request
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=tools,
        )

        for _round in range(max_rounds):
            # Collect function_call items from the response output
            function_calls = [
                item
                for item in (response.output or [])
                if getattr(item, "type", None) == "function_call"
            ]

            if not function_calls:
                # No more tool calls — we have the final answer
                break

            # Execute each function call and build tool result items
            tool_results: list[dict] = []
            for fc in function_calls:
                handler = tool_handlers.get(fc.name)
                if handler is None:
                    result = f"error: no handler registered for tool '{fc.name}'"
                    log.warning("[openai_client] No handler for tool '%s'", fc.name)
                else:
                    try:
                        args = json.loads(fc.arguments)
                        result = str(handler(**args))
                        log.info(
                            "[openai_client] Tool '%s' executed: %s",
                            fc.name,
                            result[:120],
                        )
                    except Exception as exc:  # noqa: BLE001
                        result = f"error executing {fc.name}: {exc}"
                        log.warning(
                            "[openai_client] Tool '%s' raised: %s", fc.name, exc
                        )

                tool_calls_log.append(
                    {
                        "tool": fc.name,
                        "arguments": fc.arguments,
                        "result": result,
                    }
                )
                tool_results.append(
                    {
                        "type": "function_call_output",
                        "call_id": fc.call_id,
                        "output": result,
                    }
                )

            # Feed results back, continuing from the previous response
            response = self._client.responses.create(
                model=self._model,
                previous_response_id=response.id,
                input=tool_results,
                tools=tools,
            )

        return response.output_text.strip(), tool_calls_log


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

    def ask_with_function_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,  # noqa: ARG002
        tool_handlers: dict | None = None,  # noqa: ARG002
        max_rounds: int = 5,  # noqa: ARG002
    ) -> tuple[str, list[dict]]:
        """Dry-run: no tool calls; delegates to ask()."""
        return self.ask(system_prompt, user_prompt), []

    def ask(self, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
        # Obsidian vault navigator folder selection
        if "You are a knowledge navigator for an Obsidian vault." in system_prompt:
            return json.dumps({"relevant_paths": []})

        if "Create and route the Chief of Staff work order." in user_prompt:
            task = user_prompt
            if "Current task:\n" in user_prompt:
                task = user_prompt.split("Current task:\n", maxsplit=1)[-1]
                task = task.split("\n\nObsidian vault context", maxsplit=1)[0]
            task = task.lower()
            cli_dev_flag = "CLI dev pod requested flag: True" in user_prompt
            cli_advisor_flag = "CLI advisor pod requested flag: True" in user_prompt
            route = "write_direct" if "write_direct" in task else "research"
            inferred_dev = "implementation" in task or "code" in task
            inferred_advisor = any(phrase in task for phrase in ("advisor", "brainstorm", "strategy", "evaluate"))
            dev_pod_requested = cli_dev_flag or (inferred_dev and not cli_advisor_flag)
            advisor_pod_requested = cli_advisor_flag or inferred_advisor
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
                "dev_pod_requested": dev_pod_requested,
                "advisor_pod_requested": advisor_pod_requested,
            }
            return json.dumps(
                {
                    "work_order": work_order,
                    "route": route,
                    "rationale": "dry-run deterministic routing",
                }
            )

        if "You are the Advisor Router for the Advisor Pod." in system_prompt:
            # Dry-run stubs for the semantic routing path.
            # Production routing is fully LLM-driven; these stubs cover the four
            # representative test cases used in dry-run workflow validation.
            task = user_prompt.lower()
            if "rewrite this sentence to be clearer" in task or "proofread" in task:
                # Fast-exit: simple rewrite — no advisors needed.
                selected: list[str] = []
                reasons: dict[str, str] = {}
            elif "prioritize" in task or "tradeoff" in task or "portfolio" in task or "operating model" in task:
                # Strategy/systems domain match.
                selected = ["strategy_systems"]
                reasons = {"strategy_systems": "Objective falls within strategy and tradeoff framing domain."}
            elif "stakeholder" in task or "persuade" in task or "narrative" in task or "announcement" in task:
                # Communication/influence domain match.
                selected = ["communication_influence"]
                reasons = {"communication_influence": "Objective requires messaging and stakeholder influence framing."}
            elif "ship" in task or "launch" in task or "execution plan" in task or "implementation plan" in task:
                # Entrepreneur/execution domain match.
                selected = ["entrepreneur_execution"]
                reasons = {"entrepreneur_execution": "Objective is delivery-focused and requires execution planning."}
            else:
                # Default: strategy as the broadest general-purpose advisor.
                selected = ["strategy_systems"]
                reasons = {"strategy_systems": "Default dry-run advisor for general strategic questions."}

            all_ids = (
                "strategy_systems",
                "leadership_culture",
                "communication_influence",
                "growth_mindset",
                "entrepreneur_execution",
            )
            skipped = {
                advisor_id: "Not selected for this task in dry-run routing."
                for advisor_id in all_ids
                if advisor_id not in selected
            }
            return json.dumps(
                {
                    "selected_advisors": selected,
                    "selection_reason": reasons,
                    "skipped_advisors": skipped,
                    "advisor_route_confidence": "high",
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

        if "You are the Advisor Agent — the Chief Advisor and council leader" in system_prompt:
            return "DRY RUN ADVISOR SYNTHESIS: combined selected advisor viewpoints."

        if "Apply your cluster's frameworks to the task above." in user_prompt:
            return "DRY RUN ADVISOR NOTE: cluster-specific recommendation."

        return ""
