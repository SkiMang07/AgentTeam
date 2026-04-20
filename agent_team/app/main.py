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
from app.state import SharedState
from tools.openai_client import DryRunResponsesClient, ResponsesClient


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
    parser.add_argument("task", type=str, nargs="*", help="Task for the agent team")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task = " ".join(args.task).strip()
    if not task:
        try:
            task = input("Enter your task: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNo task provided. Exiting.\n")
            return

    if not task:
        raise ValueError("A task is required.")

    if args.dry_run:
        print("\nMode: DRY RUN (no OpenAI calls)\n")
        client = DryRunResponsesClient()
    else:
        try:
            settings = get_settings()
        except ValueError as e:
            print(f"\nConfiguration error: {e}\n")
            return
        client = ResponsesClient(settings)

    chief_of_staff = ChiefOfStaffAgent(client)
    jt = JTAgent(client)
    researcher = ResearcherAgent(client)
    reviewer = ReviewerAgent(client)
    writer = WriterAgent(client)

    graph = build_graph(chief_of_staff, jt, researcher, reviewer, writer)
    jt_requested = args.jt or bool(args.jt_mode)
    print(f"JT requested (CLI): {jt_requested}")
    print(f"JT mode (CLI): {args.jt_mode}")
    initial_state: SharedState = {
        "user_task": task,
        "status": "received",
        "dry_run": args.dry_run,
        "jt_requested": jt_requested,
        "jt_mode": args.jt_mode,
        "jt_findings": None,
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

    print("\n=== Final Output ===\n")
    print(result.get("final_output", "(no final output produced)"))
    print("\n====================\n")
    print(f"Status: {result.get('status', 'unknown')}")
    if args.dry_run:
        print("Mode: DRY RUN (no OpenAI calls)")

    node_timings = result.get("model_metadata", {}).get("node_timings_ms", {})
    if node_timings:
        print("\n=== Node Timing Summary (ms) ===")
        for node_name, values in node_timings.items():
            count = len(values)
            total_ms = sum(values)
            avg_ms = total_ms / count if count else 0.0
            print(f"- {node_name}: calls={count}, total={total_ms:.1f}, avg={avg_ms:.1f}")
        print("================================\n")


if __name__ == "__main__":
    main()
