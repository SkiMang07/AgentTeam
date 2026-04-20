# Agent Team Project Plan

## Goal
Build a useful local multi agent workflow that can handle grounded project work with optional JT challenge, while keeping v1 narrow and inspectable.

## Current status
Phase 1 complete
Phase 2 in progress

## Principles
- Keep v1 narrow
- No new business integrations yet
- No extra core agents beyond current design
- Human review remains required
- Prefer boring, reliable progress over cleverness

## Workstreams

### 1. Core workflow hardening
- [x] Get local CLI scaffold running
- [x] Confirm repo and environment setup
- [ ] Tighten shared state shape
- [ ] Improve Chief of Staff routing
- [ ] Add structured reviewer findings
- [ ] Add Chief of Staff final validation pass

### 2. Optional JT challenge stage
- [ ] Add `jt_requested` state flag
- [ ] Add JT prompt file
- [ ] Add JT node or review mode
- [ ] Route JT only when explicitly requested
- [ ] Return JT findings to Chief of Staff

### 3. Local file context
- [ ] Define allowed local file inputs
- [ ] Add local file reader
- [ ] Add evidence extraction step
- [ ] Ground writer output in retrieved context
- [ ] Add evidence checks in reviewer

### 4. Project memory
- [ ] Define project memory schema
- [ ] Save current objective
- [ ] Save open questions
- [ ] Save latest approved output

## Current next task
Issue #1: Add JT state fields and routing

## Notes
Update this file when tasks are completed or priorities change.
