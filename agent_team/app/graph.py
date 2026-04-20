from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents.chief_of_staff import ChiefOfStaffAgent
from agents.researcher import ResearcherAgent
from agents.writer import WriterAgent
from app.state import SharedState


def build_graph(
    chief_of_staff: ChiefOfStaffAgent,
    researcher: ResearcherAgent,
    writer: WriterAgent,
):
    graph_builder = StateGraph(SharedState)

    def chief_node(state: SharedState) -> SharedState:
        return chief_of_staff.run(state)

    def researcher_node(state: SharedState) -> SharedState:
        return researcher.run(state)

    def writer_node(state: SharedState) -> SharedState:
        return writer.run(state)

    def human_review_node(state: SharedState) -> SharedState:
        draft = state.get("draft", "")
        print("\n=== Draft for human review ===\n")
        print(draft)
        print("\n=============================\n")

        approved = input("Approve final output? [y/N]: ").strip().lower() == "y"
        if not approved:
            notes = input("Optional revision notes for Writer (or press Enter to keep as-is): ").strip()
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
    graph_builder.add_edge("writer", "human_review")
    graph_builder.add_edge("human_review", END)

    return graph_builder.compile()
