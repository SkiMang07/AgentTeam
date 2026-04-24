"""Sandboxed file writer for agent outputs.

All writes are restricted to a single sandbox directory, preventing agents
from reading or writing outside their designated output space for a given run.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Extensions agents are permitted to write.
ALLOWED_WRITE_EXTENSIONS = {
    ".md", ".txt", ".json", ".yaml", ".yml",
    ".csv", ".py", ".html", ".js", ".ts", ".jsx", ".tsx",
}


class FileWriterError(Exception):
    """Raised when a write is blocked by sandbox or extension policy."""


class FileWriter:
    """Write files safely within a sandboxed directory.

    Args:
        sandbox_root: Base directory for this run. All writes must resolve
            within this directory. Created automatically if it does not exist.

    Example:
        writer = FileWriter("/output/run_abc123")
        path = writer.write_file("spec.md", "# Product Spec\\n...")
        print(writer.files_created)   # ['/output/run_abc123/spec.md']
    """

    def __init__(self, sandbox_root: str | Path) -> None:
        self._root = Path(sandbox_root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._created: list[str] = []
        log.info("[file_writer] Sandbox initialized: %s", self._root)

    # ── Public properties ────────────────────────────────────────────────────

    @property
    def sandbox_root(self) -> str:
        return str(self._root)

    @property
    def files_created(self) -> list[str]:
        """Absolute paths of all files written in this session."""
        return list(self._created)

    # ── Core write API ───────────────────────────────────────────────────────

    def write_file(self, relative_path: str, content: str) -> str:
        """Write *content* to *relative_path* within the sandbox.

        Returns the absolute path of the written file.

        Raises:
            FileWriterError: If the resolved path escapes the sandbox or uses
                a disallowed extension.
        """
        target = (self._root / relative_path).resolve()

        # Security: path must stay within sandbox root.
        try:
            target.relative_to(self._root)
        except ValueError:
            raise FileWriterError(
                f"Path '{relative_path}' resolves outside sandbox '{self._root}'. "
                "Only relative paths within the sandbox are permitted."
            )

        # Extension whitelist (no extension = allowed, e.g. Makefile).
        suffix = target.suffix.lower()
        if suffix and suffix not in ALLOWED_WRITE_EXTENSIONS:
            raise FileWriterError(
                f"Extension '{suffix}' is not permitted. "
                f"Allowed: {sorted(ALLOWED_WRITE_EXTENSIONS)}"
            )

        # Create any needed parent directories, then write.
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        abs_path = str(target)
        self._created.append(abs_path)
        log.info("[file_writer] Wrote %d chars → %s", len(content), abs_path)
        return abs_path

    def make_dir(self, relative_path: str) -> str:
        """Create a directory within the sandbox.

        Returns the absolute path of the created directory.
        """
        target = (self._root / relative_path).resolve()
        try:
            target.relative_to(self._root)
        except ValueError:
            raise FileWriterError(
                f"Path '{relative_path}' resolves outside sandbox '{self._root}'."
            )
        target.mkdir(parents=True, exist_ok=True)
        return str(target)
