from __future__ import annotations

import argparse

from openai import AuthenticationError, RateLimitError

from agents.chief_of_staff import ChiefOfStaffAgent
from agents.researcher import ResearcherAgent
from agents.writer import WriterAgent
from app.config import get_settings
from app.graph import build_graph
from app.state import SharedState
from tools.openai_client import ResponsesClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local multi-agent CLI")
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

    try:
        settings = get_settings()
    except ValueError as e:
        print(f"\nConfiguration error: {e}\n")
        return

    client = ResponsesClient(settings)

    chief_of_staff = ChiefOfStaffAgent(client)
    researcher = ResearcherAgent(client)
    writer = WriterAgent(client)

    graph = build_graph(chief_of_staff, researcher, writer)
    initial_state: SharedState = {"user_task": task, "status": "received"}

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


if __name__ == "__main__":
    main()
