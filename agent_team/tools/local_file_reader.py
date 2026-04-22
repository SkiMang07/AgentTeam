from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TypedDict

ALLOWED_EXTENSIONS = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".csv"}
DEFAULT_MAX_DEPTH = 1
DEFAULT_MAX_FILES = 8
MAX_CHARS_PER_FILE = 4000


class FileReadResult(TypedDict):
    files_requested: list[str]
    files_read: list[str]
    files_skipped: list[str]
    skip_reasons: dict[str, str]
    file_contents: dict[str, str]


class EvidenceItem(TypedDict):
    file_path: str
    evidence_points: list[str]



def load_local_files(
    paths: list[str],
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files: int = DEFAULT_MAX_FILES,
) -> FileReadResult:
    files_requested = [str(Path(raw).expanduser()) for raw in paths if str(raw).strip()]
    files_read: list[str] = []
    files_skipped: list[str] = []
    skip_reasons: dict[str, str] = {}
    file_contents: dict[str, str] = {}

    if not files_requested:
        return {
            "files_requested": [],
            "files_read": [],
            "files_skipped": [],
            "skip_reasons": {},
            "file_contents": {},
        }

    candidate_files: list[Path] = []

    for raw in files_requested:
        path = Path(raw)
        if not path.exists():
            files_skipped.append(str(path))
            skip_reasons[str(path)] = "path_not_found"
            continue

        if path.is_file():
            candidate_files.append(path)
            continue

        if not path.is_dir():
            files_skipped.append(str(path))
            skip_reasons[str(path)] = "unsupported_path_type"
            continue

        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            relative_depth = len(child.relative_to(path).parts) - 1
            if relative_depth > max_depth:
                files_skipped.append(str(child))
                skip_reasons[str(child)] = f"exceeds_max_depth_{max_depth}"
                continue
            candidate_files.append(child)

    for file_path in sorted(candidate_files):
        file_key = str(file_path)
        if len(files_read) >= max_files:
            files_skipped.append(file_key)
            skip_reasons[file_key] = f"exceeds_max_files_{max_files}"
            continue

        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            files_skipped.append(file_key)
            skip_reasons[file_key] = "unsupported_extension"
            continue

        try:
            file_contents[file_key] = _read_text_friendly_file(file_path)
            files_read.append(file_key)
        except UnicodeDecodeError:
            files_skipped.append(file_key)
            skip_reasons[file_key] = "decode_error"
        except ValueError:
            files_skipped.append(file_key)
            skip_reasons[file_key] = "parse_error"
        except OSError:
            files_skipped.append(file_key)
            skip_reasons[file_key] = "read_error"

    return {
        "files_requested": files_requested,
        "files_read": files_read,
        "files_skipped": files_skipped,
        "skip_reasons": skip_reasons,
        "file_contents": file_contents,
    }


def build_evidence_bundle(file_contents: dict[str, str]) -> list[EvidenceItem]:
    bundle: list[EvidenceItem] = []
    for file_path, content in file_contents.items():
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        points: list[str] = []

        if lines:
            points.append(f"First line: {lines[0][:200]}")
        if len(lines) > 1:
            points.append(f"Second line: {lines[1][:200]}")

        points.append(f"Total non-empty lines: {len(lines)}")

        bundle.append(
            {
                "file_path": file_path,
                "evidence_points": points,
            }
        )
    return bundle


def _read_text_friendly_file(file_path: Path) -> str:
    if file_path.suffix.lower() == ".json":
        raw = file_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        normalized = json.dumps(parsed, indent=2, ensure_ascii=False)
        return normalized[:MAX_CHARS_PER_FILE]

    if file_path.suffix.lower() == ".csv":
        rows: list[str] = []
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            for idx, row in enumerate(reader):
                rows.append(", ".join(cell.strip() for cell in row))
                if idx >= 20:
                    break
        return "\n".join(rows)[:MAX_CHARS_PER_FILE]

    return file_path.read_text(encoding="utf-8")[:MAX_CHARS_PER_FILE]
