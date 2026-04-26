from __future__ import annotations

import argparse

from openai import AuthenticationError, RateLimitError

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
from app.config import get_settings
from app.graph import build_graph
from app.jt_request import detect_jt_request
from app.state import SharedState, empty_project_memory, normalize_project_memory
from tools.agent_knowledge_loader import AgentKnowledgeLoader
from tools.local_file_reader import load_local_files
from tools.obsidian_context import ObsidianContextTool
from tools.openai_client import DryRunResponsesClient, ResponsesClient
from tools.session_persistence import describe_session, load_session, save_session
from tools.voice_loader import VoiceLoader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local multi-agent CLI")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run deterministically without OpenAI API calls.",
    )
    parser.add_argument(
        "--jt",
        action="store_true",
        help="Enable optional JT challenge stage.",
    )
    parser.add_argument(
        "--jt-mode",
        type=str,
        default=None,
        help="Optional JT mode label (for example: advisory or strict).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print detailed node artifacts for diagnosis.",
    )
    parser.add_argument(
        "--files-path",
        action="append",
        default=[],
        help="Explicit local file or folder path to include as bounded evidence input. Repeat to add multiple paths.",
    )
    parser.add_argument(
        "--web-search",
        action="store_true",
        help="Enable live web search for the Researcher agent.",
    )
    parser.add_argument(
        "--dev-pod",
        action="store_true",
        help="Route task through the developer pod (Backend, Frontend, QA agents).",
    )
    parser.add_argument(
        "--advisor",
        action="store_true",
        help="Route task through the advisor pod (all five advisor clusters + synthesis).",
    )
    parser.add_argument("task", type=str, nargs="*", help="Task for the agent team")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    file_read_result = load_local_files(args.files_path)

    if args.dry_run:
        print("\nMode: DRY RUN (no OpenAI calls)\n")
        client = DryRunResponsesClient()
        obsidian_tool: ObsidianContextTool | None = None
        agent_knowledge_loader: AgentKnowledgeLoader | None = None
        voice_loader = VoiceLoader("")
    else:
        try:
            settings = get_settings()
        except ValueError as e:
            print(f"\nConfiguration error: {e}\n")
            return

        def _make_client(agent: str) -> ResponsesClient:
            """Return a ResponsesClient pinned to the model configured for *agent*."""
            resolved = settings.agent_model(agent)
            return ResponsesClient(settings, model=resolved)

        # Shared client used only for infrastructure tools (Obsidian navigation,
        # vault context). Classification/routing quality is fine at the global model.
        client = ResponsesClient(settings)

        if settings.obsidian_vault_path:
            obsidian_tool = ObsidianContextTool(settings.obsidian_vault_path, client)
            if obsidian_tool.available:
                print(f"[tools] Obsidian vault loaded: {settings.obsidian_vault_path}")
            else:
                print(f"[tools] Warning: OBSIDIAN_VAULT_PATH set but path not found: {settings.obsidian_vault_path}")
                obsidian_tool = None

            agent_knowledge_loader = AgentKnowledgeLoader(settings.obsidian_vault_path)
            if agent_knowledge_loader.available:
                print(f"[tools] Agent knowledge layer loaded: {settings.obsidian_vault_path}/agent_team/agent_docs")
            else:
                print("[tools] Warning: Agent knowledge layer not found (agent_team/agent_docs missing)")
                agent_knowledge_loader = None
        else:
            obsidian_tool = None
            agent_knowledge_loader = None

        voice_loader = VoiceLoader(settings.voice_file_path)
        if voice_loader.available:
            print(f"[tools] Voice/style guide loaded: {settings.voice_file_path}")
        elif settings.voice_file_path:
            print(f"[tools] Warning: VOICE_FILE_PATH set but file not found: {settings.voice_file_path}")

    if not args.dry_run:
        print("[models] Agent model assignments:")
        for _agent_name in (
            "chief_of_staff", "researcher", "writer", "reviewer", "jt",
            "backend", "frontend", "qa",
            "advisor_router", "advisor", "advisor_clusters",
        ):
            print(f"  {_agent_name}: {settings.agent_model(_agent_name)}")

    chief_of_staff = ChiefOfStaffAgent(
        _make_client("chief_of_staff") if not args.dry_run else client,
        obsidian_tool=obsidian_tool,
        agent_knowledge_loader=agent_knowledge_loader,
    )
    jt = JTAgent(_make_client("jt") if not args.dry_run else client)
    researcher = ResearcherAgent(
        _make_client("researcher") if not args.dry_run else client,
        obsidian_tool=obsidian_tool,
    )
    reviewer = ReviewerAgent(_make_client("reviewer") if not args.dry_run else client)
    writer = WriterAgent(
        _make_client("writer") if not args.dry_run else client,
        voice_loader=voice_loader,
    )
    backend = BackendAgent(_make_client("backend") if not args.dry_run else client)
    frontend = FrontendAgent(_make_client("frontend") if not args.dry_run else client)
    qa = QAAgent(_make_client("qa") if not args.dry_run else client)
    advisor = AdvisorAgent(_make_client("advisor") if not args.dry_run else client)
    advisor_router = AdvisorRouterAgent(
        _make_client("advisor_router") if not args.dry_run else client
    )
    strategy_systems_adv = StrategySystemsAdvisorAgent(
        _make_client("strategy_systems_advisor") if not args.dry_run else client
    )
    leadership_culture_adv = LeadershipCultureAdvisorAgent(
        _make_client("leadership_culture_advisor") if not args.dry_run else client
    )
    communication_influence_adv = CommunicationInfluenceAdvisorAgent(
        _make_client("communication_influence_advisor") if not args.dry_run else client
    )
    growth_mindset_adv = GrowthMindsetAdvisorAgent(
        _make_client("growth_mindset_advisor") if not args.dry_run else client
    )
    entrepreneur_execution_adv = EntrepreneurExecutionAdvisorAgent(
        _make_client("entrepreneur_execution_advisor") if not args.dry_run else client
    )

    graph = build_graph(
        chief_of_staff,
        jt,
        researcher,
        reviewer,
        writer,
        backend,
        frontend,
        qa,
        advisor=advisor,
        advisor_router=advisor_router,
        strategy_systems_advisor=strategy_systems_adv,
        leadership_culture_advisor=leadership_culture_adv,
        communication_influence_advisor=communication_influence_adv,
        growth_mindset_advisor=growth_mindset_adv,
        entrepreneur_execution_advisor=entrepreneur_execution_adv,
    )

    # ── Session persistence ───────────────────────────────────────────────────
    # Try to restore the prior session from disk. Falls back to empty memory
    # gracefully if the file doesn't exist or is malformed.
    _session_file = settings.session_file if not args.dry_run else ""
    _loaded = load_session(_session_file) if _session_file else None
    if _loaded:
        print(f"\n[session] Restored prior session: {describe_session(_loaded)}")
        print(f"[session] File: {_session_file}\n")
        session_project_memory = _loaded
    else:
        if _session_file and not args.dry_run:
            print(f"\n[session] No prior session found — starting fresh.")
            print(f"[session] Will save to: {_session_file}\n")
        session_project_memory = empty_project_memory()

    pending_task = " ".join(args.task).strip()

    while True:
        task = pending_task
        if not task:
            try:
                task = input("Enter your task: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nNo task provided. Exiting.\n")
                return
        if not task:
            print("\nNo task provided. Exiting.\n")
            return

        # ── CoS Intake ────────────────────────────────────────────────────────
        # Run a pre-dispatch intake analysis before touching the graph.
        # The CoS reads the task, vault context, and agent knowledge layer,
        # then either confirms it's ready to proceed or asks 2-3 targeted
        # questions. This keeps clarification upfront rather than buried at
        # the end of a pipeline run.
        if not args.dry_run:
            branch_hint = "build" if args.dev_pod else ("brainstorm" if args.advisor else "plan")
            print("\n[CoS] Running intake analysis...\n")
            try:
                intake = chief_of_staff.intake(task, branch_hint=branch_hint)
                print(f"[CoS] {intake['analysis']}")
                print(f"[CoS] Suggested approach: {intake['suggested_approach']}")
                if not intake["ready"]:
                    print("\n[CoS] Before I send this to the team, a few things I need from you:\n")
                    for i, q in enumerate(intake["questions"], 1):
                        print(f"  {i}. {q}")
                    try:
                        clarification = input("\nYour response: ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print("\nIntake cancelled. Exiting.\n")
                        return
                    if clarification:
                        task = f"{task}\n\n[CoS intake clarification]: {clarification}"
                        print()
                else:
                    print("[CoS] Ready to dispatch.\n")
            except Exception as exc:  # noqa: BLE001
                print(f"[CoS] Intake unavailable ({exc}), proceeding directly.\n")

        jt_requested, jt_mode = detect_jt_request(task=task, cli_jt=args.jt, cli_mode=args.jt_mode)
        # CLI branch flags are forwarded as hints — CoS reads them but makes the
        # final routing call.  Hard overrides are kept for backward compat: if
        # --dev-pod or --advisor is explicit, they still force the first sub-task.
        branch_hint = "build" if args.dev_pod else ("brainstorm" if args.advisor else "plan")
        dev_pod_requested = args.dev_pod
        advisor_pod_requested = args.advisor
        print(f"JT requested (CLI): {jt_requested}")
        print(f"JT mode (CLI): {jt_mode}")
        print(f"Branch hint (CLI): {branch_hint}")
        if args.web_search:
            print("[tools] Web search enabled for Researcher.")

        initial_state: SharedState = {
            "user_task": task,
            "status": "received",
            "dry_run": args.dry_run,
            "debug": args.debug,
            "web_search_enabled": args.web_search,
            "jt_requested": jt_requested,
            "jt_mode": jt_mode,
            "dev_pod_requested": dev_pod_requested,
            "advisor_pod_requested": advisor_pod_requested,
            "branch_hint": branch_hint,
            "task_plan": [],
            "current_subtask_index": 0,
            "subtask_results": [],
            "jt_feedback": [],
            "jt_rewrite": None,
            "jt_findings": None,
            "current_run": {
                "objective": "",
                "deliverable_type": "",
                "open_questions": [],
                "latest_draft": "",
                "latest_approved_output": "",
            },
            "project_memory": session_project_memory,
            "files_requested": file_read_result["files_requested"],
            "files_read": file_read_result["files_read"],
            "files_skipped": file_read_result["files_skipped"],
            "skip_reasons": file_read_result["skip_reasons"],
            "model_metadata": {
                "file_contents": file_read_result["file_contents"],
            },
        }

        try:
            result = graph.invoke(initial_state)
        except AuthenticationError:
            print(
                "\nAuthentication failed: your OpenAI API key appears invalid.\n"
                "Check OPENAI_API_KEY in .env and try again.\n"
            )
            return
        except RateLimitError as e:
            message = str(e).lower()
            if "insufficient_quota" in message:
                print(
                    "\nOpenAI request failed: your project appears to be out of quota.\n"
                    "Check billing/usage limits in OpenAI Platform, then try again.\n"
                )
            else:
                print("\nOpenAI rate limit reached. Please wait a moment and try again.\n")
            return

        # ── Sub-task continuation loop ────────────────────────────────────────
        # If the CoS decomposed the task into a plan, iterate through remaining
        # sub-tasks. Intermediate sub-tasks auto-approve (dry_run=True in state
        # only affects human_review_node — real API calls still run normally).
        # The final sub-task goes through normal human review.
        task_plan = result.get("task_plan", [])
        if task_plan and len(task_plan) > 1:
            subtask_results: list[dict] = []
            current_index = 0

            while current_index + 1 < len(task_plan):
                subtask_output = result.get("final_output", "")
                subtask_results.append({
                    "id": task_plan[current_index].get("id", str(current_index + 1)),
                    "description": task_plan[current_index].get("description", ""),
                    "branch": task_plan[current_index].get("branch", "plan"),
                    "output": subtask_output,
                })

                current_index += 1
                next_subtask = task_plan[current_index]
                total = len(task_plan)
                is_last = current_index == total - 1

                print(
                    f"\n[task_plan] Sub-task {current_index}/{total} done. "
                    f"Starting sub-task {current_index + 1}/{total}: "
                    f"{next_subtask.get('description', '')[:80]}\n"
                )

                # Carry forward memory with prior sub-task's approved output so
                # the next agent knows what was just produced.
                updated_memory = normalize_project_memory(result.get("project_memory"))
                updated_memory = {
                    **updated_memory,
                    "latest_approved_output": subtask_output,
                }

                next_state: SharedState = {
                    **initial_state,
                    "user_task": next_subtask.get("description", ""),
                    "status": "received",
                    # Auto-approve all but the final sub-task at human_review_node.
                    "dry_run": False if is_last else True,
                    "work_order": next_subtask.get("work_order", {}),
                    "dev_pod_requested": next_subtask.get("branch") == "build",
                    "advisor_pod_requested": next_subtask.get("branch") == "brainstorm",
                    "branch_hint": next_subtask.get("branch", "plan"),
                    "task_plan": task_plan,
                    "current_subtask_index": current_index,
                    "subtask_results": subtask_results,
                    "project_memory": updated_memory,
                    # Clear per-run output state.
                    "draft": "",
                    "final_output": "",
                    "jt_feedback": [],
                    "jt_rewrite": None,
                    "jt_findings": None,
                    "review_feedback": [],
                    "auto_redraft_count": 0,
                    "chief_redraft_count": 0,
                    "model_metadata": {
                        "file_contents": file_read_result["file_contents"],
                    },
                }

                try:
                    result = graph.invoke(next_state)
                except (AuthenticationError, RateLimitError) as e:
                    print(f"\n[task_plan] Sub-task {current_index + 1} failed: {e}\n")
                    break

                # Save progress after each completed sub-task.
                inter_memory = normalize_project_memory(result.get("project_memory"))
                if _session_file:
                    save_session(inter_memory, _session_file)
                    print(f"[session] Sub-task {current_index + 1} saved.")

            # Print sub-task plan summary before the final output block.
            if subtask_results:
                print("\n=== Task Plan Summary ===")
                for sr in subtask_results:
                    print(f"  [{sr['branch']}] {sr['description'][:70]}")
                    preview = (sr["output"] or "").replace("\n", " ")[:120]
                    print(f"    → {preview}...")
                print(f"  [{task_plan[-1].get('branch', 'plan')}] "
                      f"{task_plan[-1].get('description', '')[:70]} ← final (see below)")
                print("========================\n")

        session_project_memory = normalize_project_memory(result.get("project_memory"))

        # Persist to disk so the next session can pick up where this one left off.
        if _session_file:
            save_session(session_project_memory, _session_file)
            print(f"[session] Saved: {describe_session(session_project_memory)}")

        print("\n=== Final Output ===\n")
        print(result.get("final_output", "(no final output produced)"))
        print("\n====================\n")
        print(f"Status: {result.get('status', 'unknown')}")
        if args.dry_run:
            print("Mode: DRY RUN (no OpenAI calls)")

        file_summary = result.get("file_read_summary")
        if file_summary:
            print(f"File read summary: {file_summary}")

        print("\n=== Session Project Memory ===")
        print(f"- current_objective: {session_project_memory.get('current_objective', '')}")
        print(f"- active_deliverable_type: {session_project_memory.get('active_deliverable_type', '')}")
        print(f"- open_questions: {session_project_memory.get('open_questions', [])}")
        print(f"- latest_draft: {session_project_memory.get('latest_draft', '')}")
        print(f"- latest_approved_output: {session_project_memory.get('latest_approved_output', '')}")
        print("==============================\n")

        node_timings = result.get("model_metadata", {}).get("node_timings_ms", {})
        if node_timings:
            print("\n=== Node Timing Summary (ms) ===")
            for node_name, values in node_timings.items():
                count = len(values)
                total_ms = sum(values)
                avg_ms = total_ms / count if count else 0.0
                print(f"- {node_name}: calls={count}, total={total_ms:.1f}, avg={avg_ms:.1f}")
            print("================================\n")

        if args.task:
            return

        try:
            continue_session = input("Run another task in this local session? [y/N]: ").strip().lower() == "y"
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not continue_session:
            return
        pending_task = ""


if __name__ == "__main__":
    main()
