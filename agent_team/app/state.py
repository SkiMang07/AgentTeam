from __future__ import annotations

from typing import Any, Literal, Mapping, NotRequired, TypedDict


class ModelMetadata(TypedDict, total=False):
    node_timings_ms: dict[str, list[float]]
    run_summary: dict[str, Any]
    execution_path: list[str]


class ChiefWorkOrder(TypedDict):
    objective: str
    deliverable_type: str
    success_criteria: list[str]
    research_needed: bool
    open_questions: list[str]
    jt_requested: bool


class ChiefFinalValidation(TypedDict):
    answers_request: bool
    matches_deliverable_type: bool
    reviewer_findings_addressed: bool
    jt_findings_addressed: bool
    obvious_missing_items: list[str]
    rationale: str
    recommended_action: Literal["human_review", "redraft"]


class ReviewerFindings(TypedDict):
    overall_assessment: str
    missing_content: list[str]
    unsupported_claims: list[str]
    contradictions_or_logic_problems: list[str]
    format_or_structure_issues: list[str]
    recommended_next_action: Literal["approve", "revise", "reject"]


class JTInput(TypedDict):
    writer_draft: str
    user_task: str
    approved_facts: list[str]
    jt_mode: str | None


class EvidenceItem(TypedDict):
    file_path: str
    evidence_points: list[str]


class ProjectMemory(TypedDict):
    current_objective: str
    active_deliverable_type: str
    open_questions: list[str]
    latest_draft: str
    latest_approved_output: str


class CurrentRunState(TypedDict):
    objective: str
    deliverable_type: str
    open_questions: list[str]
    latest_draft: str
    latest_approved_output: str


class SharedState(TypedDict):
    user_task: str
    dry_run: NotRequired[bool]
    debug: NotRequired[bool]
    work_order: NotRequired[ChiefWorkOrder]
    # Backward-compatibility field: canonical JT routing should resolve from work_order.jt_requested.
    jt_requested: NotRequired[bool]
    jt_mode: NotRequired[str | None]
    jt_input: NotRequired[JTInput]
    jt_feedback: NotRequired[list[str]]
    jt_rewrite: NotRequired[str | None]
    jt_findings: NotRequired[str | None]
    jt_review_count: NotRequired[int]
    route: NotRequired[Literal["research", "write_direct", "memory_lookup"]]
    memory_turn_type: NotRequired[Literal["project_work", "memory_inspection", "memory_transform"]]
    memory_lookup_requested: NotRequired[bool]
    memory_lookup_fields: NotRequired[list[Literal["latest_approved_output", "current_objective", "active_deliverable_type"]]]
    memory_lookup_result: NotRequired[str]
    research_facts: NotRequired[list[str]]
    research_gaps: NotRequired[list[str]]
    approved_facts: NotRequired[list[str]]
    files_requested: NotRequired[list[str]]
    files_read: NotRequired[list[str]]
    files_skipped: NotRequired[list[str]]
    skip_reasons: NotRequired[dict[str, str]]
    evidence_bundle: NotRequired[list[EvidenceItem]]
    file_read_summary: NotRequired[str]
    current_run: NotRequired[CurrentRunState]
    project_memory: NotRequired[ProjectMemory]
    draft: NotRequired[str]
    reviewer_findings: NotRequired[ReviewerFindings]
    review_feedback: NotRequired[list[str]]
    writer_guidance_notes: NotRequired[list[str]]
    reviewer_notes: NotRequired[list[str]]
    chief_notes: NotRequired[list[str]]
    human_notes: NotRequired[list[str]]
    revision_targets: NotRequired[list[str]]
    redraft_source_draft: NotRequired[str]
    review_approved: NotRequired[bool]
    reviewer_parse_failed: NotRequired[bool]
    reviewer_parse_error_raw: NotRequired[str]
    reviewer_evaluated_draft: NotRequired[str]
    auto_redraft_count: NotRequired[int]
    chief_redraft_count: NotRequired[int]
    critical_reviewer_blocking: NotRequired[bool]
    chief_final_next_step: NotRequired[Literal["writer", "human_review"]]
    chief_final_validation: NotRequired[ChiefFinalValidation]
    final_output: NotRequired[str]
    status: NotRequired[str]
    model_metadata: NotRequired[ModelMetadata | dict[str, Any]]


def get_canonical_jt_requested(state: Mapping[str, Any]) -> bool:
    work_order = state.get("work_order")
    if isinstance(work_order, Mapping):
        value = work_order.get("jt_requested")
        if isinstance(value, bool):
            return value
    return bool(state.get("jt_requested", False))


def empty_project_memory() -> ProjectMemory:
    return {
        "current_objective": "",
        "active_deliverable_type": "",
        "open_questions": [],
        "latest_draft": "",
        "latest_approved_output": "",
    }


def normalize_project_memory(raw: object) -> ProjectMemory:
    if not isinstance(raw, Mapping):
        return empty_project_memory()

    current_objective = raw.get("current_objective", "")
    active_deliverable_type = raw.get("active_deliverable_type", "")
    open_questions = raw.get("open_questions", [])
    latest_draft = raw.get("latest_draft", "")
    latest_approved_output = raw.get("latest_approved_output", "")

    return {
        "current_objective": current_objective.strip() if isinstance(current_objective, str) else "",
        "active_deliverable_type": (
            active_deliverable_type.strip() if isinstance(active_deliverable_type, str) else ""
        ),
        "open_questions": (
            [item.strip() for item in open_questions if isinstance(item, str) and item.strip()]
            if isinstance(open_questions, list)
            else []
        ),
        "latest_draft": latest_draft if isinstance(latest_draft, str) else "",
        "latest_approved_output": latest_approved_output if isinstance(latest_approved_output, str) else "",
    }


def get_memory_lookup_fields(
    task: str,
) -> list[Literal["latest_approved_output", "current_objective", "active_deliverable_type"]]:
    if not isinstance(task, str):
        return []
    normalized = " ".join(task.lower().split())

    wants_latest_approved = any(
        phrase in normalized
        for phrase in (
            "latest approved output",
            "latest_approved_output",
            "approved output currently stored",
            "latest stored output",
            "latest output from this session",
            "latest output in this session",
            "latest output",
            "stored output",
        )
    )
    wants_objective = any(
        phrase in normalized
        for phrase in (
            "current objective",
            "objective currently stored",
            "objective in project memory",
            "objective in session memory",
            "what objective",
            "stored objective",
        )
    )
    wants_deliverable_type = any(
        phrase in normalized
        for phrase in (
            "deliverable type",
            "active deliverable type",
            "deliverable currently stored",
            "deliverable in project memory",
            "deliverable in session memory",
            "stored deliverable type",
            "object type",
            "output type",
            "deliverable/object type",
        )
    )

    fields: list[Literal["latest_approved_output", "current_objective", "active_deliverable_type"]] = []
    if wants_latest_approved:
        fields.append("latest_approved_output")
    if wants_objective:
        fields.append("current_objective")
    if wants_deliverable_type:
        fields.append("active_deliverable_type")
    return fields
