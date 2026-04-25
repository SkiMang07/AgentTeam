from __future__ import annotations

from pathlib import Path

AGENT_DOCS_RELATIVE = "agent_team/agent_docs"
CLAUDE_FILE_NAME = "CLAUDE.md"
MAX_DESCRIPTOR_CHARS = 1500  # per agent — keeps total prompt size manageable


class AgentKnowledgeLoader:
    """
    Loads CLAUDE.md descriptor files from agent_team/agent_docs/.

    This is the CoS's always-on team knowledge layer — separate from the
    task-selective Obsidian vault context. Every intake and dispatch call
    loads this so the CoS knows what every agent does, when to route to it,
    and what it needs without having to rediscover this each time.
    """

    def __init__(self, vault_path: str) -> None:
        self._vault_path = Path(vault_path).expanduser().resolve()
        self._agent_docs = self._vault_path / AGENT_DOCS_RELATIVE

    @property
    def available(self) -> bool:
        return self._agent_docs.exists() and self._agent_docs.is_dir()

    def load_all(self) -> str:
        """
        Return all agent CLAUDE.md files as a formatted prompt block.

        Each descriptor is capped at MAX_DESCRIPTOR_CHARS to keep the
        total size manageable. The "What this agent is" and "When to route
        here" sections appear first in every file, so the most routing-
        relevant content is always within the cap.
        """
        if not self.available:
            return "(Agent knowledge layer not available — agent_docs folder not found)"

        blocks: list[str] = []
        try:
            agent_dirs = sorted(
                [d for d in self._agent_docs.iterdir() if d.is_dir()],
                key=lambda p: p.name,
            )
        except OSError:
            return "(Agent knowledge layer unavailable — could not read agent_docs)"

        for agent_dir in agent_dirs:
            claude_file = agent_dir / CLAUDE_FILE_NAME
            if not claude_file.exists():
                continue
            try:
                content = claude_file.read_text(encoding="utf-8")
                if len(content) > MAX_DESCRIPTOR_CHARS:
                    content = content[:MAX_DESCRIPTOR_CHARS] + "\n...(truncated)"
                blocks.append(f"--- Agent: {agent_dir.name} ---\n{content}")
            except OSError:
                continue

        if not blocks:
            return "(Agent knowledge layer empty — no CLAUDE.md files found in agent_docs)"

        header = (
            "AGENT TEAM KNOWLEDGE LAYER\n"
            "The following descriptors tell you what each agent does, when to route to it,\n"
            "what it needs, and what good output from it looks like.\n\n"
        )
        return header + "\n\n".join(blocks)

    def load_roster_summary(self) -> str:
        """
        Return a compact one-liner roster — useful for intake when full
        descriptors would be too heavy.
        """
        if not self.available:
            return "(Agent roster unavailable)"

        lines: list[str] = []
        try:
            agent_dirs = sorted(
                [d for d in self._agent_docs.iterdir() if d.is_dir()],
                key=lambda p: p.name,
            )
        except OSError:
            return "(Agent roster unavailable)"

        for agent_dir in agent_dirs:
            claude_file = agent_dir / CLAUDE_FILE_NAME
            if not claude_file.exists():
                continue
            try:
                content = claude_file.read_text(encoding="utf-8")
                # Extract first non-empty line after the h1 heading as the summary
                summary = ""
                past_heading = False
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        past_heading = True
                        continue
                    if past_heading and stripped and not stripped.startswith("#"):
                        summary = stripped
                        break
                lines.append(f"- {agent_dir.name}: {summary}")
            except OSError:
                continue

        if not lines:
            return "(Agent roster empty)"

        return "Available agents:\n" + "\n".join(lines)
