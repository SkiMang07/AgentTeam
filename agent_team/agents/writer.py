from __future__ import annotations

from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "writer.md"


class WriterAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        approved_facts = state.get("approved_facts", [])
        facts_block = "\n".join(f"- {fact}" for fact in approved_facts)
        guidance_notes = state.get("writer_guidance_notes", [])
        guidance_block = "\n".join(f"- {note}" for note in guidance_notes)
        work_order = state.get("work_order", {})
        success_criteria = "\n".join(f"- {item}" for item in work_order.get("success_criteria", []))
        open_questions = "\n".join(f"- {item}" for item in work_order.get("open_questions", []))

        evidence_bundle = state.get("evidence_bundle", [])
        evidence_lines: list[str] = []
        if isinstance(evidence_bundle, list):
            for item in evidence_bundle:
                if not isinstance(item, dict):
                    continue
                file_path = item.get("file_path", "")
                evidence_points = item.get("evidence_points", [])
                evidence_lines.append(f"- file: {file_path}")
                if isinstance(evidence_points, list):
                    for point in evidence_points:
                        if isinstance(point, str):
                            evidence_lines.append(f"  - {point}")
        evidence_block = "\n".join(evidence_lines) if evidence_lines else "- (no local file evidence loaded)"

        revision_targets = state.get("revision_targets", [])
        prior_draft = state.get("redraft_source_draft", "")
        reviewer_findings = state.get("reviewer_findings", {})
        revision_target_block = ""
        priority_block = ""
        if isinstance(reviewer_findings, dict):
            unsupported = reviewer_findings.get("unsupported_claims", [])
            contradictions = reviewer_findings.get("contradictions_or_logic_problems", [])
            if (isinstance(unsupported, list) and unsupported) or (isinstance(contradictions, list) and contradictions):
                priority_block = (
                    "\n\nPriority redraft rule:\n"
                    "- First remove unsupported claims and resolve core fact contradictions.\n"
                    "- Only after grounding issues are fixed should you adjust style or format details.\n"
                )
        if revision_targets:
            bullets = "\n".join(f"- {item}" for item in revision_targets)
            revision_target_block = (
                "\n\nRevision targets from Reviewer (address each one directly):\n"
                f"{bullets}\n"
                "Make the smallest possible edits to satisfy these notes while preserving source meaning."
            )
        redraft_source_block = ""
        if revision_targets and prior_draft:
            redraft_source_block = (
                "\n\nCurrent draft to revise (do a surgical revision, not a full rewrite):\n"
                f"{prior_draft}"
            )

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Draft output for the Chief of Staff work order using only approved facts and structured evidence. "
                "If facts are missing, state assumptions and limits clearly. "
                "Do not introduce new factual specifics beyond the source task text and approved facts. "
                "Never claim you read files outside files_read. "
                "When files_read is non-empty, prioritize file-derived approved facts and evidence bundle details."
                f"{priority_block}"
                f"{revision_target_block}\n\n"
                f"{redraft_source_block}\n\n"
                f"Original task:\n{state['user_task']}\n\n"
                f"Work order objective:\n{work_order.get('objective', '')}\n\n"
                f"Work order deliverable_type:\n{work_order.get('deliverable_type', '')}\n\n"
                f"Work order success_criteria:\n{success_criteria if success_criteria else '- (none provided)'}\n\n"
                f"Work order open_questions:\n{open_questions if open_questions else '- (none provided)'}\n\n"
                f"Files read:\n{state.get('files_read', [])}\n"
                f"Files skipped:\n{state.get('files_skipped', [])}\n"
                f"Writer guidance notes (non-fact revision guidance):\n{guidance_block if guidance_block else '- (none provided)'}\n\n"
                f"Structured evidence bundle:\n{evidence_block}\n\n"
                f"Approved facts:\n{facts_block if facts_block else '- (none provided)'}"
            ),
        )

        prior_writer_history = state.get("model_metadata", {}).get("writer_outputs", [])
        writer_history = [*prior_writer_history, raw]

        return {
            **state,
            "draft": raw,
            "status": "drafted",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "writer_raw": raw,
                "writer_outputs": writer_history,
            },
        }
