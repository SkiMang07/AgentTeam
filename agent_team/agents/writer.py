from __future__ import annotations

from pathlib import Path

from app.state import SharedState, normalize_project_memory
from tools.openai_client import ResponsesClient
from tools.voice_loader import VoiceLoader

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "writer.md"
ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "prompts" / "artifacts"

# Map deliverable_type values to their template filenames.
ARTIFACT_TEMPLATES: dict[str, str] = {
    "executive_brief": "executive_brief.md",
    "decision_memo": "decision_memo.md",
    "project_plan": "project_plan.md",
}


def _load_artifact_template(deliverable_type: str) -> str:
    """Return the artifact template text for deliverable_type, or empty string if none exists."""
    filename = ARTIFACT_TEMPLATES.get(deliverable_type.strip().lower() if deliverable_type else "")
    if not filename:
        return ""
    template_path = ARTIFACTS_DIR / filename
    if not template_path.exists():
        return ""
    return template_path.read_text(encoding="utf-8")


class WriterAgent:
    def __init__(
        self,
        client: ResponsesClient,
        voice_loader: VoiceLoader | None = None,
    ) -> None:
        self._client = client
        base_prompt = PROMPT_PATH.read_text(encoding="utf-8")

        # Append voice/style guide to the system prompt at init time so it is
        # baked into every model call without any runtime overhead.
        if voice_loader and voice_loader.available:
            voice_block = voice_loader.load_for_prompt()
            self._prompt = f"{voice_block}\n\n{base_prompt}" if voice_block else base_prompt
        else:
            self._prompt = base_prompt

    def run(self, state: SharedState) -> SharedState:
        if state.get("memory_lookup_requested", False):
            memory_lookup_result = state.get("memory_lookup_result", "")
            if not isinstance(memory_lookup_result, str) or not memory_lookup_result.strip():
                memory = normalize_project_memory(state.get("project_memory"))
                latest_approved_output = memory.get("latest_approved_output", "")
                memory_lookup_result = (
                    latest_approved_output
                    if isinstance(latest_approved_output, str) and latest_approved_output.strip()
                    else "No latest approved output is currently stored in session project memory."
                )
            prior_writer_history = state.get("model_metadata", {}).get("writer_outputs", [])
            writer_history = [*prior_writer_history, memory_lookup_result]
            return {
                **state,
                "draft": memory_lookup_result,
                "memory_lookup_result": memory_lookup_result,
                "status": "drafted",
                "model_metadata": {
                    **state.get("model_metadata", {}),
                    "writer_raw": memory_lookup_result,
                    "writer_outputs": writer_history,
                },
            }

        approved_facts = state.get("approved_facts", [])
        facts_block = "\n".join(f"- {fact}" for fact in approved_facts)
        guidance_notes = state.get("writer_guidance_notes", [])
        guidance_block = "\n".join(f"- {note}" for note in guidance_notes)
        work_order = state.get("work_order", {})
        project_memory = normalize_project_memory(state.get("project_memory"))
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
        required_structures = state.get("required_structures", [])
        required_structures_block = (
            "\n".join(
                f"- type: {item.get('type', '')}; label: {item.get('label', '')}; "
                f"items: {item.get('items', [])}; constraints: {item.get('constraints', [])}; "
                f"source_file: {item.get('source_file', '')}"
                for item in required_structures
                if isinstance(item, dict)
            )
            if isinstance(required_structures, list) and required_structures
            else "- (none)"
        )
        files_read = state.get("files_read", [])
        has_local_file_evidence = isinstance(files_read, list) and len(files_read) > 0

        # Raw file content — built by evidence_extract_node and stored in state so
        # it doesn't need to be re-read from model_metadata here.  file_contents is
        # stripped from model_metadata after evidence_extract to keep downstream
        # prompts lean; raw_file_context is the controlled, capped version for the writer.
        raw_files_block = state.get("raw_file_context", "") or ""

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

        deliverable_type = work_order.get("deliverable_type", "")
        artifact_template = _load_artifact_template(deliverable_type)
        artifact_block = (
            f"\n\nArtifact template (follow this structure exactly — it overrides default prose format for this deliverable type):\n{artifact_template}"
            if artifact_template
            else ""
        )

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Draft output for the Chief of Staff work order using only approved facts and structured evidence. "
                "If facts are missing, state assumptions and limits clearly. "
                "Do not introduce new factual specifics beyond the source task text and approved facts. "
                "Never claim you read files outside files_read. "
                "When files_read is non-empty, prioritize file-derived approved facts and evidence bundle details."
                " When local file evidence is present, preserve explicit names, labels, section headers,"
                " constraints, and workstream titles from that evidence as primary structure."
                " Treat required_structures as binding contracts. Preserve listed items and constraints exactly."
                " Do not rename provided workstreams or silently replace provided structures with generic frameworks."
                f"{priority_block}"
                f"{revision_target_block}\n\n"
                f"{redraft_source_block}\n\n"
                f"Current task:\n{state['user_task']}\n\n"
                f"Work order objective:\n{work_order.get('objective', '')}\n\n"
                f"Work order deliverable_type:\n{deliverable_type}\n\n"
                f"Work order success_criteria:\n{success_criteria if success_criteria else '- (none provided)'}\n\n"
                f"Work order open_questions:\n{open_questions if open_questions else '- (none provided)'}\n\n"
                f"Current evidence:\n"
                f"- Files read: {state.get('files_read', [])}\n"
                f"- Files skipped: {state.get('files_skipped', [])}\n"
                f"- Local file evidence present: {has_local_file_evidence}\n"
                f"Writer guidance notes (non-fact revision guidance):\n{guidance_block if guidance_block else '- (none provided)'}\n\n"
                f"Raw file content (treat as ground truth — use exact names, labels, and structures from these files):\n"
                f"{raw_files_block if raw_files_block else '- (no local files provided)'}\n\n"
                f"Structured evidence bundle:\n{evidence_block}\n\n"
                f"Required structures (binding contracts):\n{required_structures_block}\n\n"
                f"Approved facts:\n{facts_block if facts_block else '- (none provided)'}\n\n"
                "Continuity memory (context only unless the task explicitly asks to inspect/reuse it):\n"
                f"- current_objective: {project_memory.get('current_objective', '')}\n"
                f"- active_deliverable_type: {project_memory.get('active_deliverable_type', '')}\n"
                f"- open_questions: {project_memory.get('open_questions', [])}\n"
                f"- latest_approved_output: {project_memory.get('latest_approved_output', '')}"
                f"{artifact_block}"
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
