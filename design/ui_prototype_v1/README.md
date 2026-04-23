# UI Prototype v1 (Static, Branch-Aware Design)

This folder contains a **standalone static HTML prototype** for a premium dark, desktop-first AgentTeam operator console.

## How to open

1. From the repository root, open `design/ui_prototype_v1/index.html` directly in a browser.
2. No dependencies, build tools, frameworks, or backend services are required.

## Architecture reflected in this prototype

The prototype reflects the current three-branch model after Chief of Staff routing:

- **Plan**
- **Build**
- **Brainstorm**

Layout stays branch-aware and mode-specific:

- **Left:** Request Setup
- **Middle:** Run Orchestration
- **Right:** Workspace

## Request Setup controls (design-only)

### Plan mode

- Uses **Output format** (renamed from artifact language in setup controls).
- Output format options are:
  - Chat
  - Executive Brief
  - Decision Memo
  - Project Plan
  - Let CoS decide
  - Determine during planning
- JT remains a **Plan-only** modifier.
- Local files and web search controls remain visible only in Plan mode.
- Memory is represented as continuity/status, not as a backend feature toggle.

### Build mode

- Replaces older invented “build target” mock options with a more structured request shape:
  - Request
  - Build surface
  - Output type
  - Constraints
  - Acceptance notes
- These controls are intentionally **future-facing UI contract design**, not a claim that runtime currently accepts this typed form.

### Brainstorm mode

- Adds an **Output format** control with:
  - Chat
  - Let CoS decide
  - Determine during planning
- Keeps Brainstorm tied to advisor clusters + synthesis rather than introducing new artifact classes.
- Plan and Brainstorm can explicitly return **Chat** in the prototype.

## Orchestration rail and workspace (design-only)

### Plan rail

1. Chief of Staff
2. Researcher / Evidence
3. Writer
4. JT (when enabled)
5. Reviewer
6. Chief of Staff final check
7. Human Review

JT remains positioned after Writer and before Reviewer.

### Build rail

1. Pod Entry (system state)
2. Backend
3. Frontend
4. QA
5. QA revision loop (optional system state)
6. Assemble (system state)
7. Human Review

### Brainstorm rail

1. Advisor Entry (system state)
2. Strategy and Systems
3. Leadership and Culture
4. Communication and Influence
5. Growth and Mindset
6. Entrepreneur and Execution
7. Advisor Synthesis
8. Human Review

Workspace tabs remain branch-specific:

- **Plan:** Draft, Artifact Preview, Reviewer Findings, Approval
- **Build:** Backend Output, Frontend Output, QA Findings, Assembled Output, Approval
- **Brainstorm:** Advisor Synthesis, Cluster Notes, Approval

## Scope and honesty notes

- This remains a **design-only static prototype**.
- It is **not wired to runtime graph/state execution**.
- It does **not** imply downloadable artifact generation.
- Python runtime code is unchanged.
