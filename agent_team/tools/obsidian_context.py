from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.openai_client import ResponsesClient

CLAUDE_FILE_NAME = "CLAUDE.md"
MAX_VAULT_MAP_SUMMARY_CHARS = 600
MAX_FOLDER_CONTEXT_FILE_SNIPPETS = 5
MAX_FOLDER_CONTEXT_SNIPPET_CHARS = 300
MAX_FOLDERS_TO_LOAD = 3
VAULT_WALK_MAX_DEPTH = 2
ALLOWED_CONTEXT_EXTENSIONS = {".md", ".txt"}


class ObsidianContextTool:
    """
    Navigates an Obsidian vault intelligently for a given task.

    Two-pass design:
      1. Walk vault to VAULT_WALK_MAX_DEPTH, collect all CLAUDE.md files and
         build a compact vault map.
      2. Ask the LLM which folders are most relevant to the current task.
      3. Load full CLAUDE.md content + top-level file snippets from those folders.

    Gracefully returns empty context when the vault path is not configured or
    does not exist.
    """

    def __init__(self, vault_path: str, client: ResponsesClient) -> None:
        self._vault_path = Path(vault_path).expanduser().resolve()
        self._client = client

    @property
    def available(self) -> bool:
        return self._vault_path.exists() and self._vault_path.is_dir()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, task: str) -> dict:
        """
        Return structured vault context relevant to *task*.

        Shape:
          {
            "available": bool,
            "vault_map": [...],          # all discovered CLAUDE.md entries
            "selected_contexts": [...],  # full content for relevant folders
          }
        """
        if not self.available:
            return {"available": False, "vault_map": [], "selected_contexts": []}

        vault_map = self._build_vault_map()
        if not vault_map:
            return {"available": True, "vault_map": [], "selected_contexts": []}

        selected_paths = self._select_relevant_folders(task, vault_map)
        selected_contexts = [
            ctx
            for raw_path in selected_paths
            if (ctx := self._load_folder_context(Path(raw_path))) is not None
        ]

        return {
            "available": True,
            "vault_map": vault_map,
            "selected_contexts": selected_contexts,
        }

    @staticmethod
    def render_for_prompt(context: dict) -> str:
        """Convert a context dict to a readable block for prompt injection."""
        if not context.get("available"):
            return "(Obsidian vault not configured)"

        selected = context.get("selected_contexts", [])
        if not selected:
            return "(No relevant vault context found for this task)"

        blocks: list[str] = []
        for folder_ctx in selected:
            folder_name = folder_ctx.get("folder", "unknown")
            claude_md = folder_ctx.get("claude_md", "").strip()
            file_snippets = folder_ctx.get("file_snippets", [])

            lines = [f"=== Vault folder: {folder_name} ==="]
            if claude_md:
                lines.append(claude_md)
            if file_snippets:
                lines.append("\nTop-level files in this folder:")
                for snippet in file_snippets:
                    lines.append(f"  [{snippet['name']}]")
                    if snippet.get("snippet"):
                        lines.append(f"  {snippet['snippet'][:200].strip()}")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    # ------------------------------------------------------------------
    # Vault map construction
    # ------------------------------------------------------------------

    def _build_vault_map(self) -> list[dict]:
        entries: list[dict] = []
        self._walk_for_claude_files(
            directory=self._vault_path,
            depth=0,
            entries=entries,
            max_depth=VAULT_WALK_MAX_DEPTH,
        )
        return entries

    def _walk_for_claude_files(
        self,
        directory: Path,
        depth: int,
        entries: list[dict],
        max_depth: int,
    ) -> None:
        try:
            claude_file = directory / CLAUDE_FILE_NAME
            if claude_file.exists() and claude_file.is_file():
                entries.append({
                    "path": str(directory),
                    "name": directory.name if depth > 0 else "(vault root)",
                    "depth": depth,
                    "summary": _read_truncated(claude_file, MAX_VAULT_MAP_SUMMARY_CHARS),
                })
        except (PermissionError, OSError):
            return

        if depth >= max_depth:
            return

        try:
            subdirs = sorted(
                [d for d in directory.iterdir() if d.is_dir() and not d.name.startswith(".")],
                key=lambda p: p.name,
            )
        except (PermissionError, OSError):
            return

        for subdir in subdirs:
            self._walk_for_claude_files(
                directory=subdir,
                depth=depth + 1,
                entries=entries,
                max_depth=max_depth,
            )

    # ------------------------------------------------------------------
    # Folder selection via LLM
    # ------------------------------------------------------------------

    def _select_relevant_folders(self, task: str, vault_map: list[dict]) -> list[str]:
        map_lines: list[str] = []
        for entry in vault_map:
            indent = "  " * entry["depth"]
            map_lines.append(f"{indent}Folder: {entry['name']}  (path: {entry['path']})")
            # Include first 3 non-empty lines of the CLAUDE.md summary
            for line in entry["summary"].splitlines()[:3]:
                if line.strip():
                    map_lines.append(f"{indent}  > {line.strip()}")

        vault_map_text = "\n".join(map_lines)

        response = self._client.ask(
            system_prompt=(
                "You are a knowledge navigator for an Obsidian vault. "
                "Given a task and a vault folder map (folder names with brief CLAUDE.md summaries), "
                "select the folder paths most relevant to the task. "
                "Return strict JSON only: {\"relevant_paths\": [\"path1\", \"path2\"]}. "
                "Select at most 3 paths. "
                "Only include paths that appear verbatim in the vault map. "
                "Return an empty array if nothing is clearly relevant."
            ),
            user_prompt=(
                f"Task: {task}\n\n"
                f"Vault folder map:\n{vault_map_text}"
            ),
        )

        valid_paths = {entry["path"] for entry in vault_map}
        return _parse_relevant_paths(response, valid_paths, vault_map)

    # ------------------------------------------------------------------
    # Full folder context loading
    # ------------------------------------------------------------------

    def _load_folder_context(self, folder_path: Path) -> dict | None:
        if not folder_path.exists() or not folder_path.is_dir():
            return None

        claude_file = folder_path / CLAUDE_FILE_NAME
        claude_content = ""
        if claude_file.exists() and claude_file.is_file():
            try:
                claude_content = claude_file.read_text(encoding="utf-8")
            except OSError:
                pass

        file_snippets: list[dict] = []
        try:
            for f in sorted(folder_path.iterdir()):
                if (
                    f.is_file()
                    and f.suffix in ALLOWED_CONTEXT_EXTENSIONS
                    and f.name != CLAUDE_FILE_NAME
                    and not f.name.startswith(".")
                ):
                    snippet = _read_truncated(f, MAX_FOLDER_CONTEXT_SNIPPET_CHARS)
                    if snippet.strip():
                        file_snippets.append({"name": f.name, "snippet": snippet})
                    if len(file_snippets) >= MAX_FOLDER_CONTEXT_FILE_SNIPPETS:
                        break
        except PermissionError:
            pass

        if not claude_content and not file_snippets:
            return None

        return {
            "folder": folder_path.name,
            "path": str(folder_path),
            "claude_md": claude_content,
            "file_snippets": file_snippets,
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _read_truncated(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
        return text[:max_chars] if len(text) > max_chars else text
    except OSError:
        return ""


def _parse_relevant_paths(
    raw_response: str,
    valid_paths: set[str],
    vault_map: list[dict],
) -> list[str]:
    """Parse LLM folder-selection response; fall back gracefully on failure."""
    try:
        data = json.loads(raw_response)
        paths = data.get("relevant_paths", [])
        if isinstance(paths, list):
            return [p for p in paths if isinstance(p, str) and p in valid_paths][:MAX_FOLDERS_TO_LOAD]
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback: return depth-1 folders up to the limit
    depth1 = [e["path"] for e in vault_map if e.get("depth") == 1]
    return depth1[:MAX_FOLDERS_TO_LOAD]
