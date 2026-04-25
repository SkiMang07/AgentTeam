"""
VaultSessionLoader — session-level vault orientation tool.

Two-tier design that scales to any vault size without an LLM call:

  Tier 1 — Full content
    • All explicitly pinned folders (user-specified, always included)
    • Top FULL_TIER_RECENT most recently modified non-pinned folders
    • Each entry: up to MAX_CHARS_PER_FILE characters of raw CLAUDE.md content

  Tier 2 — Compact index
    • Every remaining CLAUDE.md in the vault
    • Each entry: ~120 chars — first heading + status tag + opening description
    • Ensures CoS knows every project exists even without full detail

Result: CoS always has complete vault coverage. Active/pinned work gets full
context; the rest is an index CoS can reference by name. Scales to 500+ folders.
"""
from __future__ import annotations

import re
from pathlib import Path

CLAUDE_FILE_NAME = "CLAUDE.md"

# Tier 1 — full-content budget
FULL_TIER_RECENT = 15      # non-pinned folders by recency that get full content
MAX_CHARS_PER_FILE = 1800  # per full-tier entry

# Tier 2 — compact index
MAX_COMPACT_CHARS = 130    # per compact entry

# Hard ceiling on how many files we scan (avoids pathological vaults)
MAX_FILES_SCANNED = 500
MAX_VAULT_DEPTH = 10


class VaultSessionLoader:
    """
    Scans a vault directory for all CLAUDE.md files and returns a two-tier
    context block for the Chief of Staff session orientation.
    """

    def __init__(self, vault_path: str) -> None:
        self._vault_path = Path(vault_path).expanduser().resolve()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._vault_path.exists() and self._vault_path.is_dir()

    @property
    def vault_path(self) -> str:
        return str(self._vault_path)

    @property
    def vault_name(self) -> str:
        return self._vault_path.name

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self) -> dict:
        """
        Scan the vault and return all CLAUDE.md entries with metadata.

        Returns:
          {
            "available": bool,
            "vault_name": str,
            "files_found": int,
            "entries": [
              {
                "relative_path": str,
                "content": str,       # full content (truncated)
                "mtime": float,       # for recency sorting
              },
              ...
            ]
          }
        """
        if not self.available:
            return {
                "available": False,
                "vault_name": self.vault_name,
                "files_found": 0,
                "entries": [],
            }

        all_files: list[Path] = []
        for claude_file in self._vault_path.rglob(CLAUDE_FILE_NAME):
            if not claude_file.is_file():
                continue
            try:
                depth = len(claude_file.relative_to(self._vault_path).parts)
                if depth <= MAX_VAULT_DEPTH + 1:
                    all_files.append(claude_file)
            except ValueError:
                continue
            if len(all_files) >= MAX_FILES_SCANNED:
                break

        # Most recently modified first
        all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        entries: list[dict] = []
        for claude_file in all_files:
            try:
                content = claude_file.read_text(encoding="utf-8").strip()
                if not content:
                    continue
                rel = claude_file.parent.relative_to(self._vault_path)
                relative_path = str(rel) if str(rel) != "." else "(vault root)"
                entries.append({
                    "relative_path": relative_path,
                    "content": content[:MAX_CHARS_PER_FILE],
                    "mtime": claude_file.stat().st_mtime,
                })
            except (OSError, UnicodeDecodeError):
                continue

        return {
            "available": True,
            "vault_name": self.vault_name,
            "files_found": len(all_files),
            "entries": entries,
        }

    def render_for_prompt(
        self,
        context: dict | None = None,
        pinned_folders: list[str] | None = None,
    ) -> str:
        """
        Render vault context as a two-tier, prompt-ready block.

        Args:
          context:        Pre-loaded result from load(). Loaded fresh if None.
          pinned_folders: Folder names/substrings that always get full content.
                          Case-insensitive substring match against relative_path.
        """
        if context is None:
            context = self.load()

        if not context.get("available"):
            return "(Vault not configured or not found)"

        entries: list[dict] = context.get("entries", [])
        if not entries:
            return "(No CLAUDE.md files found in vault)"

        pins = [p.lower().strip() for p in (pinned_folders or []) if p.strip()]

        # ── Assign tiers ──────────────────────────────────────────────────────
        pinned_entries: list[dict] = []
        recent_entries: list[dict] = []
        compact_entries: list[dict] = []

        # Entries are already sorted by mtime (most recent first).
        # Pinned matches are pulled out first; remaining fill recent then compact.
        remaining: list[dict] = []
        for entry in entries:
            if pins and _is_pinned(entry["relative_path"], pins):
                pinned_entries.append(entry)
            else:
                remaining.append(entry)

        for entry in remaining:
            if len(recent_entries) < FULL_TIER_RECENT:
                recent_entries.append(entry)
            else:
                compact_entries.append(entry)

        # ── Render ────────────────────────────────────────────────────────────
        vault_name = context.get("vault_name", "vault")
        total = context.get("files_found", len(entries))
        full_count = len(pinned_entries) + len(recent_entries)
        compact_count = len(compact_entries)

        lines: list[str] = [
            f"Vault: {vault_name} — {total} CLAUDE.md files found",
            f"Full context: {full_count} folders "
            f"({len(pinned_entries)} pinned + {len(recent_entries)} most recent)",
        ]
        if compact_count:
            lines.append(f"Compact index: {compact_count} additional folders")
        lines.append("")

        # Pinned (full)
        if pinned_entries:
            lines.append("── PINNED FOLDERS (full context) ──────────────────")
            for entry in pinned_entries:
                lines.append(f"\n=== {entry['relative_path']}/CLAUDE.md ===")
                lines.append(entry["content"])

        # Recent non-pinned (full)
        if recent_entries:
            lines.append("\n── RECENT FOLDERS (full context) ──────────────────")
            for entry in recent_entries:
                lines.append(f"\n=== {entry['relative_path']}/CLAUDE.md ===")
                lines.append(entry["content"])

        # Compact index
        if compact_entries:
            lines.append(
                "\n── VAULT INDEX (remaining folders — compact summaries) ──"
            )
            lines.append(
                "These folders exist in your vault. CoS can reference them "
                "by name; full context loads if the task is relevant.\n"
            )
            for entry in compact_entries:
                summary = _compact_summary(entry["content"])
                lines.append(f"• {entry['relative_path']} — {summary}")

        return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_pinned(relative_path: str, pins: list[str]) -> bool:
    """True if any pin string is a case-insensitive substring of relative_path."""
    path_lower = relative_path.lower()
    return any(pin in path_lower for pin in pins)


def _compact_summary(content: str) -> str:
    """
    Extract a compact single-line summary from CLAUDE.md content.

    Pulls: first heading → status tag → first substantive description line.
    Result is capped at MAX_COMPACT_CHARS characters.
    """
    lines = [ln.rstrip() for ln in content.splitlines() if ln.strip()]

    heading = ""
    status = ""
    description = ""

    for line in lines:
        stripped = line.strip()

        # First H1 or H2 heading
        if not heading:
            m = re.match(r"^#{1,2}\s+(.+)", stripped)
            if m:
                heading = m.group(1).strip()
                continue

        # Status tag — matches "Status: X", "**Status:** X", "status: X"
        if not status:
            m = re.match(r"\*{0,2}status:?\*{0,2}\s*:?\s*(.+)", stripped, re.IGNORECASE)
            if m:
                val = m.group(1).strip().lstrip("*").strip()
                if val and len(val) < 50:
                    status = val
                continue

        # First substantive description line (not a heading, not a list bullet)
        if not description:
            if (
                not stripped.startswith("#")
                and not stripped.startswith("-")
                and not stripped.startswith("*")
                and not stripped.startswith(">")
                and len(stripped) > 25
            ):
                description = stripped

    parts: list[str] = []
    if heading:
        parts.append(heading)
    if status:
        parts.append(f"({status})")
    if description and description.lower() != heading.lower():
        # Keep description short so the compact line stays compact
        parts.append(description[:80])

    result = " — ".join(parts) if parts else content[:80]
    return result[:MAX_COMPACT_CHARS]
