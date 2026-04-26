from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from langgraph.graph import END, START, StateGraph

log = logging.getLogger(__name__)

from agents.advisor import AdvisorAgent
from agents.advisor_router import AdvisorRouterAgent
from agents.backend import BackendAgent
from agents.chief_of_staff import ChiefOfStaffAgent
from agents.communication_influence_advisor import CommunicationInfluenceAdvisorAgent
from agents.entrepreneur_execution_advisor import EntrepreneurExecutionAdvisorAgent
from agents.frontend import FrontendAgent
from agents.growth_mindset_advisor import GrowthMindsetAdvisorAgent
from agents.jt import JTAgent
from agents.leadership_culture_advisor import LeadershipCultureAdvisorAgent
from agents.qa import QAAgent
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.strategy_systems_advisor import StrategySystemsAdvisorAgent
from agents.writer import WriterAgent
from app.state import (
    SharedState,
    get_canonical_advisor_pod_requested,
    get_canonical_dev_pod_requested,
    get_canonical_jt_requested,
    get_memory_lookup_fields,
    normalize_project_memory,
)
from app.advisor_registry import ADVISOR_IDS
from tools.local_file_reader import build_evidence_bundle


def build_graph(
    chief_of_staff: ChiefOfStaffAgent,
    jt: JTAgent,
    researcher: ResearcherAgent,
    reviewer: ReviewerAgent,
    writer: WriterAgent,
    backend: BackendAgent | None = None,
    frontend: FrontendAgent | None = None,
    qa: QAAgent | None = None,
    advisor: AdvisorAgent | None = None,
    advisor_router: AdvisorRouterAgent | None = None,
    strategy_systems_advisor: StrategySystemsAdvisorAgent | None = None,
    leadership_culture_advisor: LeadershipCultureAdvisorAgent | None = None,
    communication_influence_advisor: CommunicationInfluenceAdvisorAgent | None = None,
    growth_mindset_advisor: GrowthMindsetAdvisorAgent | None = None,
    entrepreneur_execution_advisor: EntrepreneurExecutionAdvisorAgent | None = None,
    on_node_enter=None,
    on_node_exit=None,
    human_review_fn=None,
    file_writer: Any | None = None,
):
    graph_builder = StateGraph(SharedState)
    max_auto_redrafts = 1

    def timed_node(node_name: str, fn):
        def _wrapped(state: SharedState) -> SharedState:
            if on_node_enter:
                on_node_enter(node_name, state)
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
            result = {
                **result_state,
                "model_metadata": merged_metadata,
            }
            if on_node_exit:
                on_node_exit(node_name, result, elapsed_ms)
            return result

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
        required_structures: list[dict[str, object]] = []
        for item in evidence_bundle:
            item_structures = item.get("required_structures", [])
            if isinstance(item_structures, list):
                for structure in item_structures:
                    if isinstance(structure, dict):
                        required_structures.append(structure)
        research_facts = [fact for fact in state.get("research_facts", []) if isinstance(fact, str)]

        evidence_facts: list[str] = []
        for item in evidence_bundle:
            file_path = item.get("file_path", "")
            evidence_points = item.get("evidence_points", [])
            for point in evidence_points:
                if isinstance(point, str) and point.strip():
                    evidence_facts.append(f"[{file_path}] {point}")

        # File-derived evidence facts come first so they're not buried by generic
        # researcher output when the writer scans the approved_facts list.
        approved_facts = _dedupe_preserving_order([*evidence_facts, *research_facts])

        # Safety net: if no research ran and no file evidence was loaded, the writer
        # would produce hollow filler with nothing to ground its output against.
        # Inject the prior session's approved output as a concrete fallback fact so
        # the writer at minimum has the last known good output to work from.
        # Excluded for memory-lookup turns (which intentionally set approved_facts
        # themselves) and when research already produced facts (no need for fallback).
        if not approved_facts and not state.get("memory_lookup_requested", False):
            _prior = normalize_project_memory(state.get("project_memory")).get(
                "latest_approved_output", ""
            )
            if isinstance(_prior, str) and _prior.strip():
                approved_facts = [f"Prior session approved output:\n{_prior}"]
                print(
                    "[evidence_extract] No research facts available — injecting prior "
                    "session output as fallback context for the Writer."
                )

        simple_grounded_retrieval = _is_simple_grounded_retrieval_task(
            task=state.get("user_task", ""),
            required_structures=required_structures,
            files_read=state.get("files_read", []),
        )
        requested = len(state.get("files_requested", []))
        read = len(state.get("files_read", []))
        skipped = len(state.get("files_skipped", []))
        file_read_summary = f"requested={requested}, read={read}, skipped={skipped}"
        brainstorm_file_grounding_used = bool(
            get_canonical_advisor_pod_requested(state) and read > 0 and evidence_bundle
        )
        brainstorm_file_grounding_summary = (
            f"brainstorm_file_grounding_used={brainstorm_file_grounding_used}; "
            f"evidence_items={len(evidence_bundle)}; approved_facts={len(approved_facts)}"
        )
        if brainstorm_file_grounding_used:
            print(f"[advisor_grounding] {brainstorm_file_grounding_summary}")

        # Build a compact raw-content block for the writer (capped to avoid large
        # prompts) then strip file_contents from model_metadata so it does not ride
        # through every downstream node and blow up context windows.
        _MAX_RAW_CHARS_PER_FILE = 3000
        _MAX_RAW_FILES = 5
        raw_parts: list[str] = []
        for _fp, _content in list(file_contents.items())[:_MAX_RAW_FILES]:
            if isinstance(_content, str) and _content.strip():
                raw_parts.append(f"--- {_fp} ---\n{_content[:_MAX_RAW_CHARS_PER_FILE]}")
        raw_file_context = "\n\n".join(raw_parts)

        stripped_metadata = {k: v for k, v in (model_metadata if isinstance(model_metadata, dict) else {}).items() if k != "file_contents"}

        return {
            **state,
            "evidence_bundle": evidence_bundle,
            "approved_facts": approved_facts,
            "required_structures": required_structures,
            "simple_grounded_retrieval": simple_grounded_retrieval,
            "file_read_summary": file_read_summary,
            "brainstorm_file_grounding_used": brainstorm_file_grounding_used,
            "brainstorm_file_grounding_summary": brainstorm_file_grounding_summary,
            "raw_file_context": raw_file_context,
            "status": "evidence_extracted",
            "model_metadata": stripped_metadata,
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

    def _is_simple_grounded_retrieval_task(
        *,
        task: object,
        required_structures: list[dict[str, object]],
        files_read: object,
    ) -> bool:
        if not isinstance(task, str):
            return False
        if not isinstance(files_read, list) or not files_read:
            return False
        if not required_structures:
            return False
        normalized = " ".join(task.lower().split())
        retrieval_phrases = (
            "what are the three workstreams",
            "what does the file say",
            "based on my files",
            "what are the names",
            "list the items",
            "list the workstreams",
        )
        return any(phrase in normalized for phrase in retrieval_phrases)

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
            lookup_fields = ["current_objective", "active_deliverable_type", "latest_approved_output"]

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
        elif state.get("dev_pod_requested", False):
            pod_verdict = state.get("pod_qa_verdict", "unknown")
            print(f"Reviewer verdict: pod_qa_{pod_verdict}")
        elif state.get("advisor_pod_requested", False):
            advisor_route = state.get("advisor_route", {})
            selected = advisor_route.get("selected_advisors", []) if isinstance(advisor_route, dict) else []
            print(f"Advisor route selected: {selected}")
            if isinstance(advisor_route, dict):
                reasons = advisor_route.get("selection_reason", {})
                if isinstance(reasons, dict):
                    for advisor_id, reason in reasons.items():
                        print(f"- advisor reason [{advisor_id}]: {reason}")
        else:
            print(f"Reviewer verdict: {'approved' if review_approved else 'needs_revision'}")
        if state.get("file_read_summary"):
            print(f"File read summary: {state.get('file_read_summary')}")
        if review_feedback:
            print("Reviewer feedback:")
            for item in review_feedback:
                print(f"- {item}")
            print()

        if human_review_fn is not None:
            approved, notes = human_review_fn(draft, state)
        else:
            try:
                approved = input("Approve final output? [y/N]: ").strip().lower() == "y"
            except (EOFError, KeyboardInterrupt):
                return {
                    **state,
                    "final_output": "Finalization interrupted before approval.",
                    "status": "stopped_by_human",
                }
            notes = ""
            if not approved:
                try:
                    notes = input("Optional revision notes for Writer (or press Enter to keep as-is): ").strip()
                except (EOFError, KeyboardInterrupt):
                    return {
                        **state,
                        "final_output": "Finalization interrupted before approval.",
                        "status": "stopped_by_human",
                    }
        if not approved:
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

    max_pod_revisions = 2

    def pod_entry_node(state: SharedState) -> SharedState:
        work_order = state.get("work_order") or {}
        existing_brief = state.get("pod_task_brief", "")
        if not existing_brief:
            criteria = "\n".join(f"- {c}" for c in work_order.get("success_criteria", []))
            pod_task_brief = (
                f"Objective: {work_order.get('objective', '')}\n"
                f"Deliverable: {work_order.get('deliverable_type', '')}\n"
                f"Success criteria:\n{criteria or '- (none provided)'}"
            )
        else:
            pod_task_brief = existing_brief
        return {
            **state,
            "pod_task_brief": pod_task_brief,
            "pod_artifacts": {},
            "pod_qa_findings": [],
            "pod_qa_verdict": None,
            "pod_revision_count": 0,
            "status": "pod_started",
        }

    def pod_backend_node(state: SharedState) -> SharedState:
        if backend is None:
            raise RuntimeError("BackendAgent not provided to build_graph")
        return backend.run(state)

    def pod_frontend_node(state: SharedState) -> SharedState:
        if frontend is None:
            raise RuntimeError("FrontendAgent not provided to build_graph")
        return frontend.run(state)

    def pod_qa_node(state: SharedState) -> SharedState:
        if qa is None:
            raise RuntimeError("QAAgent not provided to build_graph")
        return qa.run(state)

    def pod_revise_prep_node(state: SharedState) -> SharedState:
        revision_count = state.get("pod_revision_count", 0)
        findings = state.get("pod_qa_findings", [])
        findings_block = "\n".join(f"- {f}" for f in findings) or "- (no specific findings)"
        revision_note = (
            f"\n\n[Revision {revision_count + 1}] QA findings to address:\n{findings_block}"
        )
        print(f"\n[pod] QA requested revision {revision_count + 1}. Re-running backend + frontend.\n")
        return {
            **state,
            "pod_task_brief": f"{state.get('pod_task_brief', '')}{revision_note}",
            "pod_artifacts": {},
            "pod_revision_count": revision_count + 1,
            "status": "pod_revising",
        }

    def pod_assemble_node(state: SharedState) -> SharedState:
        artifacts = state.get("pod_artifacts") or {}
        backend_out = artifacts.get("backend", "")
        frontend_out = artifacts.get("frontend", "")
        qa_findings = state.get("pod_qa_findings", [])
        revision_count = state.get("pod_revision_count", 0)

        parts: list[str] = []
        if backend_out:
            parts.append(f"## Backend\n\n{backend_out}")
        if frontend_out:
            parts.append(f"## Frontend\n\n{frontend_out}")
        if qa_findings:
            findings_block = "\n".join(f"- {f}" for f in qa_findings)
            verdict = state.get("pod_qa_verdict", "")
            label = "QA Notes (passed)" if verdict == "pass" else f"QA Notes (escalated after {revision_count} revision(s))"
            parts.append(f"## {label}\n\n{findings_block}")

        assembled = "\n\n---\n\n".join(parts) if parts else "(no pod output generated)"
        return {
            **state,
            "draft": assembled,
            "status": "pod_assembled",
        }

    timed_pod_entry_node = timed_node("pod_entry", pod_entry_node)
    timed_pod_backend_node = timed_node("pod_backend", pod_backend_node)
    timed_pod_frontend_node = timed_node("pod_frontend", pod_frontend_node)
    timed_pod_qa_node = timed_node("pod_qa", pod_qa_node)
    timed_pod_revise_prep_node = timed_node("pod_revise_prep", pod_revise_prep_node)
    timed_pod_assemble_node = timed_node("pod_assemble", pod_assemble_node)

    # ── Advisor pod nodes ──────────────────────────────────────────────────────

    def advisor_entry_node(state: SharedState) -> SharedState:
        """Prepare the advisor brief from the work order or existing brief."""
        work_order = state.get("work_order") or {}
        existing_brief = state.get("advisor_brief", "")
        if not existing_brief:
            criteria = "\n".join(f"- {c}" for c in work_order.get("success_criteria", []))
            advisor_brief = (
                f"Objective: {work_order.get('objective', '')}\n"
                f"Open questions: {work_order.get('open_questions', [])}\n"
                f"Success criteria:\n{criteria or '- (none provided)'}"
            )
        else:
            advisor_brief = existing_brief

        evidence_bundle = state.get("evidence_bundle", [])
        if not isinstance(evidence_bundle, list):
            evidence_bundle = []

        approved_facts = [
            fact for fact in state.get("approved_facts", []) if isinstance(fact, str) and fact.strip()
        ]
        if evidence_bundle:
            evidence_lines: list[str] = []
            for item in evidence_bundle:
                fp = item.get("file_path", "")
                points = item.get("evidence_points", [])
                evidence_lines.append(f"  [{fp}]")
                for pt in points[:6]:   # cap at 6 points per file to stay concise
                    evidence_lines.append(f"    • {pt}")
            if evidence_lines:
                advisor_brief = (
                    advisor_brief
                    + "\n\nLocal file context (binding for project-specific structure and labels):\n"
                    + "\n".join(evidence_lines)
                )
        if approved_facts:
            facts_lines = "\n".join(f"  - {fact}" for fact in approved_facts[:30])
            advisor_brief = (
                advisor_brief
                + "\n\nApproved facts (treat as primary context when they come from local files):\n"
                + facts_lines
            )
        required_structures = state.get("required_structures", [])
        if isinstance(required_structures, list) and required_structures:
            structure_lines: list[str] = []
            for structure in required_structures:
                if not isinstance(structure, dict):
                    continue
                structure_lines.append(
                    f"- type: {structure.get('type', '')}; label: {structure.get('label', '')}; "
                    f"items: {structure.get('items', [])}; constraints: {structure.get('constraints', [])}; "
                    f"source_file: {structure.get('source_file', '')}"
                )
            if structure_lines:
                advisor_brief = (
                    advisor_brief
                    + "\n\nRequired structures (binding contracts from local files):\n"
                    + "\n".join(structure_lines)
                )

        return {
            **state,
            "advisor_brief": advisor_brief,
            "advisor_route": {
                "selected_advisors": [],
                "selection_reason": {},
                "skipped_advisors": {},
                "advisor_route_confidence": "low",
            },
            "advisor_selected_advisors": [],
            "advisor_invoked_advisors": [],
            "advisor_outputs": {},
            "advisor_synthesis": "",
            "status": "advisor_started",
        }

    def advisor_simple_grounded_answer_node(state: SharedState) -> SharedState:
        required_structures = state.get("required_structures", [])
        lines: list[str] = []
        if isinstance(required_structures, list):
            for structure in required_structures:
                if not isinstance(structure, dict):
                    continue
                items = structure.get("items", [])
                label = structure.get("label", "items")
                if isinstance(items, list) and items:
                    heading = f"The {len(items)} {label} from your file are:"
                    lines.append(heading)
                    for idx, item in enumerate(items, start=1):
                        if isinstance(item, str):
                            lines.append(f"{idx}. {item}")
                    break
        concise_answer = "\n".join(lines) if lines else "I could not find grounded list items in the provided files."
        return {
            **state,
            "draft": concise_answer,
            "advisor_synthesis": concise_answer,
            "status": "advisor_simple_grounded_answered",
        }

    def advisor_router_node(state: SharedState) -> SharedState:
        if advisor_router is None:
            raise RuntimeError("AdvisorRouterAgent not provided to build_graph")
        return advisor_router.run(state)

    def _mark_advisor_invoked(state: SharedState, advisor_id: str) -> SharedState:
        invoked = [item for item in state.get("advisor_invoked_advisors", []) if isinstance(item, str)]
        if advisor_id not in invoked:
            invoked.append(advisor_id)
        return {
            **state,
            "advisor_invoked_advisors": invoked,
        }

    def advisor_strategy_systems_node(state: SharedState) -> SharedState:
        if strategy_systems_advisor is None:
            raise RuntimeError("StrategySystemsAdvisorAgent not provided to build_graph")
        return _mark_advisor_invoked(strategy_systems_advisor.run(state), "strategy_systems")

    def advisor_leadership_culture_node(state: SharedState) -> SharedState:
        if leadership_culture_advisor is None:
            raise RuntimeError("LeadershipCultureAdvisorAgent not provided to build_graph")
        return _mark_advisor_invoked(leadership_culture_advisor.run(state), "leadership_culture")

    def advisor_communication_influence_node(state: SharedState) -> SharedState:
        if communication_influence_advisor is None:
            raise RuntimeError("CommunicationInfluenceAdvisorAgent not provided to build_graph")
        return _mark_advisor_invoked(
            communication_influence_advisor.run(state),
            "communication_influence",
        )

    def advisor_growth_mindset_node(state: SharedState) -> SharedState:
        if growth_mindset_advisor is None:
            raise RuntimeError("GrowthMindsetAdvisorAgent not provided to build_graph")
        return _mark_advisor_invoked(growth_mindset_advisor.run(state), "growth_mindset")

    def advisor_entrepreneur_execution_node(state: SharedState) -> SharedState:
        if entrepreneur_execution_advisor is None:
            raise RuntimeError("EntrepreneurExecutionAdvisorAgent not provided to build_graph")
        return _mark_advisor_invoked(
            entrepreneur_execution_advisor.run(state),
            "entrepreneur_execution",
        )

    def advisor_assemble_node(state: SharedState) -> SharedState:
        if advisor is None:
            raise RuntimeError("AdvisorAgent not provided to build_graph")
        return advisor.synthesize(state)

    timed_advisor_entry_node = timed_node("advisor_entry", advisor_entry_node)
    timed_advisor_router_node = timed_node("advisor_router", advisor_router_node)
    timed_advisor_strategy_systems_node = timed_node("advisor_strategy_systems", advisor_strategy_systems_node)
    timed_advisor_leadership_culture_node = timed_node("advisor_leadership_culture", advisor_leadership_culture_node)
    timed_advisor_communication_influence_node = timed_node("advisor_communication_influence", advisor_communication_influence_node)
    timed_advisor_growth_mindset_node = timed_node("advisor_growth_mindset", advisor_growth_mindset_node)
    timed_advisor_entrepreneur_execution_node = timed_node("advisor_entrepreneur_execution", advisor_entrepreneur_execution_node)
    timed_advisor_assemble_node = timed_node("advisor_assemble", advisor_assemble_node)
    timed_advisor_simple_grounded_answer_node = timed_node(
        "advisor_simple_grounded_answer",
        advisor_simple_grounded_answer_node,
    )

    def route_after_pod_qa(state: SharedState) -> str:
        verdict = state.get("pod_qa_verdict", "revise")
        revision_count = state.get("pod_revision_count", 0)
        if verdict == "pass" or revision_count >= max_pod_revisions:
            return "pod_assemble"
        return "pod_revise_prep"

    def route_after_advisor_router(state: SharedState) -> str:
        selected = [
            advisor_id
            for advisor_id in state.get("advisor_selected_advisors", [])
            if isinstance(advisor_id, str)
        ]
        for advisor_id in ADVISOR_IDS:
            if advisor_id in selected:
                return f"advisor_{advisor_id}"
        return "advisor_assemble"

    def route_after_advisor_node(state: SharedState) -> str:
        selected = [
            advisor_id
            for advisor_id in state.get("advisor_selected_advisors", [])
            if isinstance(advisor_id, str)
        ]
        invoked = {
            advisor_id
            for advisor_id in state.get("advisor_invoked_advisors", [])
            if isinstance(advisor_id, str)
        }
        for advisor_id in ADVISOR_IDS:
            if advisor_id in selected and advisor_id not in invoked:
                return f"advisor_{advisor_id}"
        return "advisor_assemble"

    def route_after_advisor_entry(state: SharedState) -> str:
        if state.get("simple_grounded_retrieval", False):
            return "advisor_simple_grounded_answer"
        return "advisor_router"

    def route_after_chief(state: SharedState) -> str:
        if get_canonical_dev_pod_requested(state):
            return "pod_entry"
        if get_canonical_advisor_pod_requested(state):
            files_read = state.get("files_read", [])
            has_local_file_evidence = isinstance(files_read, list) and len(files_read) > 0
            if has_local_file_evidence:
                return "researcher"
            return "advisor_entry"
        work_order = state.get("work_order")
        route = state.get("route")
        if route == "memory_lookup" or state.get("memory_lookup_requested", False):
            return "memory_lookup_prep"
        # Explicit route field takes precedence — CoS may have applied overrides (web_search,
        # vault context) that set route="research" even if work_order.research_needed was
        # originally False. Always honour the explicit route when it says "research".
        if route == "research":
            return "researcher"
        if isinstance(work_order, dict) and isinstance(work_order.get("research_needed"), bool):
            return "researcher" if work_order["research_needed"] else "evidence_extract"
        return "evidence_extract"

    def route_after_writer(state: SharedState) -> str:
        if state.get("memory_lookup_requested", False):
            return "human_review"
        return "jt" if get_canonical_jt_requested(state) else "reviewer"

    def route_after_evidence_extract(state: SharedState) -> str:
        if get_canonical_advisor_pod_requested(state):
            return "advisor_entry"
        return "writer"

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

    # ── Artifact writer node ──────────────────────────────────────────────────
    # Runs after human_review approval. If a file_writer was provided at graph
    # build time (i.e. the run was started with an output_dir), it auto-writes
    # the approved final_output as output.md — a guaranteed persistent copy
    # regardless of whether the writer agent also created files.
    # Non-finalized states (stopped_by_human, rejected) pass through unchanged.

    def artifact_writer_node(state: SharedState) -> SharedState:
        if file_writer is None:
            return state

        if state.get("status") != "finalized":
            return state

        final_output = state.get("final_output", "")
        if not final_output:
            return state

        existing: list[str] = list(state.get("files_created", []))

        try:
            path = file_writer.write_file("output.md", final_output)
            existing.append(path)
            log.info("[artifact_writer] Auto-wrote final output → %s", path)
            print(f"[artifact_writer] Final output saved → {path}")
        except Exception as exc:  # noqa: BLE001
            log.warning("[artifact_writer] Could not write output.md: %s", exc)

        return {
            **state,
            "files_created": existing,
        }

    timed_artifact_writer_node = timed_node("artifact_writer", artifact_writer_node)

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
    graph_builder.add_node("artifact_writer", timed_artifact_writer_node)
    graph_builder.add_node("reviewer_parse_failure", timed_node("reviewer_parse_failure", reviewer_parse_failure_node))
    graph_builder.add_node(
        "review_rejected_after_redraft",
        timed_node("review_rejected_after_redraft", review_rejected_after_redraft_node),
    )
    graph_builder.add_node("pod_entry", timed_pod_entry_node)
    graph_builder.add_node("pod_backend", timed_pod_backend_node)
    graph_builder.add_node("pod_frontend", timed_pod_frontend_node)
    graph_builder.add_node("pod_qa", timed_pod_qa_node)
    graph_builder.add_node("pod_revise_prep", timed_pod_revise_prep_node)
    graph_builder.add_node("pod_assemble", timed_pod_assemble_node)

    graph_builder.add_node("advisor_entry", timed_advisor_entry_node)
    graph_builder.add_node("advisor_router", timed_advisor_router_node)
    graph_builder.add_node("advisor_strategy_systems", timed_advisor_strategy_systems_node)
    graph_builder.add_node("advisor_leadership_culture", timed_advisor_leadership_culture_node)
    graph_builder.add_node("advisor_communication_influence", timed_advisor_communication_influence_node)
    graph_builder.add_node("advisor_growth_mindset", timed_advisor_growth_mindset_node)
    graph_builder.add_node("advisor_entrepreneur_execution", timed_advisor_entrepreneur_execution_node)
    graph_builder.add_node("advisor_assemble", timed_advisor_assemble_node)
    graph_builder.add_node("advisor_simple_grounded_answer", timed_advisor_simple_grounded_answer_node)

    graph_builder.add_edge(START, "chief_of_staff")
    graph_builder.add_conditional_edges(
        "chief_of_staff",
        route_after_chief,
        {
            "researcher": "researcher",
            "evidence_extract": "evidence_extract",
            "memory_lookup_prep": "memory_lookup_prep",
            "pod_entry": "pod_entry",
            "advisor_entry": "advisor_entry",
        },
    )
    graph_builder.add_edge("memory_lookup_prep", "writer")
    graph_builder.add_edge("researcher", "evidence_extract")
    graph_builder.add_conditional_edges(
        "evidence_extract",
        route_after_evidence_extract,
        {
            "advisor_entry": "advisor_entry",
            "writer": "writer",
        },
    )
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
    graph_builder.add_edge("human_review", "artifact_writer")
    graph_builder.add_edge("artifact_writer", END)
    graph_builder.add_edge("reviewer_parse_failure", END)
    graph_builder.add_edge("review_rejected_after_redraft", END)

    graph_builder.add_edge("pod_entry", "pod_backend")
    graph_builder.add_edge("pod_backend", "pod_frontend")
    graph_builder.add_edge("pod_frontend", "pod_qa")
    graph_builder.add_conditional_edges(
        "pod_qa",
        route_after_pod_qa,
        {
            "pod_assemble": "pod_assemble",
            "pod_revise_prep": "pod_revise_prep",
        },
    )
    graph_builder.add_edge("pod_revise_prep", "pod_backend")
    graph_builder.add_edge("pod_assemble", "human_review")

    graph_builder.add_conditional_edges(
        "advisor_entry",
        route_after_advisor_entry,
        {
            "advisor_router": "advisor_router",
            "advisor_simple_grounded_answer": "advisor_simple_grounded_answer",
        },
    )
    graph_builder.add_conditional_edges(
        "advisor_router",
        route_after_advisor_router,
        {
            "advisor_strategy_systems": "advisor_strategy_systems",
            "advisor_leadership_culture": "advisor_leadership_culture",
            "advisor_communication_influence": "advisor_communication_influence",
            "advisor_growth_mindset": "advisor_growth_mindset",
            "advisor_entrepreneur_execution": "advisor_entrepreneur_execution",
            "advisor_assemble": "advisor_assemble",
        },
    )
    graph_builder.add_conditional_edges(
        "advisor_strategy_systems",
        route_after_advisor_node,
        {
            "advisor_strategy_systems": "advisor_strategy_systems",
            "advisor_leadership_culture": "advisor_leadership_culture",
            "advisor_communication_influence": "advisor_communication_influence",
            "advisor_growth_mindset": "advisor_growth_mindset",
            "advisor_entrepreneur_execution": "advisor_entrepreneur_execution",
            "advisor_assemble": "advisor_assemble",
        },
    )
    graph_builder.add_conditional_edges(
        "advisor_leadership_culture",
        route_after_advisor_node,
        {
            "advisor_strategy_systems": "advisor_strategy_systems",
            "advisor_leadership_culture": "advisor_leadership_culture",
            "advisor_communication_influence": "advisor_communication_influence",
            "advisor_growth_mindset": "advisor_growth_mindset",
            "advisor_entrepreneur_execution": "advisor_entrepreneur_execution",
            "advisor_assemble": "advisor_assemble",
        },
    )
    graph_builder.add_conditional_edges(
        "advisor_communication_influence",
        route_after_advisor_node,
        {
            "advisor_strategy_systems": "advisor_strategy_systems",
            "advisor_leadership_culture": "advisor_leadership_culture",
            "advisor_communication_influence": "advisor_communication_influence",
            "advisor_growth_mindset": "advisor_growth_mindset",
            "advisor_entrepreneur_execution": "advisor_entrepreneur_execution",
            "advisor_assemble": "advisor_assemble",
        },
    )
    graph_builder.add_conditional_edges(
        "advisor_growth_mindset",
        route_after_advisor_node,
        {
            "advisor_strategy_systems": "advisor_strategy_systems",
            "advisor_leadership_culture": "advisor_leadership_culture",
            "advisor_communication_influence": "advisor_communication_influence",
            "advisor_growth_mindset": "advisor_growth_mindset",
            "advisor_entrepreneur_execution": "advisor_entrepreneur_execution",
            "advisor_assemble": "advisor_assemble",
        },
    )
    graph_builder.add_conditional_edges(
        "advisor_entrepreneur_execution",
        route_after_advisor_node,
        {
            "advisor_strategy_systems": "advisor_strategy_systems",
            "advisor_leadership_culture": "advisor_leadership_culture",
            "advisor_communication_influence": "advisor_communication_influence",
            "advisor_growth_mindset": "advisor_growth_mindset",
            "advisor_entrepreneur_execution": "advisor_entrepreneur_execution",
            "advisor_assemble": "advisor_assemble",
        },
    )
    graph_builder.add_edge("advisor_assemble", "human_review")
    graph_builder.add_edge("advisor_simple_grounded_answer", "human_review")

    return graph_builder.compile()
