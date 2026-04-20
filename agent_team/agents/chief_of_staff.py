from __future__ import annotations

import json
import re
from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "chief_of_staff.md"


class ChiefOfStaffAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        user_task = state["user_task"]
        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Classify and route this task. Return strict JSON with keys: "
                "route, rationale, jt_requested, jt_mode. "
                "route must be 'research' or 'write_direct'. "
                "jt_requested must be true only when explicitly requested in the task text.\n\n"
                f"Task:\n{user_task}"
            ),
        )
        data = self._normalize_output(self._safe_parse(raw))
        route = data["route"]
        return {
            **state,
            "route": route,
            "jt_requested": data["jt_requested"],
            "jt_mode": data["jt_mode"],
            "status": "routed",
            "model_metadata": {"chief_of_staff_raw": raw},
        }

    def final_pass(self, state: SharedState) -> SharedState:
        review_feedback = state.get("review_feedback", [])
        review_block = "\n".join(f"- {item}" for item in review_feedback) or "- (none)"
        jt_findings = state.get("jt_findings")
        jt_block = jt_findings if jt_findings else "(JT not requested or no findings)"

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Run final Chief of Staff pass before human review. "
                "Return strict JSON with keys: next_step, rationale, instructions. "
                "next_step must be 'human_review' or 'redraft'. "
                "Use 'redraft' only when the draft should be revised before human review.\n\n"
                f"Draft:\n{state.get('draft', '')}\n\n"
                f"Reviewer findings:\n{review_block}\n\n"
                f"JT findings:\n{jt_block}"
            ),
        )
        data = self._normalize_final_output(self._safe_parse(raw))
        current_notes = state.get("approved_facts", [])
        chief_notes = data.get("instructions", "")
        should_redraft = (
            data["next_step"] == "redraft"
            and state.get("chief_redraft_count", 0) < 1
        )

        if should_redraft and chief_notes:
            current_notes = [*current_notes, f"Chief final pass note: {chief_notes}"]

        return {
            **state,
            "approved_facts": current_notes,
            "chief_final_next_step": "writer" if should_redraft else "human_review",
            "chief_redraft_count": state.get("chief_redraft_count", 0) + (1 if should_redraft else 0),
            "status": "chief_finalized",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "chief_of_staff_final_raw": raw,
            },
        }

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            candidate = ChiefOfStaffAgent._extract_json_object(raw)
            if candidate is not None:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
            return {"route": "research", "rationale": "fallback due to parse error", "jt_requested": False, "jt_mode": None}

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        route = data.get("route")
        if route not in {"research", "write_direct"}:
            route = "research"
        jt_requested = data.get("jt_requested")
        if not isinstance(jt_requested, bool):
            jt_requested = False

        jt_mode = data.get("jt_mode")
        if jt_mode is not None and not isinstance(jt_mode, str):
            jt_mode = None

        return {
            **data,
            "route": route,
            "jt_requested": jt_requested,
            "jt_mode": jt_mode,
        }

    @staticmethod
    def _normalize_final_output(data: dict) -> dict:
        next_step = data.get("next_step")
        if next_step not in {"human_review", "redraft"}:
            next_step = "human_review"

        instructions = data.get("instructions")
        if not isinstance(instructions, str):
            instructions = ""

        return {
            **data,
            "next_step": next_step,
            "instructions": instructions,
        }

    @staticmethod
    def _extract_json_object(raw: str) -> str | None:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return match.group(0)
        return None
