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


MAX_HEADINGS = 4
MAX_BULLETS = 6
MAX_SNIPPETS = 4
MAX_SNIPPET_CHARS = 180



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

        headings = _extract_headings(lines)
        bullets = _extract_bullets(lines)
        snippets = _extract_key_snippets(lines)

        points.append(f"Total non-empty lines: {len(lines)}")
        points.extend(headings)
        points.extend(bullets)
        points.extend(snippets)

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


def _extract_headings(lines: list[str]) -> list[str]:
    headings: list[str] = []
    for line in lines:
        if line.startswith("#"):
            normalized = line.lstrip("#").strip()
            if normalized:
                headings.append(f"Heading: {normalized[:MAX_SNIPPET_CHARS]}")
        if len(headings) >= MAX_HEADINGS:
            break
    return headings


def _extract_bullets(lines: list[str]) -> list[str]:
    bullets: list[str] = []
    for line in lines:
        if line.startswith(("- ", "* ")):
            normalized = line[2:].strip()
        elif _is_numbered_bullet(line):
            normalized = line.split(".", 1)[1].strip()
        else:
            continue
        if normalized:
            bullets.append(f"Bullet: {normalized[:MAX_SNIPPET_CHARS]}")
        if len(bullets) >= MAX_BULLETS:
            break
    return bullets


def _extract_key_snippets(lines: list[str]) -> list[str]:
    snippets: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line.startswith("#") or line.startswith(("- ", "* ")) or _is_numbered_bullet(line):
            continue
        normalized = " ".join(line.split())
        if len(normalized) < 45 or normalized in seen:
            continue
        seen.add(normalized)
        snippets.append(f"Snippet: {normalized[:MAX_SNIPPET_CHARS]}")
        if len(snippets) >= MAX_SNIPPETS:
            break
    return snippets


def _is_numbered_bullet(line: str) -> bool:
    parts = line.split(".", 1)
    if len(parts) != 2:
        return False
    return parts[0].isdigit()
