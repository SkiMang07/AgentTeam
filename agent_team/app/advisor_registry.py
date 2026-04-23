from __future__ import annotations

from typing import TypedDict


class AdvisorProfile(TypedDict):
    id: str
    name: str
    when_to_use: str
    when_not_to_use: str
    expected_input_needs: str


ADVISOR_ROSTER: list[AdvisorProfile] = [
    {
        "id": "strategy_systems",
        "name": "Strategy & Systems",
        "when_to_use": "Use for prioritization, portfolio choices, sequencing, operating model, and tradeoff framing.",
        "when_not_to_use": "Skip for simple rewrites, grammar polish, or narrow implementation-only code tasks.",
        "expected_input_needs": "Clear objective, constraints, and the key decision or tradeoff.",
    },
    {
        "id": "leadership_culture",
        "name": "Leadership & Culture",
        "when_to_use": "Use for team alignment, ownership, accountability, cross-team friction, and manager communication.",
        "when_not_to_use": "Skip when no people/process leadership dimension is present.",
        "expected_input_needs": "Team context, stakeholders, and known collaboration risks.",
    },
    {
        "id": "communication_influence",
        "name": "Communication & Influence",
        "when_to_use": "Use for messaging, stakeholder persuasion, narrative clarity, and change communication.",
        "when_not_to_use": "Skip when the task is purely analytical or implementation planning with no messaging objective.",
        "expected_input_needs": "Audience, channel, intended action, and any sensitive framing constraints.",
    },
    {
        "id": "growth_mindset",
        "name": "Growth & Mindset",
        "when_to_use": "Use for habits, behavior change, learning loops, and personal/team mindset reframes.",
        "when_not_to_use": "Skip when tactical execution details matter more than behavior or habit change.",
        "expected_input_needs": "Current behaviors, friction points, and the desired sustained outcome.",
    },
    {
        "id": "entrepreneur_execution",
        "name": "Entrepreneur & Execution",
        "when_to_use": "Use for execution plans, launch risk, operating cadence, and practical go-to-market constraints.",
        "when_not_to_use": "Skip for abstract brainstorming with no delivery requirement.",
        "expected_input_needs": "Scope, timeline pressure, resourcing assumptions, and delivery constraints.",
    },
]


ADVISOR_IDS: tuple[str, ...] = tuple(item["id"] for item in ADVISOR_ROSTER)
