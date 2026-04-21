from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


class ModelMetadata(TypedDict, total=False):
    node_timings_ms: dict[str, list[float]]
    run_summary: dict[str, Any]
    execution_path: list[str]


class ChiefFinalValidation(TypedDict):
    answers_request: bool
    matches_deliverable_type: bool
    reviewer_findings_addressed: bool
    jt_findings_addressed: bool
    obvious_missing_items: list[str]
    rationale: str
    recommended_action: Literal["human_review", "redraft"]


class SharedState(TypedDict):
    user_task: str
    dry_run: NotRequired[bool]
    debug: NotRequired[bool]
    jt_requested: NotRequired[bool]
    jt_mode: NotRequired[str | None]
    jt_findings: NotRequired[str | None]
    jt_review_count: NotRequired[int]
    route: NotRequired[Literal["research", "write_direct"]]
    research_facts: NotRequired[list[str]]
    research_gaps: NotRequired[list[str]]
    approved_facts: NotRequired[list[str]]
    draft: NotRequired[str]
    review_feedback: NotRequired[list[str]]
    revision_targets: NotRequired[list[str]]
    redraft_source_draft: NotRequired[str]
    review_approved: NotRequired[bool]
    reviewer_parse_failed: NotRequired[bool]
    reviewer_parse_error_raw: NotRequired[str]
    auto_redraft_count: NotRequired[int]
    chief_redraft_count: NotRequired[int]
    chief_final_next_step: NotRequired[Literal["writer", "human_review"]]
    chief_final_validation: NotRequired[ChiefFinalValidation]
    final_output: NotRequired[str]
    status: NotRequired[str]
    model_metadata: NotRequired[ModelMetadata | dict[str, Any]]
