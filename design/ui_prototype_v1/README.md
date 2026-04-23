# UI Prototype v1 (Static, Branch-Aware Design)

This folder contains a **standalone static HTML prototype** for a premium dark, desktop-first AgentTeam operator console.

## How to open

1. From the repository root, open `design/ui_prototype_v1/index.html` directly in a browser.
2. No dependencies, build tools, frameworks, or backend services are required.

## What changed in this version

The prototype now matches the live architecture in `agent_team/app/graph.py`, `agent_team/app/state.py`, and the current agent modules:

- The UI is explicitly **branch-aware** after Chief of Staff.
- Top-level mode choices are now:
  - **Plan**
  - **Build** (developer pod)
  - **Brainstorm** (advisor team)
- Layout is now aligned to the requested desktop model:
  - **Left:** Request Setup
  - **Middle:** Run Orchestration
  - **Right:** Workspace

## Branch mapping to current repo behavior

### Plan branch

Orchestration rail reflects the current plan path:

1. Chief of Staff
2. Researcher / Evidence
3. Writer
4. JT (only when enabled)
5. Reviewer
6. Chief of Staff final check
7. Human Review

Notes:
- JT is shown only in Plan and appears after Writer and before Reviewer.
- Memory is represented as continuity status (not as a generic runtime toggle).

### Build branch

Orchestration rail reflects the developer pod path:

1. Pod Entry (system state)
2. Backend
3. Frontend
4. QA
5. QA revision loop (optional system state)
6. Assemble (system state)
7. Human Review

Notes:
- Helper nodes are visually styled as **system states** rather than person-like agents.

### Brainstorm branch

Orchestration rail reflects the advisor pod path:

1. Advisor Entry (system state)
2. Strategy and Systems
3. Leadership and Culture
4. Communication and Influence
5. Growth and Mindset
6. Entrepreneur and Execution
7. Advisor Synthesis
8. Human Review

## Workspace behavior (design-only)

Workspace tabs are mode-specific:

- **Plan:** Draft, Artifact Preview, Reviewer Findings, Approval
- **Build:** Backend Output, Frontend Output, QA Findings, Assembled Output, Approval
- **Brainstorm:** Advisor Synthesis, Cluster Notes, Approval

Artifact previews are aligned to currently implemented template types:

- Executive Brief
- Decision Memo
- Project Plan

This prototype **does not imply downloadable runtime artifacts** and remains explicit that it is a design mock, not a wired UI.

## Scope notes

- Design-only static prototype; no backend wiring.
- Python code and runtime behavior are unchanged.
- No frameworks or build tooling were added.
