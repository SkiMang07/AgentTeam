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
    route: NotRequired[Literal["research", "write_direct"]]
    research_facts: NotRequired[list[str]]
    research_gaps: NotRequired[list[str]]
    approved_facts: NotRequired[list[str]]
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
