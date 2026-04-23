# UI Prototype v1 (Static Design Exploration)

This folder contains a **standalone static HTML prototype** for a premium, dark-themed Agent Team operator console.

## How to open

1. From the repository root, open `design/ui_prototype_v1/index.html` directly in a browser.
2. No dependencies, build tools, or backend services are required.

## What is included

- Three-panel desktop-first layout:
  - **Prompt** panel (job setup)
  - **Agent Team** panel (execution rail + step cards)
  - **Output** panel (response/artifact preview + review controls)
- Minimal vanilla JS interactions:
  - Mock run progression when **Run Agent Team** is pressed
  - Clickable agent cards
  - Output state switching between **Response** and **Artifact Preview**

## Scope notes

- This is design-only and intentionally not wired to backend state or APIs.
- Existing app behavior is unchanged.
