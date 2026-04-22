from __future__ import annotations

import json
from pathlib import Path

from app.state import SharedState, normalize_project_memory
from tools.local_file_reader import build_evidence_bundle
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "researcher.md"


class ResearcherAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        work_order = state.get("work_order", {})
        project_memory = normalize_project_memory(state.get("project_memory"))
        evidence_bundle = self._load_structured_evidence(state)
        evidence_block = self._render_evidence_block(evidence_bundle)
        has_file_evidence = bool(evidence_bundle)
        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Extract facts and gaps for the Chief of Staff work order. Return strict JSON with keys: facts, gaps. "
                "Both must be arrays of short strings.\n"
                "When local file evidence is provided, use it as grounding context for both facts and gaps.\n\n"
                f"Current task:\n{state['user_task']}\n\n"
                f"Work order objective: {work_order.get('objective', '')}\n"
                f"Work order deliverable_type: {work_order.get('deliverable_type', '')}\n"
                f"Work order success_criteria: {work_order.get('success_criteria', [])}\n"
                f"Work order open_questions: {work_order.get('open_questions', [])}\n\n"
                f"Current evidence:\n"
                f"- Files read: {state.get('files_read', [])}\n"
                f"Local file evidence available: {has_file_evidence}\n"
                f"Structured local file evidence:\n{evidence_block}\n\n"
                "Continuity memory (context only; not default evidence):\n"
                f"- current_objective: {project_memory.get('current_objective', '')}\n"
                f"- active_deliverable_type: {project_memory.get('active_deliverable_type', '')}\n"
                f"- open_questions: {project_memory.get('open_questions', [])}\n"
                f"- latest_approved_output_present: {bool(project_memory.get('latest_approved_output', '').strip())}"
            ),
        )
        data = self._normalize_output(self._safe_parse(raw))
        facts = data["facts"]
        gaps = data["gaps"]

        return {
            **state,
            "research_facts": facts,
            "research_gaps": gaps,
            "approved_facts": facts,
            "status": "researched",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "researcher_raw": raw,
            },
        }

    @staticmethod
    def _load_structured_evidence(state: SharedState) -> list[dict[str, list[str] | str]]:
        model_metadata = state.get("model_metadata", {})
        if not isinstance(model_metadata, dict):
            return []
        file_contents = model_metadata.get("file_contents", {})
        if not isinstance(file_contents, dict):
            return []
        return build_evidence_bundle(file_contents)

    @staticmethod
    def _render_evidence_block(evidence_bundle: list[dict[str, list[str] | str]]) -> str:
        lines: list[str] = []
        for item in evidence_bundle:
            file_path = item.get("file_path", "")
            evidence_points = item.get("evidence_points", [])
            lines.append(f"- file: {file_path}")
            if isinstance(evidence_points, list):
                for point in evidence_points:
                    if isinstance(point, str):
                        lines.append(f"  - {point}")
        return "\n".join(lines) if lines else "- (no local file evidence loaded)"

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"facts": [], "gaps": ["Failed to parse researcher output"]}

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        notes: list[str] = []

        facts = data.get("facts")
        if not isinstance(facts, list) or not all(isinstance(item, str) for item in facts):
            facts = []
            notes.append("Validation note: normalized invalid facts to an empty list.")

        gaps = data.get("gaps")
        if not isinstance(gaps, list) or not all(isinstance(item, str) for item in gaps):
            gaps = []
            notes.append("Validation note: normalized invalid gaps to an empty list.")

        if notes:
            gaps = [*gaps, *notes]

        return {**data, "facts": facts, "gaps": gaps}
