from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents.chief_of_staff import ChiefOfStaffAgent
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.writer import WriterAgent
from app.state import SharedState


def build_graph(
    chief_of_staff: ChiefOfStaffAgent,
    researcher: ResearcherAgent,
    reviewer: ReviewerAgent,
    writer: WriterAgent,
):
    graph_builder = StateGraph(SharedState)

    def chief_node(state: SharedState) -> SharedState:
        return chief_of_staff.run(state)

    def researcher_node(state: SharedState) -> SharedState:
        return researcher.run(state)

    def writer_node(state: SharedState) -> SharedState:
        return writer.run(state)

    def reviewer_node(state: SharedState) -> SharedState:
        return reviewer.run(state)

    def human_review_node(state: SharedState) -> SharedState:
        draft = state.get("draft", "")
        review_feedback = state.get("review_feedback", [])
        review_approved = state.get("review_approved", False)
        print("\n=== Draft for human review ===\n")
        print(draft)
        print("\n=============================\n")
        print(f"Reviewer verdict: {'approved' if review_approved else 'needs_revision'}")
        if review_feedback:
            print("Reviewer feedback:")
            for item in review_feedback:
                print(f"- {item}")
            print()

        try:
            approved = input("Approve final output? [y/N]: ").strip().lower() == "y"
        except (EOFError, KeyboardInterrupt):
            return {
                **state,
                "final_output": "Finalization interrupted before approval.",
                "status": "stopped_by_human",
            }
        if not approved:
            try:
                notes = input("Optional revision notes for Writer (or press Enter to keep as-is): ").strip()
            except (EOFError, KeyboardInterrupt):
                return {
                    **state,
                    "final_output": "Finalization interrupted before approval.",
                    "status": "stopped_by_human",
                }
            if notes:
                revised_state = {
                    **state,
                    "approved_facts": [
                        *state.get("approved_facts", []),
                        f"Human reviewer note: {notes}",
                    ],
                    "status": "needs_redraft",
                }
                return writer.run(revised_state)

            return {
                **state,
                "final_output": "Finalization declined by human reviewer.",
                "status": "stopped_by_human",
            }

        return {
            **state,
            "final_output": draft,
            "status": "finalized",
        }

    def route_after_chief(state: SharedState) -> str:
        return "researcher" if state.get("route") == "research" else "writer"

    graph_builder.add_node("chief_of_staff", chief_node)
    graph_builder.add_node("researcher", researcher_node)
    graph_builder.add_node("writer", writer_node)
    graph_builder.add_node("reviewer", reviewer_node)
    graph_builder.add_node("human_review", human_review_node)

    graph_builder.add_edge(START, "chief_of_staff")
    graph_builder.add_conditional_edges(
        "chief_of_staff",
        route_after_chief,
        {
            "researcher": "researcher",
            "writer": "writer",
        },
    )
    graph_builder.add_edge("researcher", "writer")
    graph_builder.add_edge("writer", "reviewer")
    graph_builder.add_edge("reviewer", "human_review")
    graph_builder.add_edge("human_review", END)

    return graph_builder.compile()
