from __future__ import annotations

from pathlib import Path


class VoiceLoader:
    """
    Loads Andrew's voice/style guide from a local file and exposes it for
    injection into the Writer's system prompt.

    Gracefully returns an empty string when the path is not configured or
    the file does not exist — so the Writer degrades cleanly rather than
    failing hard.
    """

    def __init__(self, voice_file_path: str) -> None:
        self._path = Path(voice_file_path).expanduser().resolve() if voice_file_path.strip() else None

    @property
    def available(self) -> bool:
        return bool(self._path and self._path.exists() and self._path.is_file())

    def load(self) -> str:
        """Return voice/style guide content, or empty string if unavailable."""
        if not self.available or self._path is None:
            return ""
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def load_for_prompt(self) -> str:
        """
        Return a prompt-ready block with a header, or an empty string so
        callers can append it without introducing blank sections.
        """
        content = self.load()
        if not content.strip():
            return ""
        return f"## Voice and Style Guide\n\n{content.strip()}"
