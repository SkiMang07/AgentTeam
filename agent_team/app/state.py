from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


class ModelMetadata(TypedDict, total=False):
    node_timings_ms: dict[str, list[float]]
    run_summary: dict[str, Any]


class SharedState(TypedDict):
    user_task: str
    dry_run: NotRequired[bool]
    jt_requested: NotRequired[bool]
    jt_mode: NotRequired[str | None]
    jt_findings: NotRequired[str | None]
    route: NotRequired[Literal["research", "write_direct"]]
    research_facts: NotRequired[list[str]]
    research_gaps: NotRequired[list[str]]
    approved_facts: NotRequired[list[str]]
    draft: NotRequired[str]
    review_feedback: NotRequired[list[str]]
    review_approved: NotRequired[bool]
    auto_redraft_count: NotRequired[int]
    chief_redraft_count: NotRequired[int]
    chief_final_next_step: NotRequired[Literal["writer", "human_review"]]
    final_output: NotRequired[str]
    status: NotRequired[str]
    model_metadata: NotRequired[ModelMetadata | dict[str, Any]]
