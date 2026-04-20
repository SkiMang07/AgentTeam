from __future__ import annotations

import re


def detect_jt_request(task: str, cli_jt: bool = False, cli_mode: str | None = None) -> tuple[bool, str | None]:
    mode = _normalize_mode(cli_mode)
    if mode is not None:
        return True, mode

    text = task.strip()
    lowered = text.lower()

    mode = _mode_from_text(lowered)
    if mode is not None:
        return True, mode

    explicit_request = any(
        marker in lowered
        for marker in (
            "jt requested: true",
            "run jt",
            "use jt",
            "as jt",
        )
    )
    jt_requested = bool(cli_jt) or explicit_request
    return jt_requested, None


def _mode_from_text(lowered_task: str) -> str | None:
    patterns = (
        r"\bjt mode\s*:\s*([a-z_][a-z0-9_]*)",
        r"\buse jt\s+([a-z_][a-z0-9_]*)\s+mode\b",
        r"\bjt\s+([a-z_][a-z0-9_]*)\s+mode\b",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered_task)
        if match:
            return _normalize_mode(match.group(1))
    return None


def _normalize_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    normalized = mode.strip().lower()
    return normalized or None
