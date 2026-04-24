"""OpenAI function-tool schemas and handler factories for AgentTeam agents.

Usage:
    from tools.agent_tools import CREATE_FILE_TOOL, make_file_tool_handlers
    from tools.file_writer import FileWriter

    fw = FileWriter("/output/run_abc")
    handlers = make_file_tool_handlers(fw)

    text, calls = client.ask_with_function_tools(
        system_prompt=...,
        user_prompt=...,
        tools=[CREATE_FILE_TOOL],
        tool_handlers=handlers,
    )
"""
from __future__ import annotations

from typing import Any, Callable

# ── Tool schemas (OpenAI Responses API function-calling format) ───────────────

CREATE_FILE_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "create_file",
    "description": (
        "Create a file in the session output directory. "
        "Use this whenever the deliverable should persist as a downloadable file — "
        "spec docs, developer plans, API contracts, project briefs, reports, "
        "conversation flow maps, feature backlogs, or any structured content that "
        "a reader will want to open and reference later. "
        "You may call this tool multiple times to create multiple files "
        "(e.g. one file per section or component). "
        "Use subdirectories to organise related files (e.g. 'plans/api_contract.md'). "
        "After creating files, return a concise inline summary of what was produced."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": (
                    "Relative path for the file within the output directory. "
                    "Examples: 'spec.md', 'plans/developer_handoff.md', 'api_contract.json'. "
                    "Allowed extensions: "
                    ".md .txt .json .yaml .yml .csv .py .html .js .ts .jsx .tsx"
                ),
            },
            "content": {
                "type": "string",
                "description": "Complete file content to write. Do not truncate.",
            },
            "description": {
                "type": "string",
                "description": (
                    "One-line description of this file's purpose "
                    "(shown in the run summary)."
                ),
            },
        },
        "required": ["filename", "content", "description"],
        "additionalProperties": False,
    },
}

# ── Handler factories ─────────────────────────────────────────────────────────


def make_file_tool_handlers(file_writer: Any) -> dict[str, Callable]:
    """Return a tool-name → callable mapping bound to *file_writer*.

    The returned dict is passed directly to
    ``ResponsesClient.ask_with_function_tools(tool_handlers=...)``.
    """

    def create_file(filename: str, content: str, description: str = "") -> str:  # noqa: ARG001
        """Write *content* to *filename* in the sandbox and return a status string."""
        try:
            path = file_writer.write_file(filename, content)
            return f"ok: written to {path}"
        except Exception as exc:  # noqa: BLE001
            return f"error: {exc}"

    return {
        "create_file": create_file,
    }
