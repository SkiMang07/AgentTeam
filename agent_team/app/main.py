from __future__ import annotations

import argparse

from openai import AuthenticationError, RateLimitError

from agents.chief_of_staff import ChiefOfStaffAgent
from agents.jt import JTAgent
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.writer import WriterAgent
from app.config import get_settings
from app.graph import build_graph
from app.jt_request import detect_jt_request
from app.state import SharedState, empty_project_memory, normalize_project_memory
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
    parser.add_argument("task", type=str, nargs="*", help="Task for the agent team")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    file_read_result = load_local_files(args.files_path)

    if args.dry_run:
        print("\nMode: DRY RUN (no OpenAI calls)\n")
        client = DryRunResponsesClient()
        obsidian_tool: ObsidianContextTool | None = None
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
        else:
            obsidian_tool = None

        voice_loader = VoiceLoader(settings.voice_file_path)
        if voice_loader.available:
            print(f"[tools] Voice/style guide loaded: {settings.voice_file_path}")
        elif settings.voice_file_path:
            print(f"[tools] Warning: VOICE_FILE_PATH set but file not found: {settings.voice_file_path}")

    chief_of_staff = ChiefOfStaffAgent(client, obsidian_tool=obsidian_tool)
    jt = JTAgent(client)
    researcher = ResearcherAgent(client, obsidian_tool=obsidian_tool)
    reviewer = ReviewerAgent(client)
    writer = WriterAgent(client, voice_loader=voice_loader)

    graph = build_graph(chief_of_staff, jt, researcher, reviewer, writer)
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

        jt_requested, jt_mode = detect_jt_request(task=task, cli_jt=args.jt, cli_mode=args.jt_mode)
        print(f"JT requested (CLI): {jt_requested}")
        print(f"JT mode (CLI): {jt_mode}")
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
