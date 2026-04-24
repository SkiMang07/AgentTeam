from __future__ import annotations

import json
from pathlib import Path

from app.state import SharedState, normalize_project_memory
from tools.local_file_reader import build_evidence_bundle
from tools.obsidian_context import ObsidianContextTool
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "researcher.md"

# Web search tool declaration for OpenAI Responses API
WEB_SEARCH_TOOL = [{"type": "web_search_preview"}]


class ResearcherAgent:
    def __init__(
        self,
        client: ResponsesClient,
        obsidian_tool: ObsidianContextTool | None = None,
    ) -> None:
        self._client = client
        self._obsidian_tool = obsidian_tool
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        work_order = state.get("work_order", {})
        project_memory = normalize_project_memory(state.get("project_memory"))
        evidence_bundle = self._load_structured_evidence(state)
        evidence_block = self._render_evidence_block(evidence_bundle)
        required_structures = state.get("required_structures", [])
        required_structures_block = (
            json.dumps(required_structures, indent=2)
            if isinstance(required_structures, list) and required_structures
            else "[]"
        )
        has_file_evidence = bool(evidence_bundle)

        # Load Obsidian vault context for this task
        obsidian_block = self._load_obsidian_context(state["user_task"])

        # Decide whether to use web search:
        # Only when explicitly enabled via --web-search flag, research is needed,
        # and no local file evidence has already been provided.
        research_needed = work_order.get("research_needed", True)
        web_search_enabled = state.get("web_search_enabled", False)
        use_web_search = web_search_enabled and research_needed and not has_file_evidence

        user_prompt = (
            "Extract facts and gaps for the Chief of Staff work order. Return strict JSON with keys: facts, gaps. "
            "Both must be arrays of short strings.\n"
            "Priority order for sourcing facts:\n"
            "  1. Local file evidence (if provided) — treat as ground truth.\n"
            "  2. Obsidian vault context — treat as reliable background from Andrew's second brain.\n"
            "  3. Web search results (if search was enabled) — use for current best practices, "
            "external data, and anything not covered by local sources.\n"
            "When local file evidence is provided, prefer it over web results for project-specific facts.\n"
            "Call out gaps clearly when sources do not cover required facts.\n\n"
            f"Current task:\n{state['user_task']}\n\n"
            f"Work order objective: {work_order.get('objective', '')}\n"
            f"Work order deliverable_type: {work_order.get('deliverable_type', '')}\n"
            f"Work order success_criteria: {work_order.get('success_criteria', [])}\n"
            f"Work order open_questions: {work_order.get('open_questions', [])}\n\n"
            f"Obsidian vault context (Andrew's second brain — use as primary background knowledge):\n"
            f"{obsidian_block}\n\n"
            f"Current local file evidence:\n"
            f"- Files read: {state.get('files_read', [])}\n"
            f"Local file evidence available: {has_file_evidence}\n"
            f"Structured local file evidence:\n{evidence_block}\n\n"
            f"Required structures extracted from files (binding contracts):\n{required_structures_block}\n\n"
            f"Web search enabled for this run: {use_web_search}\n\n"
            "Continuity memory (context only; not default evidence):\n"
            f"- current_objective: {project_memory.get('current_objective', '')}\n"
            f"- active_deliverable_type: {project_memory.get('active_deliverable_type', '')}\n"
            f"- open_questions: {project_memory.get('open_questions', [])}\n"
            f"- latest_approved_output_present: {bool(project_memory.get('latest_approved_output', '').strip())}"
        )

        # Use web search tool when appropriate
        if use_web_search:
            raw = self._client.ask_with_tools(
                system_prompt=self._prompt,
                user_prompt=user_prompt,
                tools=WEB_SEARCH_TOOL,
            )
        else:
            raw = self._client.ask(
                system_prompt=self._prompt,
                user_prompt=user_prompt,
            )

        data = self._normalize_output(self._safe_parse(raw))
        facts = data["facts"]
        gaps = data["gaps"]

        return {
            **state,
            "research_facts": facts,
            "research_gaps": gaps,
            "approved_facts": facts,
            "status": "researched",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "researcher_raw": raw,
                "researcher_web_search_used": use_web_search,
            },
        }

    def _load_obsidian_context(self, task: str) -> str:
        """Load vault context for the given task; return a prompt-ready block."""
        if self._obsidian_tool is None or not self._obsidian_tool.available:
            return "(Obsidian vault not configured)"
        try:
            context = self._obsidian_tool.load(task)
            return ObsidianContextTool.render_for_prompt(context)
        except Exception as exc:  # noqa: BLE001
            return f"(Obsidian context unavailable: {exc})"

    @staticmethod
    def _load_structured_evidence(state: SharedState) -> list[dict[str, list[str] | str]]:
        model_metadata = state.get("model_metadata", {})
        if not isinstance(model_metadata, dict):
            return []
        file_contents = model_metadata.get("file_contents", {})
        if not isinstance(file_contents, dict):
            return []
        return build_evidence_bundle(file_contents)

    @staticmethod
    def _render_evidence_block(evidence_bundle: list[dict[str, list[str] | str]]) -> str:
        lines: list[str] = []
        for item in evidence_bundle:
            file_path = item.get("file_path", "")
            evidence_points = item.get("evidence_points", [])
            lines.append(f"- file: {file_path}")
            if isinstance(evidence_points, list):
                for point in evidence_points:
                    if isinstance(point, str):
                        lines.append(f"  - {point}")
        return "\n".join(lines) if lines else "- (no local file evidence loaded)"

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        # Web search responses return prose first, then JSON — extract it
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Try to find embedded JSON object
        import re
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        # If the model returned prose (common with web search), wrap it as facts
        if raw.strip():
            lines = [line.strip("- •*").strip() for line in raw.splitlines() if line.strip()]
            facts = [line for line in lines if len(line) > 10]
            return {"facts": facts[:20], "gaps": ["Web search returned prose; structured JSON not parsed."]}
        return {"facts": [], "gaps": ["Failed to parse researcher output"]}

    @staticmethod
    def _normalize_output(data: dict) -> dict:
        notes: list[str] = []

        facts = data.get("facts")
        if not isinstance(facts, list) or not all(isinstance(item, str) for item in facts):
            facts = []
            notes.append("Validation note: normalized invalid facts to an empty list.")

        gaps = data.get("gaps")
        if not isinstance(gaps, list) or not all(isinstance(item, str) for item in gaps):
            gaps = []
            notes.append("Validation note: normalized invalid gaps to an empty list.")

        if notes:
            gaps = [*gaps, *notes]

        return {**data, "facts": facts, "gaps": gaps}
