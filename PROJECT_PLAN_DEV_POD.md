# Agent Team — Phase 3: Developer Pod

## Goal

Extend AgentTeam with a developer pod: a Frontend, Backend, and QA agent sub-team that handles code tasks end-to-end, runs an internal code→QA→revision loop, and hands finished drafts to human review. The pod keeps the same human-review gate as the rest of the pipeline and is invoked only when explicitly requested.

## Current status

**Phase:** Phase 3 — Developer Pod  
**State:** Implementation complete. Dry run and live run both passed. Display bug fixed. Branch ready to merge.  
**Next action:** Merge `gallant-knuth-a59ace` branch → confirm JT still works on non-pod tasks → run AgriWebb task.

## Locked decisions

These are not open for re-discussion in implementation sessions.

| Question | Decision |
|---|---|
| Execution model | Review-only. QA reads and critiques code; does not execute it. No sandbox required. |
| Definition of done | Working drafts Andrew refines. Success = significantly less coding time, not deploy-ready output. |
| Invocation | `--dev-pod` CLI flag + CoS detection on deliverable_type / task language. Mirrors JT pattern exactly. |
| Context source | Pod works from work order + `pod_task_brief` CoS writes before routing. CoS is the context layer; pod agents are pure code producers. QA flags any context gaps in findings. |
| Human review | Remains the final gate. Pod loop runs before it, not instead of it. |
| Revision cap | Max 2 internal pod revision cycles before escalating to human review regardless of QA verdict. |
| Agent order | Backend runs first. Frontend runs after Backend so it can see the API contract. QA reviews both. |
| Loop replacement | Pod replaces the researcher→writer loop for code tasks. Pod's assembled output lands in `draft`; `human_review` handles it as normal. |

## Architecture

### New state fields (additions to `SharedState`)

```python
dev_pod_requested: NotRequired[bool]           # mirrors jt_requested
pod_task_brief:    NotRequired[str]            # CoS-written spec for the pod
pod_artifacts:     NotRequired[dict[str, str]] # filename → code content
pod_qa_findings:   NotRequired[list[str]]      # QA's issues list
pod_qa_verdict:    NotRequired[Literal["pass", "revise"]]
pod_revision_count: NotRequired[int]           # loop guard
```

### New `ChiefWorkOrder` field

```python
dev_pod_requested: bool
```

### New graph nodes

| Node | Role |
|---|---|
| `pod_entry` | CoS writes `pod_task_brief` — a tighter spec with file/function targets. Routes to Backend. |
| `pod_backend` | Generates backend code artifacts (API, data layer, integrations). |
| `pod_frontend` | Generates frontend code artifacts. Runs after Backend so it can reference the API contract. |
| `pod_qa` | Reviews all artifacts against the brief. Returns `verdict` (pass/revise) + `findings`. |
| `pod_assemble` | Merges artifacts into `draft` as a formatted code deliverable. Routes to `human_review`. |

### Pod loop

```
pod_entry → pod_backend → pod_frontend → pod_qa
                                            ↓
                             (revise + count < 2) → pod_backend
                                            ↓
                               (pass or max reached) → pod_assemble → human_review
```

### Routing change in `route_after_chief`

One new branch: if `dev_pod_requested` → `pod_entry` instead of `researcher` or `evidence_extract`.

## Workstreams

### 1. State

**Objective:** Add pod fields to `SharedState` and `ChiefWorkOrder`.

- [x] Add `dev_pod_requested: NotRequired[bool]` to `SharedState`
- [x] Add `pod_task_brief: NotRequired[str]` to `SharedState`
- [x] Add `pod_artifacts: NotRequired[dict[str, str]]` to `SharedState`
- [x] Add `pod_qa_findings: NotRequired[list[str]]` to `SharedState`
- [x] Add `pod_qa_verdict: NotRequired[Literal["pass", "revise"]]` to `SharedState`
- [x] Add `pod_revision_count: NotRequired[int]` to `SharedState`
- [x] Add `dev_pod_requested: bool` to `ChiefWorkOrder`
- [x] Confirm changes compile cleanly (no import errors, no type errors)

### 2. Agents

**Objective:** Write the three pod agents in `agent_team/agents/`.

- [x] Write `agent_team/agents/backend.py` — generates backend code artifacts from `pod_task_brief`
- [x] Write `agent_team/agents/frontend.py` — generates frontend code artifacts; receives backend artifacts in context
- [x] Write `agent_team/agents/qa.py` — reviews all artifacts, returns `verdict` + `findings` as structured JSON
- [x] Write `agent_team/prompts/backend.md`
- [x] Write `agent_team/prompts/frontend.md`
- [x] Write `agent_team/prompts/qa.md`

### 3. Graph nodes

**Objective:** Wire pod nodes into `graph.py` with the internal loop.

- [x] Add `pod_entry_node` — CoS writes `pod_task_brief`, routes to `pod_backend`
- [x] Add `pod_backend_node`
- [x] Add `pod_frontend_node`
- [x] Add `pod_qa_node`
- [x] Add `pod_assemble_node` — merges artifacts into `draft`, routes to `human_review`
- [x] Add `route_after_pod_qa` — returns `pod_backend` if revise + count < 2, else `pod_assemble`
- [x] Wrap all nodes with `timed_node` (matches existing pattern)

### 4. Routing and CLI

**Objective:** Connect the pod to the existing routing and invocation layer.

- [x] Extend `route_after_chief` to branch on `dev_pod_requested → pod_entry`
- [x] Add `--dev-pod` CLI flag to the entrypoint (confirm entrypoint path before editing)
- [x] Update CoS prompt (`prompts/chief_of_staff.md`) to detect code tasks and set `dev_pod_requested: true` in work order — triggers on `deliverable_type: "code"` / `"script"` / `"feature"` or task language ("build", "implement", "write a script")
- [x] Update CoS prompt to write a `pod_task_brief` when routing to the pod

### 5. Integration test

**Objective:** Validate the pod loop behaves correctly end-to-end.

- [x] Dry run: simple, well-defined code task (not AgriWebb — use a throwaway feature)
- [x] Confirm execution path includes all five pod nodes
- [x] Confirm QA revision loop fires at least once and terminates correctly
- [x] Confirm `draft` contains assembled code at `human_review`
- [ ] Confirm JT still works independently on non-pod tasks after routing changes

## First real project

**AgriWebb sales discovery tool** — web app, existing prototype, clear direction. This is the first real task to hand to the pod once the integration test passes. Do not use it as the integration test itself.

## Definition of success for this phase

The pod is working when it can:

1. Accept a concrete code task via `--dev-pod` or natural language
2. Route through Backend → Frontend → QA without errors
3. Complete at least one QA revision cycle and terminate within the cap
4. Hand a coherent, readable code draft to human review
5. Leave all non-pod task paths completely unchanged

## Risks to avoid

- Running unsandboxed code during QA (decided: review-only — do not revisit)
- Letting pod entry pull files directly (CoS handles context — do not add file-reading to pod agents)
- Breaking existing researcher→writer→reviewer routing for non-pod tasks
- Adding more than three pod agents in v1 (Frontend, Backend, QA — that's it)
- Confusing `pod_artifacts` (dict of filename → code) with `draft` (the final assembled string for human review)

## Change log

### 2026-04-23 — Integration test passed, display bug fixed
- Dry run confirmed execution path: CoS → pod_entry → pod_backend → pod_frontend → pod_qa → pod_revise_prep → pod_backend → pod_frontend → pod_qa → pod_assemble → human_review
- Live run produced working Flask API (Python) + React TypeScript frontend component for farm properties endpoint
- QA revision loop fired once and terminated correctly on second pass
- Fixed cosmetic display bug in `human_review_node`: pod paths now show `pod_qa_pass/revise` instead of misleading `needs_revision` from the unused reviewer node
- Workstreams 1–4 complete; integration test (workstream 5) passed except JT regression check (still pending)
- Branch `gallant-knuth-a59ace` ready to merge

### 2026-04-23 — Web console wired; pod output flows through browser approval gate
- FastAPI server (`app/server.py`) and SSE streaming added to the project
- Pod's human review gate now works in the browser: UI pauses on assembled code draft, user approves or sends back with notes via `/approve` endpoint
- Sequential branch execution added to UI: Brainstorm output can auto-feed Plan as task input
- No pod agent code changed — web layer is purely additive

### 2026-04-22 — Phase 3 plan created
- Design session complete; all three decisions locked (execution model, definition of done, invocation pattern)
- Architecture defined: 5 new nodes, 6 new state fields, 1 new ChiefWorkOrder field
- First real project identified: AgriWebb sales discovery tool (web app)
- Implementation order confirmed: state → agents → graph nodes → routing/CLI → integration test
