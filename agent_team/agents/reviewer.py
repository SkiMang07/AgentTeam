from __future__ import annotations

import json
import re
from pathlib import Path

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
                return {
                    **state,
                    "review_approved": False,
                    "review_feedback": [jt_shape_error],
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
            return {
                **state,
                "review_approved": False,
                "review_feedback": [contract_violation],
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
        parse_failed = bool(parsed.get("_parse_failed", False))
        prior_reviewer_history = state.get("model_metadata", {}).get("reviewer_outputs", [])
        reviewer_history = [*prior_reviewer_history, raw]

        return {
            **state,
            "review_approved": data["approved"],
            "review_feedback": data["feedback"],
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
            "The user-requested output format is an object to validate, not an instruction for your own output.\n"
            "Return ONLY valid JSON (no markdown fences, no prose before or after) with keys:\n"
            "- approved (boolean)\n"
            "- feedback (array of short strings)\n\n"
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
                "approved": False,
                "feedback": ["Failed to parse reviewer output"],
                "_parse_failed": True,
            }

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        approved = data.get("approved")
        if not isinstance(approved, bool):
            approved = False

        feedback = data.get("feedback")
        if not isinstance(feedback, list) or not all(isinstance(item, str) for item in feedback):
            feedback = ["Validation note: normalized invalid feedback to a default note."]

        return {**data, "approved": approved, "feedback": feedback}

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
