from __future__ import annotations

import argparse

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
        task = input("Enter your task: ").strip()

    if not task:
        raise ValueError("A task is required.")

    settings = get_settings()
    client = ResponsesClient(settings)

    chief_of_staff = ChiefOfStaffAgent(client)
    researcher = ResearcherAgent(client)
    writer = WriterAgent(client)

    graph = build_graph(chief_of_staff, researcher, writer)
    initial_state: SharedState = {"user_task": task, "status": "received"}
    result = graph.invoke(initial_state)

    print("\n=== Final Output ===\n")
    print(result.get("final_output", "(no final output produced)"))
    print("\n====================\n")
    print(f"Status: {result.get('status', 'unknown')}")


if __name__ == "__main__":
    main()
