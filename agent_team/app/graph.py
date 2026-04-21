from __future__ import annotations

from time import perf_counter

from langgraph.graph import END, START, StateGraph

from agents.chief_of_staff import ChiefOfStaffAgent
from agents.jt import JTAgent
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.writer import WriterAgent
from app.state import SharedState


def build_graph(
    chief_of_staff: ChiefOfStaffAgent,
    jt: JTAgent,
    researcher: ResearcherAgent,
    reviewer: ReviewerAgent,
    writer: WriterAgent,
):
    graph_builder = StateGraph(SharedState)
    max_auto_redrafts = 1

    def get_work_order_jt_requested(state: SharedState) -> bool:
        work_order = state.get("work_order")
        if isinstance(work_order, dict):
            value = work_order.get("jt_requested")
            if isinstance(value, bool):
                return value
        return bool(state.get("jt_requested", False))

    def timed_node(node_name: str, fn):
        def _wrapped(state: SharedState) -> SharedState:
            print(f"[flow] entering node: {node_name}")
            start = perf_counter()
            result_state = fn(state)
            elapsed_ms = (perf_counter() - start) * 1000

            prior_metadata = state.get("model_metadata", {})
            result_metadata = result_state.get("model_metadata", {})
            merged_metadata = {**prior_metadata, **result_metadata}
            execution_path = [*prior_metadata.get("execution_path", []), node_name]
            merged_metadata["execution_path"] = execution_path

            existing_timings = result_metadata.get(
                "node_timings_ms",
                prior_metadata.get("node_timings_ms", {}),
            )
            node_timings_ms = {key: [*values] for key, values in existing_timings.items()}
            node_timings_ms.setdefault(node_name, []).append(elapsed_ms)

            merged_metadata["node_timings_ms"] = node_timings_ms
            return {
                **result_state,
                "model_metadata": merged_metadata,
            }

        return _wrapped

    def chief_node(state: SharedState) -> SharedState:
        return chief_of_staff.run(state)

    def researcher_node(state: SharedState) -> SharedState:
        return researcher.run(state)

    def writer_node(state: SharedState) -> SharedState:
        return writer.run(state)

    def jt_node(state: SharedState) -> SharedState:
        jt_state = jt.run(state)
        return {
            **jt_state,
            "jt_review_count": state.get("jt_review_count", 0) + 1,
        }

    def reviewer_node(state: SharedState) -> SharedState:
        return reviewer.run(state)

    def chief_final_node(state: SharedState) -> SharedState:
        return chief_of_staff.final_pass(state)

    timed_chief_node = timed_node("chief_of_staff", chief_node)
    timed_researcher_node = timed_node("researcher", researcher_node)
    timed_writer_node = timed_node("writer", writer_node)
    timed_jt_node = timed_node("jt", jt_node)
    timed_reviewer_node = timed_node("reviewer", reviewer_node)
    timed_chief_final_node = timed_node("chief_of_staff_final", chief_final_node)

    def auto_redraft_prep_node(state: SharedState) -> SharedState:
        feedback = state.get("review_feedback", [])
        reviewer_findings = state.get("reviewer_findings", {})
        if not feedback and isinstance(reviewer_findings, dict):
            for key in (
                "unsupported_claims",
                "contradictions_or_logic_problems",
                "missing_content",
                "format_or_structure_issues",
            ):
                issues = reviewer_findings.get(key, [])
                if isinstance(issues, list):
                    feedback.extend([item for item in issues if isinstance(item, str)])

        revision_notes = [f"Reviewer note: {item}" for item in feedback]
        print("\nReviewer requested revisions. Triggering one automatic redraft before human review.\n")
        return {
            **state,
            "approved_facts": [*state.get("approved_facts", []), *revision_notes],
            "revision_targets": feedback,
            "redraft_source_draft": state.get("draft", ""),
            "auto_redraft_count": state.get("auto_redraft_count", 0) + 1,
            "status": "needs_redraft_auto",
        }

    def human_review_node(state: SharedState) -> SharedState:
        if state.get("dry_run"):
            print("\nDry-run mode: auto-approving at human review step.\n")
            return {
                **state,
                "final_output": state.get("draft", ""),
                "status": "finalized",
            }

        draft = state.get("draft", "")
        review_feedback = state.get("review_feedback", [])
        review_approved = state.get("review_approved", False)
        print("\n=== Draft for human review ===\n")
        print(draft)
        print("\n=============================\n")
        execution_path = state.get("model_metadata", {}).get("execution_path", [])
        if execution_path:
            print(f"Execution path: {' -> '.join(execution_path)}")
        print(f"jt_requested: {get_work_order_jt_requested(state)}")
        print(f"jt_mode: {state.get('jt_mode')}")
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
                print("\nApplying human revision notes and re-running Writer + QC flow.\n")
                redrafted_state = timed_writer_node(revised_state)
                post_writer = timed_jt_node(redrafted_state) if redrafted_state.get("jt_requested") else redrafted_state
                rereviewed_state = timed_reviewer_node(post_writer)
                return human_review_node(rereviewed_state)

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

    def reviewer_parse_failure_node(state: SharedState) -> SharedState:
        raw_output = str(state.get("reviewer_parse_error_raw", "") or "").strip()
        compact_raw_output = " ".join(raw_output.split())
        if len(compact_raw_output) > 220:
            compact_raw_output = f"{compact_raw_output[:217]}..."
        message = (
            "Reviewer parse failure: reviewer output was not valid JSON. "
            "Approval flow stopped before human review."
        )
        if compact_raw_output:
            message = f'{message} Raw reviewer output (compact): "{compact_raw_output}"'
        print(f"\n{message}\n")
        return {
            **state,
            "final_output": message,
            "status": "reviewer_parse_failed",
        }

    def route_after_chief(state: SharedState) -> str:
        work_order = state.get("work_order")
        if isinstance(work_order, dict) and isinstance(work_order.get("research_needed"), bool):
            return "researcher" if work_order["research_needed"] else "writer"
        return "researcher" if state.get("route") == "research" else "writer"

    def route_after_writer(state: SharedState) -> str:
        return "jt" if get_work_order_jt_requested(state) else "reviewer"

    def route_after_reviewer(state: SharedState) -> str:
        if state.get("reviewer_parse_failed", False):
            return "reviewer_parse_failure"

        reviewer_findings = state.get("reviewer_findings", {})
        recommended_next_action = (
            reviewer_findings.get("recommended_next_action")
            if isinstance(reviewer_findings, dict)
            else None
        )
        is_approved = recommended_next_action == "approve"
        has_feedback = bool(state.get("review_feedback")) or recommended_next_action in {"revise", "reject"}
        auto_redraft_count = state.get("auto_redraft_count", 0)

        if (not is_approved) and has_feedback and auto_redraft_count < max_auto_redrafts:
            return "auto_redraft_prep"
        return "chief_final"

    def route_after_chief_final(state: SharedState) -> str:
        if state.get("critical_reviewer_blocking", False):
            return "review_rejected_after_redraft"
        return state.get("chief_final_next_step", "human_review")

    def review_rejected_after_redraft_node(state: SharedState) -> SharedState:
        message = (
            "Reviewer found unresolved unsupported claims or core fact contradictions. "
            "Stopping before normal human review."
        )
        print(f"\n{message}\n")
        return {
            **state,
            "final_output": message,
            "status": "review_rejected_after_redraft",
        }

    graph_builder.add_node("chief_of_staff", timed_chief_node)
    graph_builder.add_node("researcher", timed_researcher_node)
    graph_builder.add_node("writer", timed_writer_node)
    graph_builder.add_node("jt", timed_jt_node)
    graph_builder.add_node("reviewer", timed_reviewer_node)
    graph_builder.add_node("chief_final", timed_chief_final_node)
    graph_builder.add_node("auto_redraft_prep", timed_node("auto_redraft_prep", auto_redraft_prep_node))
    graph_builder.add_node("human_review", timed_node("human_review", human_review_node))
    graph_builder.add_node("reviewer_parse_failure", timed_node("reviewer_parse_failure", reviewer_parse_failure_node))
    graph_builder.add_node(
        "review_rejected_after_redraft",
        timed_node("review_rejected_after_redraft", review_rejected_after_redraft_node),
    )

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
    graph_builder.add_conditional_edges(
        "writer",
        route_after_writer,
        {
            "jt": "jt",
            "reviewer": "reviewer",
        },
    )
    graph_builder.add_edge("jt", "reviewer")
    graph_builder.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "reviewer_parse_failure": "reviewer_parse_failure",
            "auto_redraft_prep": "auto_redraft_prep",
            "chief_final": "chief_final",
        },
    )
    graph_builder.add_edge("auto_redraft_prep", "writer")
    graph_builder.add_conditional_edges(
        "chief_final",
        route_after_chief_final,
        {
            "writer": "writer",
            "human_review": "human_review",
            "review_rejected_after_redraft": "review_rejected_after_redraft",
        },
    )
    graph_builder.add_edge("human_review", END)
    graph_builder.add_edge("reviewer_parse_failure", END)
    graph_builder.add_edge("review_rejected_after_redraft", END)

    return graph_builder.compile()
