from __future__ import annotations

from time import perf_counter

from langgraph.graph import END, START, StateGraph

from agents.chief_of_staff import ChiefOfStaffAgent
from agents.jt import JTAgent
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.writer import WriterAgent
from app.state import (
    SharedState,
    get_canonical_jt_requested,
    get_memory_lookup_fields,
    normalize_project_memory,
)
from tools.local_file_reader import build_evidence_bundle


def build_graph(
    chief_of_staff: ChiefOfStaffAgent,
    jt: JTAgent,
    researcher: ResearcherAgent,
    reviewer: ReviewerAgent,
    writer: WriterAgent,
):
    graph_builder = StateGraph(SharedState)
    max_auto_redrafts = 1

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

    def evidence_extract_node(state: SharedState) -> SharedState:
        model_metadata = state.get("model_metadata", {})
        file_contents = model_metadata.get("file_contents", {}) if isinstance(model_metadata, dict) else {}
        if not isinstance(file_contents, dict):
            file_contents = {}

        evidence_bundle = build_evidence_bundle(file_contents)
        research_facts = [fact for fact in state.get("research_facts", []) if isinstance(fact, str)]

        evidence_facts: list[str] = []
        for item in evidence_bundle:
            file_path = item.get("file_path", "")
            evidence_points = item.get("evidence_points", [])
            for point in evidence_points:
                if isinstance(point, str) and point.strip():
                    evidence_facts.append(f"[{file_path}] {point}")

        approved_facts = _dedupe_preserving_order([*research_facts, *evidence_facts])
        requested = len(state.get("files_requested", []))
        read = len(state.get("files_read", []))
        skipped = len(state.get("files_skipped", []))
        file_read_summary = f"requested={requested}, read={read}, skipped={skipped}"

        return {
            **state,
            "evidence_bundle": evidence_bundle,
            "approved_facts": approved_facts,
            "file_read_summary": file_read_summary,
            "status": "evidence_extracted",
        }

    def _dedupe_preserving_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def writer_node(state: SharedState) -> SharedState:
        written_state = writer.run(state)
        project_memory = normalize_project_memory(written_state.get("project_memory"))
        draft = written_state.get("draft", "")
        is_memory_inspection_turn = written_state.get("memory_turn_type") == "memory_inspection"
        updated_project_memory = (
            project_memory
            if is_memory_inspection_turn
            else {
                **project_memory,
                "latest_draft": draft if isinstance(draft, str) else "",
            }
        )
        current_run = written_state.get("current_run", {})
        if not isinstance(current_run, dict):
            current_run = {}
        return {
            **written_state,
            "project_memory": updated_project_memory,
            "current_run": {
                **current_run,
                "latest_draft": draft if isinstance(draft, str) else "",
            },
        }

    def memory_lookup_prep_node(state: SharedState) -> SharedState:
        project_memory = normalize_project_memory(state.get("project_memory"))
        lookup_fields = get_memory_lookup_fields(state.get("user_task", ""))
        if not lookup_fields:
            lookup_fields = ["latest_approved_output"]

        lines: list[str] = []
        approved_fact_lines: list[str] = []
        if "current_objective" in lookup_fields:
            current_objective = project_memory.get("current_objective", "")
            value = (
                current_objective
                if isinstance(current_objective, str) and current_objective.strip()
                else "(not set)"
            )
            lines.append(f"current_objective: {value}")
            approved_fact_lines.append(f"Session memory current_objective: {value}")
        if "active_deliverable_type" in lookup_fields:
            active_deliverable_type = project_memory.get("active_deliverable_type", "")
            value = (
                active_deliverable_type
                if isinstance(active_deliverable_type, str) and active_deliverable_type.strip()
                else "(not set)"
            )
            lines.append(f"active_deliverable_type: {value}")
            approved_fact_lines.append(f"Session memory active_deliverable_type: {value}")
        if "latest_approved_output" in lookup_fields:
            latest_approved_output = project_memory.get("latest_approved_output", "")
            value = (
                latest_approved_output
                if isinstance(latest_approved_output, str) and latest_approved_output.strip()
                else "No latest approved output is currently stored in session project memory."
            )
            lines.append(f"latest_approved_output: {value}")
            approved_fact_lines.append(f"Session memory latest_approved_output: {value}")
        lookup_result = "\n".join(lines)
        return {
            **state,
            "memory_turn_type": "memory_inspection",
            "memory_lookup_requested": True,
            "memory_lookup_fields": lookup_fields,
            "memory_lookup_result": lookup_result,
            "approved_facts": approved_fact_lines,
            "review_feedback": [],
            "review_approved": False,
            "reviewer_findings": {
                "overall_assessment": "",
                "missing_content": [],
                "unsupported_claims": [],
                "contradictions_or_logic_problems": [],
                "format_or_structure_issues": [],
                "recommended_next_action": "approve",
            },
            "status": "memory_lookup_prepared",
        }

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
    timed_evidence_extract_node = timed_node("evidence_extract", evidence_extract_node)
    timed_writer_node = timed_node("writer", writer_node)
    timed_memory_lookup_prep_node = timed_node("memory_lookup_prep", memory_lookup_prep_node)
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
            "writer_guidance_notes": [*state.get("writer_guidance_notes", []), *revision_notes],
            "reviewer_notes": [*state.get("reviewer_notes", []), *revision_notes],
            "revision_targets": feedback,
            "redraft_source_draft": state.get("draft", ""),
            "auto_redraft_count": state.get("auto_redraft_count", 0) + 1,
            "status": "needs_redraft_auto",
        }

    def human_review_node(state: SharedState) -> SharedState:
        project_memory = normalize_project_memory(state.get("project_memory"))
        current_run = state.get("current_run", {})
        if not isinstance(current_run, dict):
            current_run = {}

        if state.get("dry_run"):
            print("\nDry-run mode: auto-approving at human review step.\n")
            approved_output = state.get("draft", "")
            is_memory_inspection_turn = state.get("memory_turn_type") == "memory_inspection"
            return {
                **state,
                "final_output": approved_output,
                "project_memory": (
                    project_memory
                    if is_memory_inspection_turn
                    else {
                        **project_memory,
                        "latest_approved_output": approved_output if isinstance(approved_output, str) else "",
                    }
                ),
                "current_run": {
                    **current_run,
                    "latest_approved_output": approved_output if isinstance(approved_output, str) else "",
                },
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
        print(f"jt_requested: {get_canonical_jt_requested(state)}")
        print(f"jt_mode: {state.get('jt_mode')}")
        if state.get("memory_lookup_requested", False):
            print("Reviewer verdict: not_run (memory lookup path)")
        else:
            print(f"Reviewer verdict: {'approved' if review_approved else 'needs_revision'}")
        if state.get("file_read_summary"):
            print(f"File read summary: {state.get('file_read_summary')}")
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
                    "writer_guidance_notes": [
                        *state.get("writer_guidance_notes", []),
                        f"Human reviewer note: {notes}",
                    ],
                    "human_notes": [*state.get("human_notes", []), notes],
                    "status": "needs_redraft",
                }
                print("\nApplying human revision notes and re-running Writer + QC flow.\n")
                redrafted_state = timed_writer_node(revised_state)
                post_writer = (
                    timed_jt_node(redrafted_state) if get_canonical_jt_requested(redrafted_state) else redrafted_state
                )
                rereviewed_state = timed_reviewer_node(post_writer)
                return human_review_node(rereviewed_state)

            return {
                **state,
                "final_output": "Finalization declined by human reviewer.",
                "status": "stopped_by_human",
            }

        is_memory_inspection_turn = state.get("memory_turn_type") == "memory_inspection"
        return {
            **state,
            "final_output": draft,
            "project_memory": (
                project_memory
                if is_memory_inspection_turn
                else {
                    **project_memory,
                    "latest_approved_output": draft if isinstance(draft, str) else "",
                }
            ),
            "current_run": {
                **current_run,
                "latest_approved_output": draft if isinstance(draft, str) else "",
            },
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
        if state.get("route") == "memory_lookup" or state.get("memory_lookup_requested", False):
            return "memory_lookup_prep"
        if isinstance(work_order, dict) and isinstance(work_order.get("research_needed"), bool):
            return "researcher" if work_order["research_needed"] else "evidence_extract"
        return "researcher" if state.get("route") == "research" else "evidence_extract"

    def route_after_writer(state: SharedState) -> str:
        if state.get("memory_lookup_requested", False):
            return "human_review"
        return "jt" if get_canonical_jt_requested(state) else "reviewer"

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
    graph_builder.add_node("evidence_extract", timed_evidence_extract_node)
    graph_builder.add_node("memory_lookup_prep", timed_memory_lookup_prep_node)
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
            "evidence_extract": "evidence_extract",
            "memory_lookup_prep": "memory_lookup_prep",
        },
    )
    graph_builder.add_edge("memory_lookup_prep", "writer")
    graph_builder.add_edge("researcher", "evidence_extract")
    graph_builder.add_edge("evidence_extract", "writer")
    graph_builder.add_conditional_edges(
        "writer",
        route_after_writer,
        {
            "human_review": "human_review",
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
