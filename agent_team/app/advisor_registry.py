from __future__ import annotations

from typing import TypedDict


class AdvisorProfile(TypedDict):
    id: str
    name: str
    domain: str
    when_to_use: str
    when_not_to_use: str
    expected_input_needs: str
    example_triggers: list[str]
    anti_triggers: list[str]


ADVISOR_ROSTER: list[AdvisorProfile] = [
    {
        "id": "strategy_systems",
        "name": "Strategy & Systems",
        "domain": (
            "Strategic framing of decisions, tradeoffs, and system-level problems. "
            "Covers portfolio prioritization, operating model design, sequencing choices, "
            "structural diagnostics, and reasoning about feedback loops, leverage points, "
            "and the underlying system producing an outcome."
        ),
        "when_to_use": (
            "Use for prioritization, portfolio choices, sequencing, operating model, "
            "and tradeoff framing."
        ),
        "when_not_to_use": (
            "Skip for simple rewrites, grammar polish, narrow implementation-only code tasks, "
            "people/team dynamics questions, or habit and mindset work."
        ),
        "expected_input_needs": "Clear objective, constraints, and the key decision or tradeoff.",
        "example_triggers": [
            "How should I prioritize three competing product bets given limited engineering capacity?",
            "We're building for two customer segments simultaneously — is that a mistake?",
            "What is the right operating model as we scale from 10 to 50 people?",
            "I have to choose between three strategic directions — how do I frame the tradeoffs?",
            "Our growth is slowing and I'm not sure if it's a strategy problem or an execution problem.",
        ],
        "anti_triggers": [
            "Rewrite this memo to be clearer and more direct. (communication task, not strategy)",
            "How do I give better feedback to a direct report who's struggling? (leadership/culture)",
            "I want to build a daily planning habit that sticks. (growth/mindset)",
            "What's the best way to launch this feature next sprint? (execution, not strategy framing)",
        ],
    },
    {
        "id": "leadership_culture",
        "name": "Leadership & Culture",
        "domain": (
            "People, team dynamics, and organizational health. Covers manager effectiveness, "
            "team trust and accountability, cross-team friction, psychological safety, "
            "feedback culture, org design for human performance, and leadership identity. "
            "Also covers the transition from individual contributor to manager."
        ),
        "when_to_use": (
            "Use for team alignment, ownership, accountability, cross-team friction, "
            "and manager communication."
        ),
        "when_not_to_use": (
            "Skip when no people or process leadership dimension is present — "
            "pure strategy, messaging, habit, or execution planning tasks don't need this advisor."
        ),
        "expected_input_needs": "Team context, stakeholders, and known collaboration risks.",
        "example_triggers": [
            "Two of my engineers aren't getting along and it's slowing the whole team down.",
            "I need to give a direct report critical feedback but I keep softening it.",
            "My team says they're aligned but then doesn't follow through — what's going on?",
            "I'm moving from IC to manager for the first time. What do I need to change?",
            "There's real tension between my team and the product team. How do I address it?",
        ],
        "anti_triggers": [
            "Help me prioritize our three strategic bets for next year. (strategy, not people)",
            "Draft a compelling email to our customer segment. (communication/influence)",
            "I'm trying to build a better morning routine. (growth/mindset)",
            "We need to ship this feature — what's the execution plan? (entrepreneur/execution)",
        ],
    },
    {
        "id": "communication_influence",
        "name": "Communication & Influence",
        "domain": (
            "Messaging, narrative design, persuasion, and stakeholder influence. "
            "Covers communication strategy for specific audiences, change communication, "
            "how to frame ideas so they spread or land, negotiation dynamics, "
            "and the structure of compelling written or verbal communication."
        ),
        "when_to_use": (
            "Use for messaging, stakeholder persuasion, narrative clarity, "
            "and change communication."
        ),
        "when_not_to_use": (
            "Skip when the task is purely analytical or implementation planning "
            "with no messaging or audience-facing objective. "
            "Also skip for simple grammar/proofreading requests."
        ),
        "expected_input_needs": (
            "Audience, channel, intended action, and any sensitive framing constraints."
        ),
        "example_triggers": [
            "I need to pitch a strategic shift to an executive team that is skeptical.",
            "How do I frame a difficult message to my team about a direction change?",
            "We're announcing a reorg — help me think through how to communicate it.",
            "I want this proposal to land with the board. How should it be structured?",
            "I'm about to go into a difficult negotiation. How do I prepare?",
        ],
        "anti_triggers": [
            "What is the right sequencing strategy for our product roadmap? (strategy/systems)",
            "My team has trust issues — how do I rebuild it? (leadership/culture)",
            "I want to stop procrastinating on hard decisions. (growth/mindset)",
            "What are the implementation steps to ship this feature? (entrepreneur/execution)",
        ],
    },
    {
        "id": "growth_mindset",
        "name": "Growth & Mindset",
        "domain": (
            "Personal growth, behavior design, identity, and cognitive reframing. "
            "Covers habit formation and breaking, identity-based change, "
            "values clarification, learning loops, mindset shifts under pressure, "
            "and the personal operating system of a high-performer. "
            "Relevant when the obstacle is internal, not structural."
        ),
        "when_to_use": (
            "Use for habits, behavior change, learning loops, "
            "and personal or team mindset reframes."
        ),
        "when_not_to_use": (
            "Skip when tactical execution details, structural decisions, "
            "or stakeholder communication matter more than internal behavior or mindset change."
        ),
        "expected_input_needs": (
            "Current behaviors, friction points, and the desired sustained outcome."
        ),
        "example_triggers": [
            "I keep saying I'll do deep work in the mornings but never follow through.",
            "I'm feeling stuck and I'm not sure if I'm working on the right things.",
            "I want to build a feedback habit but it always falls apart after two weeks.",
            "I know what I should do but I keep defaulting to what's comfortable.",
            "I need to rethink my relationship with failure — I'm too risk-averse.",
        ],
        "anti_triggers": [
            "How do I structure the strategy for our next funding round? (strategy/systems)",
            "My team is losing trust in leadership — what do I do? (leadership/culture)",
            "I need to write a compelling narrative for our investors. (communication/influence)",
            "What's the launch plan for this product? (entrepreneur/execution)",
        ],
    },
    {
        "id": "entrepreneur_execution",
        "name": "Entrepreneur & Execution",
        "domain": (
            "Practical execution: how to actually ship something, make hard founder-level calls, "
            "sequence work under constraints, manage launch risk, "
            "and build the operating cadence that turns strategy into delivered outcomes. "
            "Covers go-to-market mechanics, resource allocation, build/buy/partner decisions, "
            "and the wartime vs. peacetime operator distinction."
        ),
        "when_to_use": (
            "Use for execution plans, launch risk, operating cadence, "
            "and practical go-to-market constraints."
        ),
        "when_not_to_use": (
            "Skip for abstract brainstorming with no delivery requirement, "
            "or for pure strategy framing that isn't yet at the execution stage."
        ),
        "expected_input_needs": (
            "Scope, timeline pressure, resourcing assumptions, and delivery constraints."
        ),
        "example_triggers": [
            "We're two weeks from launch and I need to decide what to cut.",
            "What's the right sequence to ship the MVP without getting bogged down?",
            "I'm trying to decide whether to build this internally or use a vendor.",
            "We've been in planning mode for too long — how do we move to execution?",
            "What's the operating cadence I need to hit our quarterly delivery targets?",
        ],
        "anti_triggers": [
            "Should we be in this market at all? (strategy/systems — the question is before execution)",
            "My engineering lead and product lead aren't aligned. (leadership/culture)",
            "How do I write a memo that will get leadership buy-in? (communication/influence)",
            "I need to rewire how I think about risk. (growth/mindset)",
        ],
    },
]


ADVISOR_IDS: tuple[str, ...] = tuple(item["id"] for item in ADVISOR_ROSTER)
