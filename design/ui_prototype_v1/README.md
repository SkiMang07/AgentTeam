# UI Prototype v1 (Static, Workstream-Aware Design)

This folder contains a **standalone static HTML prototype** for a dark, desktop-first AgentTeam operator console.

## How to open

1. From the repository root, open `design/ui_prototype_v1/index.html` directly in a browser.
2. No dependencies, frameworks, build tools, or backend services are required.

## Architecture reflected in this prototype

The UI reflects the current three real branches after Chief of Staff routing:

- **Plan**
- **Build**
- **Brainstorm**

Layout remains:

- **Left:** Request Setup
- **Middle:** Run Orchestration
- **Right:** Workspace

## What changed in this revision

### 1) Single-select mode → multi-select workstreams

Top-level selection is now **Requested branches** with multi-select options:

- Brainstorm
- Plan
- Build

This allows design-time branch composition in one session.

### 2) Added design sequence preview

A **Design sequence preview** appears under Requested branches.

Examples represented in the UI:

- Brainstorm
- Plan
- Build
- Brainstorm → Plan
- Plan → Build
- Brainstorm → Plan → Build

Important: this sequence is a **design direction preview**, not runtime orchestration behavior today.

### 3) Request Setup updates by branch

#### Plan section

- Uses **Output format** (not artifact-type language).
- Options:
  - Chat
  - Executive Brief
  - Decision Memo
  - Project Plan
  - Let CoS decide
  - Determine during planning
- JT remains Plan-only and optional.
- Local files + web search controls are shown only when Plan is selected.
- Memory is shown as continuity/status, not as a fake backend switch.

#### Build section

- Replaced older invented target dropdown with more honest structured inputs:
  - Request
  - Build surface
  - Output type
  - Constraints
  - Acceptance notes
- Treated explicitly as **future-facing static contract design**.

#### Brainstorm section

- Added **Output format** control with:
  - Chat
  - Let CoS decide
  - Determine during planning
- Keeps Brainstorm tied to advisor-cluster flow plus synthesis.

Plan and Brainstorm now both explicitly support **Chat** output in the prototype.

### 4) Orchestration view: branch-grounded + composite preview

Middle panel keeps branch structures grounded in current architecture:

- **Plan:** Chief of Staff → Researcher / Evidence → Writer → JT (optional) → Reviewer → Chief of Staff Final Check → Human Review
- **Build:** Pod Entry → Backend → Frontend → QA → optional QA revision loop → Assemble → Human Review
- **Brainstorm:** Advisor Entry → 5 advisor clusters → Advisor Synthesis → Human Review

For multi-select workstreams, the panel renders one coherent composite sequence with explicit handoff system states between branches. This is marked as design-only.

### 5) Workspace now includes follow-on interaction design

Right panel still supports branch-aware output views, and now also includes a follow-on interaction area for:

- Ask a follow up
- Refine this
- Rerun from this output
- Continue from this result

For multi-workstream selection, workspace copy models output handoff into the next branch in sequence within the same session.

## Honesty / scope notes

- This is still a **design-only static prototype**.
- It is **not wired** to runtime Python graph/state execution.
- It does **not** claim real compound orchestration support yet.
- It does **not** claim persistent workspace storage.
- It does **not** claim downloadable artifact generation.
