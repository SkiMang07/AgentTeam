from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


class SharedState(TypedDict):
    user_task: str
    route: NotRequired[Literal["research", "write_direct"]]
    research_facts: NotRequired[list[str]]
    research_gaps: NotRequired[list[str]]
    approved_facts: NotRequired[list[str]]
    draft: NotRequired[str]
    final_output: NotRequired[str]
    status: NotRequired[str]
    model_metadata: NotRequired[dict[str, Any]]
