from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from app.state import SharedState, get_canonical_jt_requested
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "reviewer.md"


class ReviewerAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        user_task = state["user_task"]
        evaluation_draft = self._select_evaluation_draft(state)
        approved_facts = self._grounding_facts_for_review(
            user_task=user_task,
            approved_facts=state.get("approved_facts", []),
        )
        facts_block = "\n".join(f"- {fact}" for fact in approved_facts) or "- (none provided)"
        work_order = state.get("work_order", {})
        success_criteria = "\n".join(f"- {item}" for item in work_order.get("success_criteria", []))
        open_questions = "\n".join(f"- {item}" for item in work_order.get("open_questions", []))

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=self._build_reviewer_user_prompt(
                user_task=user_task,
                work_order_objective=work_order.get("objective", ""),
                work_order_deliverable_type=work_order.get("deliverable_type", ""),
                work_order_success_criteria=success_criteria or "- (none provided)",
                work_order_open_questions=open_questions or "- (none provided)",
                facts_block=facts_block,
                draft=evaluation_draft,
                using_jt_rewrite=bool(self._is_jt_requested(state) and state.get("jt_rewrite")),
            ),
        )

        parsed = self._safe_parse(raw)
        data = self._normalize_output(parsed)
        data = self._enforce_core_fact_violations(
            findings=data,
            user_task=user_task,
            work_order=work_order if isinstance(work_order, dict) else {},
            approved_facts=approved_facts,
            draft=evaluation_draft,
        )
        data = self._enforce_constrained_rewrite_contract(
            findings=data,
            user_task=user_task,
            approved_facts=approved_facts,
            draft=evaluation_draft,
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
            "reviewer_evaluated_draft": evaluation_draft,
            "reviewer_parse_failed": parse_failed,
            "reviewer_parse_error_raw": raw if parse_failed else "",
            "status": "reviewer_parse_failed" if parse_failed else "reviewed",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "reviewer_raw": raw,
                "reviewer_parse_failed": parse_failed,
                "reviewer_outputs": reviewer_history,
                "reviewer_evaluated_draft": evaluation_draft,
            },
        }

    @staticmethod
    def _grounding_facts_for_review(user_task: str, approved_facts: list[str]) -> list[str]:
        facts = [item for item in approved_facts if isinstance(item, str) and item.strip()]
        if not ReviewerAgent._detect_no_invention_constraints(user_task):
            return facts

        source_text = ReviewerAgent._extract_primary_source_text(user_task)
        if not source_text:
            return facts

        source_fact = f"Source text grounding (verbatim): {source_text}"
        if any(ReviewerAgent._normalize_text(item) == ReviewerAgent._normalize_text(source_fact) for item in facts):
            return facts
        return [*facts, source_fact]

    @staticmethod
    def _select_evaluation_draft(state: SharedState) -> str:
        jt_requested = ReviewerAgent._is_jt_requested(state)
        if jt_requested and state.get("jt_rewrite"):
            return state.get("jt_rewrite", "")
        return state.get("draft", "")

    @staticmethod
    def _is_jt_requested(state: SharedState) -> bool:
        return get_canonical_jt_requested(state)

    @staticmethod
    def _build_reviewer_user_prompt(
        user_task: str,
        work_order_objective: str,
        work_order_deliverable_type: str,
        work_order_success_criteria: str,
        work_order_open_questions: str,
        facts_block: str,
        draft: str,
        using_jt_rewrite: bool,
    ) -> str:
        artifact_label = "jt_rewrite" if using_jt_rewrite else "writer_draft"
        return (
            "Reviewer validator task:\n"
            "You are validating a candidate draft artifact against the task contract.\n"
            "You are a quality-control reviewer, not a rewriting stage.\n"
            "Identify issues and recommend a next action. Do not rewrite the draft.\n"
            "Return ONLY valid JSON (no markdown fences, no prose before or after) with keys:\n"
            "- overall_assessment (short string)\n"
            "- missing_content (array of short strings)\n"
            "- unsupported_claims (array of short strings)\n"
            "- contradictions_or_logic_problems (array of short strings)\n"
            "- format_or_structure_issues (array of short strings)\n"
            "- recommended_next_action (one of: approve, revise, reject)\n\n"
            "Feedback quality policy:\n"
            "- When rejecting, each feedback item must name the exact problematic phrase and include a minimal concrete rewrite target.\n"
            "- Avoid generic notes like 'preserve tone better'; make redraft instructions specific enough for a second pass to succeed.\n\n"
            f"Artifact type under review: {artifact_label}\n\n"
            "Validation inputs:\n"
            "<task>\n"
            f"{user_task}\n"
            "</task>\n\n"
            "<work_order>\n"
            f"objective: {work_order_objective}\n"
            f"deliverable_type: {work_order_deliverable_type}\n"
            "success_criteria:\n"
            f"{work_order_success_criteria}\n"
            "open_questions:\n"
            f"{work_order_open_questions}\n"
            "</work_order>\n\n"
            "<approved_facts>\n"
            f"{facts_block}\n"
            "</approved_facts>\n\n"
            "<candidate_draft>\n"
            f"{draft}\n"
            "</candidate_draft>"
        )

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
    def _enforce_core_fact_violations(
        findings: dict,
        user_task: str,
        work_order: dict,
        approved_facts: list[str],
        draft: str,
    ) -> dict:
        normalized = {**findings}
        unsupported = list(normalized.get("unsupported_claims", []))
        contradictions = list(normalized.get("contradictions_or_logic_problems", []))
        missing = list(normalized.get("missing_content", []))
        format_issues = list(normalized.get("format_or_structure_issues", []))

        policy = ReviewerAgent._extract_grounding_policy(
            user_task=user_task,
            work_order=work_order,
            approved_facts=approved_facts,
        )
        if not policy["is_closed_facts_mode"] and not policy["is_no_invention_mode"]:
            return normalized

        allowed_facts = policy["allowed_facts"]
        blocked_claims = policy["blocked_claims"]
        draft_normalized = ReviewerAgent._normalize_text(draft)

        blocked_hits: list[str] = []
        for claim in blocked_claims:
            claim_normalized = ReviewerAgent._normalize_text(claim)
            if claim_normalized and ReviewerAgent._appears_in_text(claim_normalized, draft_normalized):
                blocked_hits.append(claim)

        blocked_missing_items: list[str] = []
        filtered_missing: list[str] = []
        for item in missing:
            if ReviewerAgent._references_any_blocked_claim(item, blocked_claims):
                blocked_missing_items.append(item)
            else:
                filtered_missing.append(item)

        if blocked_hits:
            label = "Use-only-facts violation" if policy["is_closed_facts_mode"] else "No-invention constraint violation"
            unsupported.extend(
                [f"{label}: draft includes explicitly prohibited claim ('{item}'). Remove it." for item in blocked_hits]
            )
        if blocked_missing_items:
            label = (
                "Use-only-facts precedence"
                if policy["is_closed_facts_mode"]
                else "No-invention precedence"
            )
            unsupported.extend(
                [
                    (
                        f"{label}: blocked claim was incorrectly treated as required content ('{item}'). "
                        "Keep this out of missing_content and out of the draft."
                    )
                    for item in blocked_missing_items
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

        if blocked_hits and not any("contract was violated" in item.lower() for item in format_issues):
            contract_label = "Use-only-facts" if policy["is_closed_facts_mode"] else "No-new-facts"
            format_issues.append(
                f"{contract_label} contract was violated; remove unsupported claims before style or formatting polish."
            )

        normalized["missing_content"] = ReviewerAgent._dedupe_preserve_order(filtered_missing)
        normalized["unsupported_claims"] = ReviewerAgent._dedupe_preserve_order(unsupported)
        normalized["contradictions_or_logic_problems"] = ReviewerAgent._dedupe_preserve_order(contradictions)
        normalized["format_or_structure_issues"] = ReviewerAgent._dedupe_preserve_order(format_issues)

        if blocked_hits:
            policy_name = "closed-facts" if policy["is_closed_facts_mode"] else "no-new-facts"
            normalized["overall_assessment"] = f"Draft fails core grounding checks: unsupported claims violate the {policy_name} contract."
            normalized["recommended_next_action"] = "revise"
        return normalized

    @staticmethod
    def _extract_json_object(raw: str) -> str | None:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return match.group(0)
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
    def _extract_grounding_policy(user_task: str, work_order: dict, approved_facts: list[str]) -> dict:
        task = user_task or ""
        trigger_match = re.search(r"use only these facts\s*:\s*", task, flags=re.IGNORECASE)
        is_closed_facts_mode = trigger_match is not None
        source_text = ReviewerAgent._extract_primary_source_text(task)
        is_no_invention_mode = ReviewerAgent._detect_no_invention_constraints(task)

        allowed_facts = [item for item in approved_facts if isinstance(item, str) and item.strip()]
        if not allowed_facts and is_closed_facts_mode:
            post_trigger = task[trigger_match.end() :] if trigger_match else task
            allowlist_raw, _ = ReviewerAgent._extract_claim_scopes(post_trigger)
            allowed_facts = ReviewerAgent._split_claims(allowlist_raw)

        blocked_claims = ReviewerAgent._extract_explicitly_prohibited_claims(task)
        required_claims = ReviewerAgent._extract_required_claims_from_work_order(work_order)
        blocked_claims = [
            claim for claim in blocked_claims if not ReviewerAgent._claim_conflicts_with_required(claim, required_claims)
        ]

        if is_no_invention_mode:
            no_invention_scope = source_text or task
            blocked_claims.extend(ReviewerAgent._extract_explicitly_prohibited_claims(no_invention_scope))

        return {
            "is_closed_facts_mode": is_closed_facts_mode,
            "is_no_invention_mode": is_no_invention_mode,
            "allowed_facts": allowed_facts,
            "blocked_claims": ReviewerAgent._dedupe_preserve_order(blocked_claims),
        }

    @staticmethod
    def _enforce_constrained_rewrite_contract(
        findings: dict,
        user_task: str,
        approved_facts: list[str],
        draft: str,
    ) -> dict:
        if not ReviewerAgent._is_constrained_source_rewrite_task(user_task):
            return findings

        source_text = ReviewerAgent._extract_primary_source_text(user_task)
        if not source_text:
            return findings

        normalized = {**findings}
        unsupported = list(normalized.get("unsupported_claims", []))
        missing = list(normalized.get("missing_content", []))

        filtered_unsupported = [
            item for item in unsupported if not ReviewerAgent._unsupported_item_is_source_grounded(item, source_text)
        ]
        removed_source_grounded_issues = len(filtered_unsupported) != len(unsupported)

        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source_text))
        draft_numbers = set(re.findall(r"\d+(?:\.\d+)?", draft))
        approved_numbers = set(
            token
            for fact in approved_facts
            if isinstance(fact, str)
            for token in re.findall(r"\d+(?:\.\d+)?", fact)
        )

        dropped_numbers = sorted(source_numbers - draft_numbers)
        added_numbers = sorted(draft_numbers - source_numbers - approved_numbers)

        for value in dropped_numbers:
            missing.append(
                f"Constrained rewrite dropped source-provided specific '{value}'. Restore that source fact."
            )
        for value in added_numbers:
            filtered_unsupported.append(
                f"Constrained rewrite added new specific '{value}' not in the source draft. Remove it."
            )

        normalized["unsupported_claims"] = ReviewerAgent._dedupe_preserve_order(filtered_unsupported)
        normalized["missing_content"] = ReviewerAgent._dedupe_preserve_order(missing)

        has_any_issues = any(
            normalized[key]
            for key in (
                "missing_content",
                "unsupported_claims",
                "contradictions_or_logic_problems",
                "format_or_structure_issues",
            )
        )

        if removed_source_grounded_issues and not has_any_issues:
            normalized["overall_assessment"] = (
                "Constrained rewrite contract satisfied: rewrite stays within source-provided facts."
            )
            normalized["recommended_next_action"] = "approve"
        elif normalized.get("recommended_next_action") == "approve" and has_any_issues:
            normalized["recommended_next_action"] = "revise"

        return normalized

    @staticmethod
    def _extract_claim_scopes(raw_task_segment: str) -> tuple[str, list[str]]:
        directive_pattern = ReviewerAgent._directive_pattern()
        directive_match = directive_pattern.search(raw_task_segment)
        allowlist_raw = raw_task_segment[: directive_match.start()] if directive_match else raw_task_segment
        blocked_claims: list[str] = []
        for match in directive_pattern.finditer(raw_task_segment):
            segment_start = match.end()
            next_match = directive_pattern.search(raw_task_segment, segment_start)
            segment_end = next_match.start() if next_match else len(raw_task_segment)
            blocked_claims.extend(ReviewerAgent._split_claims(raw_task_segment[segment_start:segment_end]))
        return allowlist_raw, blocked_claims

    @staticmethod
    def _extract_directive_claims(raw_text: str) -> list[str]:
        _, blocked_claims = ReviewerAgent._extract_claim_scopes(raw_text)
        return blocked_claims

    @staticmethod
    def _extract_explicitly_prohibited_claims(raw_text: str) -> list[str]:
        prohibited: list[str] = []
        patterns = (
            r"\bdo not add\b\s*([^.;\n]+)",
            r"\bwithout adding\b\s*([^.;\n]+)",
            r"\bdo not include\b\s*([^.;\n]+)",
            r"\bwithout including\b\s*([^.;\n]+)",
            r"\bdo not invent\b\s*([^.;\n]+)",
            r"\bwithout inventing\b\s*([^.;\n]+)",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, raw_text, flags=re.IGNORECASE):
                clause = match.group(1).strip()
                if ReviewerAgent._is_generic_no_new_facts_clause(clause):
                    continue
                prohibited.extend(ReviewerAgent._split_claims(clause))
        return prohibited

    @staticmethod
    def _is_generic_no_new_facts_clause(clause: str) -> bool:
        prefix = clause.split(":", maxsplit=1)[0]
        normalized = ReviewerAgent._normalize_text(prefix)
        return bool(
            re.fullmatch(
                r"(?:any\s+)?new\s+facts?(?:\s+or\s+specifics?)?",
                normalized,
            )
        )

    @staticmethod
    def _extract_required_claims_from_work_order(work_order: dict) -> list[str]:
        if not isinstance(work_order, dict):
            return []
        required: list[str] = []
        for key in ("success_criteria", "open_questions"):
            value = work_order.get(key, [])
            if isinstance(value, list):
                required.extend([item for item in value if isinstance(item, str)])
        return required

    @staticmethod
    def _claim_conflicts_with_required(claim: str, required_claims: list[str]) -> bool:
        claim_text = ReviewerAgent._normalize_text(claim)
        if not claim_text:
            return False
        for required in required_claims:
            required_text = ReviewerAgent._normalize_text(required)
            if required_text and (
                ReviewerAgent._appears_in_text(claim_text, required_text)
                or ReviewerAgent._appears_in_text(required_text, claim_text)
            ):
                return True
        return False

    @staticmethod
    def _directive_pattern() -> re.Pattern[str]:
        return re.compile(
            r"\b(?:also\s+say|also\s+mention|mention|include|note|add|state|say)\b(?:\s+that)?\b",
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _detect_no_invention_constraints(user_task: str) -> bool:
        normalized = ReviewerAgent._normalize_text(user_task)
        phrase_patterns = (
            r"\bwithout adding (?:any )?new facts?(?: or specifics?)?\b",
            r"\bdo not add (?:any )?new facts?\b",
            r"\bdo not invent details?\b",
            r"\bwithout inventing details?\b",
            r"\buse only the information in the draft\b",
            r"\bpreserve only the provided information\b",
            r"\bpreserve meaning without inventing details\b",
            r"\bno new facts?\b",
        )
        return any(re.search(pattern, normalized) for pattern in phrase_patterns)

    @staticmethod
    def _extract_primary_source_text(user_task: str) -> str:
        quote_matches = re.findall(r'"([^"]{20,})"|\'([^\']{20,})\'', user_task)
        if not quote_matches:
            return ""
        candidates = [left or right for left, right in quote_matches]
        return max(candidates, key=lambda item: len(item.strip())).strip()

    @staticmethod
    def _is_constrained_source_rewrite_task(user_task: str) -> bool:
        if not ReviewerAgent._detect_no_invention_constraints(user_task):
            return False
        normalized = ReviewerAgent._normalize_text(user_task)
        has_rewrite_intent = bool(re.search(r"\brewrite\b", normalized))
        return has_rewrite_intent and bool(ReviewerAgent._extract_primary_source_text(user_task))

    @staticmethod
    def _unsupported_item_is_source_grounded(item: str, source_text: str) -> bool:
        normalized_item = ReviewerAgent._normalize_text(item)
        source_normalized = ReviewerAgent._normalize_text(source_text)
        if not normalized_item or not source_normalized:
            return False

        quoted = ReviewerAgent._extract_quoted_phrase(item)
        if quoted:
            quoted_normalized = ReviewerAgent._normalize_text(quoted)
            if quoted_normalized and ReviewerAgent._appears_in_text(quoted_normalized, source_normalized):
                return True

        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source_text))
        item_numbers = set(re.findall(r"\d+(?:\.\d+)?", item))
        if item_numbers and item_numbers.issubset(source_numbers):
            return True

        content_tokens = [
            token
            for token in normalized_item.split()
            if len(token) > 3 and token not in {"unsupported", "claim", "draft", "rewrite", "source", "provided"}
        ]
        if not content_tokens:
            return False
        token_overlap = sum(1 for token in content_tokens if token in source_normalized.split())
        return token_overlap >= max(2, len(content_tokens) // 2)

    @staticmethod
    def _references_any_blocked_claim(item: str, blocked_claims: list[str]) -> bool:
        item_text = ReviewerAgent._normalize_text(item)
        if not item_text:
            return False
        quoted = ReviewerAgent._extract_quoted_phrase(item)
        if quoted:
            quoted_text = ReviewerAgent._normalize_text(quoted)
            for claim in blocked_claims:
                claim_text = ReviewerAgent._normalize_text(claim)
                if claim_text and ReviewerAgent._appears_in_text(claim_text, quoted_text):
                    return True
        for claim in blocked_claims:
            claim_text = ReviewerAgent._normalize_text(claim)
            if claim_text and ReviewerAgent._appears_in_text(claim_text, item_text):
                return True
        return False

    @staticmethod
    def _extract_quoted_phrase(text: str) -> str:
        match = re.search(r"'([^']+)'|\"([^\"]+)\"", text)
        if not match:
            return ""
        return match.group(1) or match.group(2) or ""

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
        claims: list[str] = []
        for part in parts:
            claim = part.strip(" .")
            if not claim or ReviewerAgent._is_instructional_clause(claim):
                continue
            claims.append(claim)
        return claims

    @staticmethod
    def _is_instructional_clause(claim: str) -> bool:
        return bool(
            re.match(
                r"^(?:please\s+|return only|output only|respond with|rewrite|review)\b",
                claim.strip(),
                flags=re.IGNORECASE,
            )
        )

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
