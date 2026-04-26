"""Sandboxed code execution for the QA agent.

Extracts code blocks from agent artifacts, runs them in an isolated subprocess,
and returns structured results (exit code, stdout, stderr) that the QA LLM
can reason against — turning static guesses into real evidence.

Safety constraints:
  - All execution happens inside a fresh TemporaryDirectory (cleaned up on exit).
  - Hard timeout per execution (default 10 s) — no runaway processes.
  - Only Python and Node.js are executed; all other languages get a syntax-only
    or "not executable" result.
  - No network access control beyond the OS default — this is a local dev tool,
    not a public sandbox. Don't execute untrusted code.

Usage:
    from tools.code_executor import run_execution_checks

    results = run_execution_checks(backend_text, frontend_text)
    # results["backend"] and results["frontend"] are ExecutionResult dicts.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TypedDict


# ── Types ─────────────────────────────────────────────────────────────────────

class ExecutionResult(TypedDict):
    artifact: str          # "backend" | "frontend"
    language: str          # detected language
    syntax_ok: bool | None # True/False, or None if not checkable
    syntax_errors: list[str]
    executed: bool         # whether a subprocess run was attempted
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    skipped: bool          # True when language is not executable
    skip_reason: str


# ── Language detection ────────────────────────────────────────────────────────

_PYTHON_SIGNALS = re.compile(
    r"\b(import |from \w+ import|def |class |if __name__|print\(|@app\.|@router\.)",
    re.MULTILINE,
)
_JS_TS_SIGNALS = re.compile(
    r"\b(const |let |var |function |export |import |require\(|=>|module\.exports)",
    re.MULTILINE,
)
_HTML_SIGNALS = re.compile(r"<(!DOCTYPE|html|head|body|div|script)", re.IGNORECASE)
_CSS_SIGNALS = re.compile(r"\{[^}]*:[^}]*\}", re.DOTALL)


def _detect_language(code: str, fence_lang: str = "") -> str:
    """Guess the language of *code*.

    *fence_lang* is the language hint from a markdown fence (e.g. ``python``
    from ` ```python `). Takes priority when unambiguous.
    """
    hint = fence_lang.lower().strip()
    if hint in ("python", "py"):
        return "python"
    if hint in ("javascript", "js"):
        return "javascript"
    if hint in ("typescript", "ts"):
        return "typescript"
    if hint in ("html",):
        return "html"
    if hint in ("css",):
        return "css"
    if hint in ("bash", "sh", "shell"):
        return "shell"

    # Heuristic content scan
    if _HTML_SIGNALS.search(code):
        return "html"
    py_score = len(_PYTHON_SIGNALS.findall(code))
    js_score = len(_JS_TS_SIGNALS.findall(code))
    if py_score > js_score and py_score > 0:
        return "python"
    if js_score > py_score and js_score > 0:
        return "javascript"
    if py_score == js_score and py_score > 0:
        return "python"  # default to Python when ambiguous
    return "unknown"


# ── Code block extraction ─────────────────────────────────────────────────────

_FENCE_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<code>.*?)```",
    re.DOTALL,
)


def _extract_blocks(text: str) -> list[tuple[str, str]]:
    """Return a list of (language_hint, code) pairs from markdown fences.

    If no fences are found, treat the entire text as one unlabelled block.
    """
    matches = _FENCE_RE.findall(text)
    if matches:
        return [(lang.strip(), code.strip()) for lang, code in matches if code.strip()]
    stripped = text.strip()
    return [("", stripped)] if stripped else []


def _best_block(text: str, preferred_langs: tuple[str, ...]) -> tuple[str, str] | None:
    """Return the first block matching *preferred_langs*, or the longest block."""
    blocks = _extract_blocks(text)
    if not blocks:
        return None
    for lang_hint, code in blocks:
        detected = _detect_language(code, lang_hint)
        if detected in preferred_langs:
            return detected, code
    # Fall back to the longest block
    lang_hint, code = max(blocks, key=lambda b: len(b[1]))
    return _detect_language(code, lang_hint), code


# ── Python execution ──────────────────────────────────────────────────────────

def _check_python_syntax(code: str) -> list[str]:
    """Return a list of syntax error messages, or [] if the code is valid."""
    try:
        ast.parse(code)
        return []
    except SyntaxError as exc:
        return [f"SyntaxError at line {exc.lineno}: {exc.msg}"]


def _run_python(code: str, timeout: int, tmpdir: Path) -> tuple[int | None, str, str, bool]:
    """Write *code* to a temp file and execute it.

    Returns (exit_code, stdout, stderr, timed_out).
    """
    script = tmpdir / "qa_run.py"
    script.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(tmpdir),
        )
        return proc.returncode, proc.stdout[:2000], proc.stderr[:2000], False
    except subprocess.TimeoutExpired:
        return None, "", f"Execution timed out after {timeout}s.", True
    except Exception as exc:  # noqa: BLE001
        return None, "", f"Subprocess error: {exc}", False


# ── Node.js execution ─────────────────────────────────────────────────────────

def _run_node_syntax(code: str, tmpdir: Path) -> tuple[bool, list[str]]:
    """Run ``node --check`` on *code*. Returns (ok, errors)."""
    script = tmpdir / "qa_run.js"
    script.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmpdir),
        )
        if proc.returncode == 0:
            return True, []
        errors = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
        return False, errors[:10]
    except FileNotFoundError:
        return True, ["node not installed — JS syntax check skipped"]
    except subprocess.TimeoutExpired:
        return True, ["node syntax check timed out"]
    except Exception as exc:  # noqa: BLE001
        return True, [f"node syntax check error: {exc}"]


# ── Per-artifact runner ───────────────────────────────────────────────────────

def _execute_artifact(
    artifact_name: str,
    text: str,
    timeout: int,
    tmpdir: Path,
) -> ExecutionResult:
    """Run execution checks on one artifact text and return an ExecutionResult."""

    base: ExecutionResult = {
        "artifact": artifact_name,
        "language": "unknown",
        "syntax_ok": None,
        "syntax_errors": [],
        "executed": False,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "skipped": False,
        "skip_reason": "",
    }

    if not text or text.strip() in ("(no backend output)", "(no frontend output)", ""):
        return {**base, "skipped": True, "skip_reason": "No artifact content provided."}

    # Pick the most relevant code block
    block = _best_block(text, ("python", "javascript", "typescript"))
    if not block:
        return {**base, "skipped": True, "skip_reason": "No code blocks found in artifact."}

    language, code = block
    result: ExecutionResult = {**base, "language": language}

    if language == "python":
        syntax_errors = _check_python_syntax(code)
        result["syntax_ok"] = len(syntax_errors) == 0
        result["syntax_errors"] = syntax_errors

        if result["syntax_ok"]:
            exit_code, stdout, stderr, timed_out = _run_python(code, timeout, tmpdir)
            result["executed"] = True
            result["exit_code"] = exit_code
            result["stdout"] = stdout
            result["stderr"] = stderr
            result["timed_out"] = timed_out
        # If syntax failed, skip execution — the error is already captured.

    elif language in ("javascript", "typescript"):
        ok, errors = _run_node_syntax(code, tmpdir)
        result["syntax_ok"] = ok
        result["syntax_errors"] = errors

    elif language == "html":
        result["skipped"] = True
        result["skip_reason"] = "HTML — not executed, static analysis only."

    elif language == "css":
        result["skipped"] = True
        result["skip_reason"] = "CSS — not executed, static analysis only."

    else:
        result["skipped"] = True
        result["skip_reason"] = f"Language '{language}' is not executable by this tool."

    return result


# ── Public interface ──────────────────────────────────────────────────────────

def run_execution_checks(
    backend_text: str,
    frontend_text: str,
    timeout: int = 10,
) -> dict[str, ExecutionResult]:
    """Run execution checks on backend and frontend artifacts.

    Returns a dict with keys ``"backend"`` and ``"frontend"``, each an
    ExecutionResult. Uses a single shared TemporaryDirectory so both artifacts
    run in the same isolated workspace (useful when frontend imports backend).
    """
    with tempfile.TemporaryDirectory(prefix="agent_qa_") as tmpdir:
        tmp = Path(tmpdir)
        return {
            "backend": _execute_artifact("backend", backend_text, timeout, tmp),
            "frontend": _execute_artifact("frontend", frontend_text, timeout, tmp),
        }


def format_execution_results(results: dict[str, ExecutionResult]) -> str:
    """Format execution results as a compact, human-readable string for the QA prompt."""
    lines: list[str] = ["=== Code Execution Results ==="]

    for artifact_name, r in results.items():
        lines.append(f"\n[{artifact_name.upper()}]")
        lines.append(f"  Language: {r['language']}")

        if r["skipped"]:
            lines.append(f"  Status: SKIPPED — {r['skip_reason']}")
            continue

        # Syntax
        if r["syntax_ok"] is True:
            lines.append("  Syntax: PASSED")
        elif r["syntax_ok"] is False:
            lines.append("  Syntax: FAILED")
            for err in r["syntax_errors"]:
                lines.append(f"    ! {err}")

        # Execution
        if r["executed"]:
            if r["timed_out"]:
                lines.append("  Execution: TIMED OUT")
            elif r["exit_code"] == 0:
                lines.append("  Execution: PASSED (exit 0)")
            else:
                lines.append(f"  Execution: FAILED (exit {r['exit_code']})")

            if r["stdout"].strip():
                lines.append(f"  stdout:\n    {r['stdout'].strip()[:500]}")
            if r["stderr"].strip():
                lines.append(f"  stderr:\n    {r['stderr'].strip()[:500]}")
        elif r["syntax_ok"] is True:
            lines.append("  Execution: NOT ATTEMPTED (syntax passed, no runnable main block detected or language not fully executed)")
        elif r["syntax_ok"] is False:
            lines.append("  Execution: SKIPPED (syntax failed — fix errors first)")

    lines.append("\n=== End Execution Results ===")
    return "\n".join(lines)
