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

    chief_of_staff = ChiefOfStaffAgent(
        client,
        obsidian_tool=obsidian_tool,
        agent_knowledge_loader=agent_knowledge_loader,
    )
    jt = JTAgent(client)
    researcher = ResearcherAgent(client, obsidian_tool=obsidian_tool)
    reviewer = ReviewerAgent(client)
    writer = WriterAgent(client, voice_loader=voice_loader)
    backend = BackendAgent(client)
    frontend = FrontendAgent(client)
    qa = QAAgent(client)
    advisor = AdvisorAgent(client)
    advisor_router = AdvisorRouterAgent(client)
    strategy_systems_adv = StrategySystemsAdvisorAgent(client)
    leadership_culture_adv = LeadershipCultureAdvisorAgent(client)
    communication_influence_adv = CommunicationInfluenceAdvisorAgent(client)
    growth_mindset_adv = GrowthMindsetAdvisorAgent(client)
    entrepreneur_execution_adv = EntrepreneurExecutionAdvisorAgent(client)

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
        dev_pod_requested = args.dev_pod
        advisor_pod_requested = args.advisor
        print(f"JT requested (CLI): {jt_requested}")
        print(f"JT mode (CLI): {jt_mode}")
        print(f"Dev pod requested (CLI): {dev_pod_requested}")
        print(f"Advisor pod requested (CLI): {advisor_pod_requested}")
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

        session_project_memory = normalize_project_memory(result.get("project_memory"))

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
