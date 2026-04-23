#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AgentTeam Tool Integration Test Runner
# Run from the AgentTeam repo root:  bash run_tests.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/agent_team"
VENV_PYTHON="$AGENT_DIR/.venv/bin/python"
OUTPUT_DIR="$SCRIPT_DIR/test_outputs"

mkdir -p "$OUTPUT_DIR"

if [[ ! -f "$VENV_PYTHON" ]]; then
  echo "ERROR: venv not found at $VENV_PYTHON — activate or rebuild it first."
  exit 1
fi

run_test() {
  local id="$1"
  local label="$2"
  local outfile="$OUTPUT_DIR/test${id}_output.txt"
  shift 2
  local cmd=("$@")

  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  TEST $id: $label"
  echo "  Command: python -m app.main ${cmd[*]}"
  echo "═══════════════════════════════════════════════════════"
  echo ""

  {
    echo "TEST $id: $label"
    echo "Command: python -m app.main ${cmd[*]}"
    echo "Run at: $(date)"
    echo ""
    echo "─── RAW OUTPUT ─────────────────────────────────────────"
  } > "$outfile"

  # Run from agent_team dir so relative imports work.
  # Pipe 'y' to auto-approve human review so the script runs unattended.
  (cd "$AGENT_DIR" && echo "y" | "$VENV_PYTHON" -m app.main "${cmd[@]}" 2>&1) | tee -a "$outfile"

  echo "" >> "$outfile"
  echo "─── END ─────────────────────────────────────────────────" >> "$outfile"

  echo ""
  echo "  → Saved to: $outfile"
}

echo ""
echo "AgentTeam Tool Integration Tests"
echo "$(date)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Obsidian-grounded task, no web search
# Checks: Does the CoS work order reflect vault context?
#         Does the draft sound like Andrew?
# ─────────────────────────────────────────────────────────────────────────────
run_test 1 "Vault context, no web search" \
  "Write a brief project status update for the AgentTeam multi-agent CLI — summarize what has been built so far, what the three new tools do (Obsidian context navigator, voice loader, and web search), and what the next milestone is"

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Same task, web search ON
# Checks: Does the Researcher surface external facts beyond vault knowledge?
#         Do web results meaningfully extend what vault + memory already knew?
# ─────────────────────────────────────────────────────────────────────────────
run_test 2 "Vault context + web search" \
  --web-search \
  "Write a brief project status update for the AgentTeam multi-agent CLI — summarize what has been built so far, what the three new tools do (Obsidian context navigator, voice loader, and web search), and what the next milestone is"

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Voice-only writing task (no research needed)
# Checks: Does the Writer match Andrew's voice without any coaching?
#         No Obsidian project context needed here — just a writing exercise.
# ─────────────────────────────────────────────────────────────────────────────
run_test 3 "Voice-only writing task" \
  "Write a short note (3-5 sentences) to my future self about why building a local multi-agent system matters — the kind of note I'd put in my Obsidian vault as a reminder when I'm in the weeds"

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  All tests complete. Outputs saved to:"
echo "  $OUTPUT_DIR/"
echo ""
echo "  test1_output.txt — vault context, no web search"
echo "  test2_output.txt — vault context + web search"
echo "  test3_output.txt — voice-only writing"
echo "═══════════════════════════════════════════════════════"
echo ""
