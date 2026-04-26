"""Session persistence — save and load ProjectMemory across CLI and server restarts.

Design:
- Saves the five ProjectMemory fields to a single JSON file with a ``saved_at``
  timestamp.
- Load is always non-fatal: missing file, malformed JSON, or schema drift all
  return None (caller falls back to empty_project_memory).
- The file path is configured via Settings.session_file (see config.py).

Usage:
    from tools.session_persistence import save_session, load_session

    memory = load_session(settings.session_file)   # at startup
    save_session(memory, settings.session_file)     # after each run
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.state import ProjectMemory, normalize_project_memory

log = logging.getLogger(__name__)

# Fields we persist — exactly the ProjectMemory keys.
_MEMORY_KEYS = {
    "current_objective",
    "active_deliverable_type",
    "open_questions",
    "latest_draft",
    "latest_approved_output",
}


def save_session(memory: ProjectMemory, session_file: str) -> None:
    """Write *memory* to *session_file* as JSON.

    Creates parent directories if needed. Overwrites the file on every call
    (the file is always the latest state, not a log).

    Failures are logged but never re-raised — a persistence hiccup should
    never crash a run.
    """
    if not session_file:
        return

    path = Path(session_file)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "saved_at": datetime.now(tz=timezone.utc).isoformat(),
            **{k: memory.get(k, "") for k in _MEMORY_KEYS},  # type: ignore[misc]
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        log.debug("[session] Saved to %s", session_file)
    except Exception as exc:  # noqa: BLE001
        log.warning("[session] Could not save session to %s: %s", session_file, exc)


def load_session(session_file: str) -> ProjectMemory | None:
    """Load and validate the session JSON from *session_file*.

    Returns a validated ProjectMemory on success, or None if the file doesn't
    exist, can't be parsed, or is missing required keys.

    The caller should fall back to ``empty_project_memory()`` on None.
    """
    if not session_file:
        return None

    path = Path(session_file)
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("[session] Could not parse session file %s: %s", session_file, exc)
        return None

    if not isinstance(raw, dict):
        return None

    # Strip the metadata key before normalizing — normalize_project_memory only
    # cares about the five ProjectMemory fields.
    raw.pop("saved_at", None)

    memory = normalize_project_memory(raw)

    # Only return if at least one meaningful field is populated — avoids
    # treating an all-empty saved file as a useful prior session.
    has_content = any(
        memory.get(k) for k in ("current_objective", "latest_approved_output", "latest_draft")
    )
    if not has_content:
        return None

    return memory


def describe_session(memory: ProjectMemory) -> str:
    """Return a compact one-line summary of a loaded session for startup logging."""
    parts: list[str] = []

    objective = memory.get("current_objective", "").strip()
    if objective:
        preview = objective[:80] + ("…" if len(objective) > 80 else "")
        parts.append(f"objective='{preview}'")

    deliverable = memory.get("active_deliverable_type", "").strip()
    if deliverable:
        parts.append(f"type={deliverable}")

    questions = memory.get("open_questions", [])
    if questions:
        parts.append(f"open_questions={len(questions)}")

    approved = memory.get("latest_approved_output", "").strip()
    if approved:
        parts.append(f"approved_output={len(approved)} chars")

    return ", ".join(parts) if parts else "(empty)"
