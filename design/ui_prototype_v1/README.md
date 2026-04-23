# UI Prototype v1 (Static Design Exploration)

This folder contains a **standalone static HTML prototype** for a premium dark, desktop-first Agent Team operator console.

## How to open

1. From the repository root, open `design/ui_prototype_v1/index.html` directly in a browser.
2. No dependencies, build tools, or backend services are required.

## What is included

- Three-panel desktop layout kept in place:
  - **Prompt** panel for real run setup controls
  - **Agent Team** panel for orchestration state and route details
  - **Output** panel for multi-mode artifact and review states
- Prompt panel reflects current repo capabilities with mocked controls for:
  - request input, deliverable type, tone, optional context
  - selected local files
  - JT stage toggle, web search toggle, and session-memory indicator
- Agent Team panel models explicit workflow state:
  - active agent focus card
  - route summary
  - research-needed, JT-requested, reviewer and human review status
  - rail + compact cards for Chief of Staff, Researcher, Writer, Reviewer, JT, Human Review
- Output panel supports mocked output modes aligned to current artifacts:
  - plain text response state
  - structured artifact previews for **Executive Brief**, **Decision Memo**, and **Project Plan**
  - downloadable file card state
  - reviewer/QC overlay state (approve vs revise)
  - explicit human approval controls

## Mock interactions (vanilla JS)

- **Run Agent Team** triggers a simulated run progression.
- Clicking an agent card updates the focus detail panel.
- Artifact subtabs switch between Executive Brief, Decision Memo, and Project Plan previews.
- Reviewer state can be toggled between approve and revise outcomes.
- Human review controls update approval status/log state.

## Scope notes

- This is design-only and intentionally not wired to backend state or APIs.
- Existing Python app/backend behavior is unchanged.
- The prototype remains file-system runnable and framework-free.
