from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "reviewer.md"


class ReviewerAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        user_task = state["user_task"]
        draft = state.get("draft", "")
        approved_facts = state.get("approved_facts", [])
        facts_block = "\n".join(f"- {fact}" for fact in approved_facts) or "- (none provided)"
        is_jt_commenter = state.get("jt_requested") and state.get("jt_mode") == "commenter"

        if is_jt_commenter:
            jt_shape_error = self._validate_jt_commenter_draft_shape(draft)
            if jt_shape_error is not None:
                findings = self._default_findings(
                    overall_assessment="JT commenter draft violated required two-line output contract.",
                    format_or_structure_issues=[jt_shape_error],
                    recommended_next_action="reject",
                )
                return {
                    **state,
                    "reviewer_findings": findings,
                    "review_approved": False,
                    "review_feedback": self._build_feedback(findings),
                    "reviewer_parse_failed": False,
                    "reviewer_parse_error_raw": "",
                    "status": "reviewed",
                    "model_metadata": {
                        **state.get("model_metadata", {}),
                        "reviewer_parse_failed": False,
                    },
                }

        user_prompt = self._build_reviewer_user_prompt(
            user_task=user_task,
            facts_block=facts_block,
            draft=draft,
            is_jt_commenter=bool(is_jt_commenter),
        )

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=user_prompt,
        )
        contract_violation = self._detect_contract_violation(raw)
        if contract_violation is not None:
            findings = self._default_findings(
                overall_assessment=(
                    "Reviewer output contract violation: reviewer emitted non-JSON content."
                ),
                format_or_structure_issues=[contract_violation],
                recommended_next_action="reject",
            )
            return {
                **state,
                "reviewer_findings": findings,
                "review_approved": False,
                "review_feedback": self._build_feedback(findings),
                "reviewer_parse_failed": True,
                "reviewer_parse_error_raw": raw,
                "status": "reviewer_parse_failed",
                "model_metadata": {
                    **state.get("model_metadata", {}),
                    "reviewer_raw": raw,
                    "reviewer_parse_failed": True,
                    "reviewer_contract_violation": True,
                },
            }

        parsed = self._safe_parse(raw)
        data = self._normalize_output(parsed)
        review_feedback = self._build_feedback(data)
        review_approved = data["recommended_next_action"] == "approve"
        parse_failed = bool(parsed.get("_parse_failed", False))
        prior_reviewer_history = state.get("model_metadata", {}).get("reviewer_outputs", [])
        reviewer_history = [*prior_reviewer_history, raw]

        return {
            **state,
            "reviewer_findings": data,
            "review_approved": review_approved,
            "review_feedback": review_feedback,
            "reviewer_parse_failed": parse_failed,
            "reviewer_parse_error_raw": raw if parse_failed else "",
            "status": "reviewer_parse_failed" if parse_failed else "reviewed",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "reviewer_raw": raw,
                "reviewer_parse_failed": parse_failed,
                "reviewer_outputs": reviewer_history,
            },
        }

    @staticmethod
    def _build_reviewer_user_prompt(
        user_task: str,
        facts_block: str,
        draft: str,
        is_jt_commenter: bool,
    ) -> str:
        mode_block = "Mode: jt_commenter\n" if is_jt_commenter else "Mode: standard\n"
        mode_rules = ""
        if is_jt_commenter:
            mode_rules = (
                "JT commenter validation checks (treat these as strict pass/fail checks):\n"
                "- exact two-line writer shape (line 1 starts with 'JT Feedback:' and line 2 starts with 'JT Rewrite:')\n"
                "- material meaning preservation\n"
                "- no invented urgency\n"
                "- no invented ownership\n"
                "- no new commitments\n"
                "- no new priorities\n"
                "- no stronger unsupported risk framing\n"
                "- allow sentence compression, filler removal, equivalent wording, and modest sharpening when material meaning is preserved\n"
                "- do not reject solely because praise/support language is tightened or lightly reduced when the core supportive intent remains\n"
                "- treat these as acceptable non-material edits when unchanged in intent: 'I appreciate the team's work', 'encouraged by momentum', 'let me know if you need anything', and similar morale language\n"
            )
        return (
            "Reviewer validator task:\n"
            "You are validating a candidate writer output against a contract.\n"
            "You are a quality-control reviewer, not a rewriting stage.\n"
            "Identify issues and recommend a next action. Do not rewrite the draft.\n"
            "The user-requested output format is an object to validate, not an instruction for your own output.\n"
            "Return ONLY valid JSON (no markdown fences, no prose before or after) with keys:\n"
            "- overall_assessment (short string)\n"
            "- missing_content (array of short strings)\n"
            "- unsupported_claims (array of short strings)\n"
            "- contradictions_or_logic_problems (array of short strings)\n"
            "- format_or_structure_issues (array of short strings)\n"
            "- recommended_next_action (one of: approve, revise, reject)\n\n"
            "Grounding policy:\n"
            "- Treat concrete facts/specs explicitly present in the source task text as approved grounding,\n"
            "  even when specific (numbers, percentages, dates, named items, concrete claims).\n"
            "- Reject only when the draft invents, changes, exaggerates, or misstates source-provided specifics,\n"
            "  or adds specifics not present in source task text or approved facts.\n\n"
            "Feedback quality policy:\n"
            "- When rejecting, each feedback item must name the exact problematic phrase and include a minimal concrete rewrite target.\n"
            "- Avoid generic notes like 'preserve tone better'; make the redraft instruction specific enough for a second pass to succeed.\n\n"
            f"{mode_block}"
            f"{mode_rules}\n"
            "Validation inputs:\n"
            "<task>\n"
            f"{user_task}\n"
            "</task>\n\n"
            "<approved_facts>\n"
            f"{facts_block}\n"
            "</approved_facts>\n\n"
            "<candidate_draft>\n"
            f"{draft}\n"
            "</candidate_draft>"
        )

    @staticmethod
    def _detect_contract_violation(raw: str) -> str | None:
        stripped = raw.lstrip()
        if stripped.startswith("JT Feedback:") or stripped.startswith("JT Rewrite:"):
            return (
                "Reviewer contract violation: reviewer emitted JT commenter prose "
                "('JT Feedback:' / 'JT Rewrite:') instead of required JSON."
            )
        return None

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            candidate = ReviewerAgent._extract_json_object(raw)
            if candidate is not None:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
            return {
                "overall_assessment": "Failed to parse reviewer output into required JSON contract.",
                "missing_content": [],
                "unsupported_claims": [],
                "contradictions_or_logic_problems": [],
                "format_or_structure_issues": ["Failed to parse reviewer output"],
                "recommended_next_action": "reject",
                "_parse_failed": True,
            }

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        def _as_str(value: object, fallback: str) -> str:
            return value if isinstance(value, str) else fallback

        def _as_list_of_str(key: str) -> list[str]:
            value = data.get(key)
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return value
            return []

        recommended_next_action = data.get("recommended_next_action")
        if recommended_next_action not in {"approve", "revise", "reject"}:
            recommended_next_action = "revise"

        normalized = ReviewerAgent._default_findings(
            overall_assessment=_as_str(
                data.get("overall_assessment"),
                "Reviewer completed QC validation with normalized defaults.",
            ),
            missing_content=_as_list_of_str("missing_content"),
            unsupported_claims=_as_list_of_str("unsupported_claims"),
            contradictions_or_logic_problems=_as_list_of_str("contradictions_or_logic_problems"),
            format_or_structure_issues=_as_list_of_str("format_or_structure_issues"),
            recommended_next_action=recommended_next_action,
        )

        has_any_issues = any(
            normalized[key]
            for key in (
                "missing_content",
                "unsupported_claims",
                "contradictions_or_logic_problems",
                "format_or_structure_issues",
            )
        )
        if normalized["recommended_next_action"] == "approve" and has_any_issues:
            normalized["recommended_next_action"] = "revise"
        if normalized["recommended_next_action"] in {"revise", "reject"} and not has_any_issues:
            normalized["format_or_structure_issues"] = [
                "Validation note: normalized missing issue details to a default issue."
            ]

        return {**data, **normalized}

    @staticmethod
    def _extract_json_object(raw: str) -> str | None:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return match.group(0)
        return None

    @staticmethod
    def _validate_jt_commenter_draft_shape(draft: str) -> str | None:
        lines = [line.strip() for line in draft.splitlines() if line.strip()]
        if len(lines) != 2:
            return "JT commenter contract failure: draft must contain exactly two non-empty lines."
        if not lines[0].startswith("JT Feedback:"):
            return "JT commenter contract failure: line 1 must start with 'JT Feedback:'."
        if not lines[1].startswith("JT Rewrite:"):
            return "JT commenter contract failure: line 2 must start with 'JT Rewrite:'."
        return None

    @staticmethod
    def _default_findings(
        *,
        overall_assessment: str,
        missing_content: list[str] | None = None,
        unsupported_claims: list[str] | None = None,
        contradictions_or_logic_problems: list[str] | None = None,
        format_or_structure_issues: list[str] | None = None,
        recommended_next_action: Literal["approve", "revise", "reject"] = "revise",
    ) -> dict:
        return {
            "overall_assessment": overall_assessment,
            "missing_content": missing_content or [],
            "unsupported_claims": unsupported_claims or [],
            "contradictions_or_logic_problems": contradictions_or_logic_problems or [],
            "format_or_structure_issues": format_or_structure_issues or [],
            "recommended_next_action": recommended_next_action,
        }

    @staticmethod
    def _build_feedback(findings: dict) -> list[str]:
        feedback: list[str] = []
        category_labels = {
            "missing_content": "Missing content",
            "unsupported_claims": "Unsupported claim",
            "contradictions_or_logic_problems": "Logic problem",
            "format_or_structure_issues": "Format/structure issue",
        }
        for key, label in category_labels.items():
            for item in findings.get(key, []):
                feedback.append(f"{label}: {item}")
        if not feedback:
            action = findings.get("recommended_next_action", "revise")
            if action == "approve":
                feedback.append("Reviewer approved with no blocking issues.")
            else:
                feedback.append("Reviewer requested revisions with normalized default issue details.")
        return feedback
