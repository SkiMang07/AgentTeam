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
        data = self._enforce_core_fact_violations(
            findings=data,
            user_task=user_task,
            draft=draft,
        )
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
    def _enforce_core_fact_violations(findings: dict, user_task: str, draft: str) -> dict:
        normalized = {**findings}
        unsupported = list(normalized.get("unsupported_claims", []))
        contradictions = list(normalized.get("contradictions_or_logic_problems", []))
        format_issues = list(normalized.get("format_or_structure_issues", []))

        policy = ReviewerAgent._extract_closed_fact_policy(user_task)
        if not policy["is_closed_facts_mode"]:
            return normalized

        allowed_facts = policy["allowed_facts"]
        blocked_claims = policy["blocked_claims"]
        draft_normalized = ReviewerAgent._normalize_text(draft)

        blocked_hits: list[str] = []
        for claim in blocked_claims:
            claim_normalized = ReviewerAgent._normalize_text(claim)
            if claim_normalized and ReviewerAgent._appears_in_text(claim_normalized, draft_normalized):
                blocked_hits.append(claim)

        if blocked_hits:
            unsupported.extend(
                [
                    (
                        "Use-only-facts violation: draft includes blocked claim "
                        f"from task text ('{item}'). Remove it."
                    )
                    for item in blocked_hits
                ]
            )

        scope_unchanged_in_facts = any(
            "scope is unchanged" in ReviewerAgent._normalize_text(item)
            for item in allowed_facts
        )
        if scope_unchanged_in_facts and blocked_hits:
            contradictions.append(
                "Core fact contradiction: source says scope is unchanged, but draft adds new scope elements."
            )

        if blocked_hits and not any("use-only-facts" in item.lower() for item in format_issues):
            format_issues.append(
                "Use-only-facts contract was violated; remove unsupported claims before style or formatting polish."
            )

        normalized["unsupported_claims"] = ReviewerAgent._dedupe_preserve_order(unsupported)
        normalized["contradictions_or_logic_problems"] = ReviewerAgent._dedupe_preserve_order(contradictions)
        normalized["format_or_structure_issues"] = ReviewerAgent._dedupe_preserve_order(format_issues)

        if blocked_hits:
            normalized["overall_assessment"] = (
                "Draft fails core grounding checks: unsupported claims violate the closed facts contract."
            )
            normalized["recommended_next_action"] = "revise"
        return normalized

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
            "unsupported_claims": "Unsupported claim",
            "contradictions_or_logic_problems": "Logic problem",
            "missing_content": "Missing content",
            "format_or_structure_issues": "Format/structure issue",
        }
        has_core_grounding_violations = bool(
            findings.get("unsupported_claims") or findings.get("contradictions_or_logic_problems")
        )
        if has_core_grounding_violations:
            feedback.append(
                "Priority: remove unsupported claims and resolve core fact contradictions before any formatting edits."
            )
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

    @staticmethod
    def _extract_closed_fact_policy(user_task: str) -> dict:
        task = user_task or ""
        trigger_match = re.search(r"use only these facts\s*:\s*", task, flags=re.IGNORECASE)
        if not trigger_match:
            return {
                "is_closed_facts_mode": False,
                "allowed_facts": [],
                "blocked_claims": [],
            }

        post_trigger = task[trigger_match.end() :]
        directive_pattern = re.compile(
            r"\b(?:also\s+say|mention|include|note|add|state)\b(?:\s+that)?\b",
            flags=re.IGNORECASE,
        )
        directive_match = directive_pattern.search(post_trigger)
        allowlist_raw = post_trigger[: directive_match.start()] if directive_match else post_trigger
        allowed_facts = ReviewerAgent._split_claims(allowlist_raw)

        blocked_claims: list[str] = []
        for match in directive_pattern.finditer(post_trigger):
            segment_start = match.end()
            next_match = directive_pattern.search(post_trigger, segment_start)
            segment_end = next_match.start() if next_match else len(post_trigger)
            blocked_claims.extend(ReviewerAgent._split_claims(post_trigger[segment_start:segment_end]))

        return {
            "is_closed_facts_mode": True,
            "allowed_facts": allowed_facts,
            "blocked_claims": ReviewerAgent._dedupe_preserve_order(blocked_claims),
        }

    @staticmethod
    def _split_claims(raw: str) -> list[str]:
        cleaned = raw.strip().strip(".")
        if not cleaned:
            return []
        normalized = re.sub(r"\s+", " ", cleaned)
        normalized = re.split(
            r"\b(?:keep|make|ensure|format|write|draft)\b",
            normalized,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        parts = re.split(
            r";|,\s+and that\s+|,\s+that\s+|\band that\b|\.\s+|\s+\band\b\s+",
            normalized,
            flags=re.IGNORECASE,
        )
        return [part.strip(" .") for part in parts if part.strip(" .")]

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9\s]", " ", value.lower()).strip()

    @staticmethod
    def _appears_in_text(claim: str, draft: str) -> bool:
        if not claim or not draft:
            return False
        if claim in draft:
            return True

        claim_tokens = [token for token in claim.split() if len(token) > 2]
        if not claim_tokens:
            return False
        draft_tokens = set(draft.split())
        overlap = sum(1 for token in claim_tokens if token in draft_tokens)
        return overlap >= max(2, len(claim_tokens) // 2)

    @staticmethod
    def _dedupe_preserve_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            key = item.strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(key)
        return deduped
