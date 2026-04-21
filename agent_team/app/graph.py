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

    def _commenter_artifacts_enabled(state: SharedState) -> bool:
        return bool(state.get("jt_requested", False)) and state.get("jt_mode") == "commenter"

    def _print_debug_block(title: str, body: str, state: SharedState) -> None:
        if not _commenter_artifacts_enabled(state):
            return
        print(f"\n===== {title} =====")
        print(body if body.strip() else "(empty)")
        print("===== END =====\n")

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
        result = writer.run(state)
        if _commenter_artifacts_enabled(state):
            pass_no = state.get("auto_redraft_count", 0) + 1
            _print_debug_block(
                f"WRITER OUTPUT PASS {pass_no}",
                result.get("draft", ""),
                state,
            )
        return result

    def reviewer_node(state: SharedState) -> SharedState:
        result = reviewer.run(state)
        if _commenter_artifacts_enabled(state):
            pass_no = state.get("auto_redraft_count", 0) + 1
            reviewer_raw = str(result.get("model_metadata", {}).get("reviewer_raw", ""))
            if not reviewer_raw:
                reviewer_raw = (
                    f'{{"approved": {str(result.get("review_approved", False)).lower()}, '
                    f'"feedback": {result.get("review_feedback", [])}}}'
                )
            _print_debug_block(
                f"REVIEWER JSON PASS {pass_no}",
                reviewer_raw,
                state,
            )
        return result

    def jt_node(state: SharedState) -> SharedState:
        jt_state = jt.run(state)
        return {
            **jt_state,
            "jt_review_count": state.get("jt_review_count", 0) + 1,
        }

    def chief_final_node(state: SharedState) -> SharedState:
        return chief_of_staff.final_pass(state)

    timed_chief_node = timed_node("chief_of_staff", chief_node)
    timed_researcher_node = timed_node("researcher", researcher_node)
    timed_writer_node = timed_node("writer", writer_node)
    timed_reviewer_node = timed_node("reviewer", reviewer_node)
    timed_jt_node = timed_node("jt", jt_node)
    timed_chief_final_node = timed_node("chief_of_staff_final", chief_final_node)

    def auto_redraft_prep_node(state: SharedState) -> SharedState:
        feedback = state.get("review_feedback", [])
        reviewer_findings = state.get("reviewer_findings", {})
        if not feedback and isinstance(reviewer_findings, dict):
            for key in (
                "missing_content",
                "unsupported_claims",
                "contradictions_or_logic_problems",
                "format_or_structure_issues",
            ):
                issues = reviewer_findings.get(key, [])
                if isinstance(issues, list):
                    feedback.extend([item for item in issues if isinstance(item, str)])
        revision_notes = [f"Reviewer note: {item}" for item in feedback]
        print("\nReviewer requested revisions. Triggering one automatic redraft before human review.\n")
        next_state = {
            **state,
            "approved_facts": [*state.get("approved_facts", []), *revision_notes],
            "revision_targets": feedback,
            "redraft_source_draft": state.get("draft", ""),
            "auto_redraft_count": state.get("auto_redraft_count", 0) + 1,
            "status": "needs_redraft_auto",
        }
        if _commenter_artifacts_enabled(state):
            _print_debug_block(
                "AUTO REDRAFT INPUT / INSTRUCTIONS",
                (
                    f"revision_targets={next_state.get('revision_targets', [])}\n"
                    f"redraft_source_draft={next_state.get('redraft_source_draft', '')}\n"
                    f"approved_facts_added={revision_notes}"
                ),
                state,
            )
        return next_state

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
        print(f"jt_requested: {state.get('jt_requested', False)}")
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
                print("\nApplying human revision notes and re-running Writer + Reviewer.\n")
                redrafted_state = timed_writer_node(revised_state)
                rereviewed_state = timed_reviewer_node(redrafted_state)
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
        return "researcher" if state.get("route") == "research" else "writer"

    def route_after_reviewer(state: SharedState) -> str:
        if state.get("reviewer_parse_failed", False):
            return "reviewer_parse_failure"
        is_approved = state.get("review_approved", False)
        reviewer_findings = state.get("reviewer_findings", {})
        recommended_next_action = (
            reviewer_findings.get("recommended_next_action")
            if isinstance(reviewer_findings, dict)
            else None
        )
        has_feedback = bool(state.get("review_feedback")) or recommended_next_action in {"revise", "reject"}
        auto_redraft_count = state.get("auto_redraft_count", 0)
        jt_review_count = state.get("jt_review_count", 0)
        should_run_jt_stage = (
            state.get("jt_requested", False)
            and state.get("jt_mode") != "commenter"
            and jt_review_count < 1
        )
        if (not is_approved) and has_feedback and auto_redraft_count < max_auto_redrafts:
            return "auto_redraft_prep"
        if should_run_jt_stage:
            return "jt"
        return "chief_final"

    def route_after_chief_final(state: SharedState) -> str:
        if state.get("critical_reviewer_blocking", False):
            return "review_rejected_after_redraft"
        if (
            state.get("jt_requested", False)
            and state.get("jt_mode") == "commenter"
            and not state.get("review_approved", False)
        ):
            return "review_rejected_after_redraft"
        return state.get("chief_final_next_step", "human_review")

    def review_rejected_after_redraft_node(state: SharedState) -> SharedState:
        if state.get("critical_reviewer_blocking", False):
            message = (
                "Reviewer found unresolved unsupported claims or core fact contradictions. "
                "Stopping before normal human review."
            )
        else:
            message = (
                "Reviewer verdict remains needs_revision after the automatic redraft pass. "
                "Stopping before normal human review."
            )
        print(f"\n{message}\n")
        if _commenter_artifacts_enabled(state):
            writer_outputs = state.get("model_metadata", {}).get("writer_outputs", [])
            reviewer_outputs = state.get("model_metadata", {}).get("reviewer_outputs", [])
            _print_debug_block(
                "WRITER OUTPUT PASS 1",
                writer_outputs[0] if len(writer_outputs) > 0 else "",
                state,
            )
            _print_debug_block(
                "REVIEWER JSON PASS 1",
                reviewer_outputs[0] if len(reviewer_outputs) > 0 else "",
                state,
            )
            _print_debug_block(
                "AUTO REDRAFT INPUT / INSTRUCTIONS",
                (
                    f"revision_targets={state.get('revision_targets', [])}\n"
                    f"redraft_source_draft={state.get('redraft_source_draft', '')}"
                ),
                state,
            )
            _print_debug_block(
                "WRITER OUTPUT PASS 2",
                writer_outputs[1] if len(writer_outputs) > 1 else "",
                state,
            )
            _print_debug_block(
                "REVIEWER JSON PASS 2",
                reviewer_outputs[1] if len(reviewer_outputs) > 1 else "",
                state,
            )
        return {
            **state,
            "final_output": message,
            "status": "review_rejected_after_redraft",
        }

    graph_builder.add_node("chief_of_staff", timed_chief_node)
    graph_builder.add_node("researcher", timed_researcher_node)
    graph_builder.add_node("writer", timed_writer_node)
    graph_builder.add_node("reviewer", timed_reviewer_node)
    graph_builder.add_node("jt", timed_jt_node)
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
    graph_builder.add_edge("writer", "reviewer")
    graph_builder.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "reviewer_parse_failure": "reviewer_parse_failure",
            "auto_redraft_prep": "auto_redraft_prep",
            "jt": "jt",
            "chief_final": "chief_final",
        },
    )
    graph_builder.add_edge("auto_redraft_prep", "writer")
    graph_builder.add_edge("jt", "chief_final")
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
