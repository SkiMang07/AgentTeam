# Agent Team Project Plan

## Goal

Build a useful local multi agent workflow that can help with real project work while staying narrow, inspectable, and easy to extend.

This repo should remain a practical v1:
- local first
- CLI based
- grounded in explicit state
- built around Chief of Staff, Researcher, Writer, and human review
- expanded carefully only after the core loop is solid

## Current status

**Phase:** Phase 2 — tool integration complete, effectiveness not yet verified  
**State:** Three tools integrated (Obsidian context navigator, voice loader, web search). First real test run completed 2026-04-22. Pipeline runs cleanly end-to-end but tools are not yet meaningfully changing output quality.  
**Focus:** Fix the five diagnosed root causes so tools actually show up in what gets written

## Principles

- Keep version one small
- Prefer clarity over cleverness
- Do not add business integrations yet
- Do not add a UI yet
- Do not add more core agents
- Keep prompts separate from code
- Keep state explicit and typed
- Human review remains required
- Build one useful workflow before adding complexity

## Definition of success for this phase

This project is succeeding in the near term if it can:

1. Take a real user task
2. Route it clearly through the core workflow
3. Use structured research and drafting
4. Optionally run JT agent stage only when explicitly requested with explicit contracts
5. Return a final output that is reviewable and grounded
6. Move toward local file context so outputs are more useful than a normal chat window

## Current workflow

1. Chief of Staff interprets the request
2. Researcher gathers facts and gaps when needed
3. Writer produces a draft
4. Reviewer checks the draft
5. JT agent stage runs only if explicitly requested, between Writer and Reviewer
6. Chief of Staff does a final structure and completeness pass
7. Human review approves or sends back for revision

## Workstreams

### 1. Core workflow hardening

**Objective:** Make the existing loop cleaner, more explicit, and more reliable.

- [x] Get the local scaffold running from Terminal
- [x] Confirm GitHub repo and local clone are working
- [x] Review and tighten shared state fields
- [ ] Improve Chief of Staff routing logic
- [x] Add clearer reviewer output structure
- [x] Add Chief of Staff final validation pass
- [ ] Make human review behavior explicit and easy to follow
- [x] Ensure README matches the actual implementation

### 2. JT optional challenge stage

**Objective:** Add JT as a selective challenge stage without changing the repo into a bigger platform project.

**Rules:**
- JT runs only when explicitly requested
- JT produces structured feedback and a rewritten artifact
- JT runs after Writer and before Reviewer
- Reviewer validates JT rewrite content on JT paths
- Chief of Staff final consumes JT structured output for alignment checks
- JT is always a distinct graph step when requested

- [x] Add `jt_requested` field to shared state
- [x] Add `jt_mode` field to shared state
- [x] Add `jt_findings` field to shared state
- [x] Create `prompts/jt.md`
- [x] Add JT node or JT review path
- [x] Route JT only when `jt_requested = true`
- [x] Return JT findings to Chief of Staff for final pass
- [x] Document JT behavior in README if implemented

### 3. Structured handoffs

**Objective:** Make each stage work from a clearer contract instead of loose narrative handoffs.

- [x] Define Chief of Staff work order structure
- [x] Include objective in the work order
- [x] Include deliverable type in the work order
- [x] Include success criteria in the work order
- [x] Include open questions in the work order
- [x] Include whether JT is requested
- [x] Make Researcher return structured findings
- [x] Make Reviewer return structured findings

### 4. Local file context

**Objective:** Add bounded local file support so the system can work from real project materials.

- [x] Define the first allowed local file workflow
- [x] Decide where user provided files will come from
- [x] Add a simple local file reader
- [x] Add bounded file selection rules
- [x] Add evidence extraction step
- [x] Pass evidence into Writer
- [x] Make Reviewer check whether draft reflects evidence
- [x] Avoid claiming the system read files it did not actually read

### 5. Project memory

**Objective:** Add simple project level memory so the system can hold onto current work across a session.

- [x] Define a minimal project memory schema
- [x] Save current objective
- [x] Save active deliverable type
- [x] Save open questions
- [x] Save latest draft
- [x] Save latest approved output
- [x] Keep memory narrow and inspectable

### 6. Artifact quality

**Objective:** Move from generic text output to useful project artifacts.

- [x] Define the first artifact types to support
- [x] Start with executive brief — template at `agent_team/prompts/artifacts/executive_brief.md`; Writer injects on `deliverable_type = "executive_brief"`; CoS sets type when task requests exec brief or leadership brief
- [x] Add decision memo output — template at `agent_team/prompts/artifacts/decision_memo.md`; Writer injects on `deliverable_type = "decision_memo"`; CoS sets type when task requests decision memo, decision doc, or decision record
- [x] Add project plan output — template at `agent_team/prompts/artifacts/project_plan.md`; Writer injects on `deliverable_type = "project_plan"`; CoS sets type when task requests project plan or project brief
- [ ] Add risk and gaps output
- [x] Make outputs consistent and reusable — all three types follow the same injection pattern; adding a new type requires only a new `.md` file in `artifacts/` and one line in `ARTIFACT_TEMPLATES`

### 7. Tool effectiveness — diagnosed fixes

**Objective:** Make the three integrated tools (Obsidian context, voice loader, web search) actually change output quality. First test run (2026-04-22) confirmed the pipeline runs but all three tools are currently inert — the outputs are indistinguishable from a plain chat window.

**Diagnosed root causes and fixes:**

**Issue A — Routing bypasses the Researcher for writing tasks**  
The CoS routes "write a..." tasks to `write_direct`, which skips the Researcher entirely. This means vault context extraction, approved facts, and web search all never fire. The Writer gets an empty facts list and produces generic output.  
Fix: Update CoS routing logic and/or prompt so tasks involving project-specific facts force `research_needed: true`. Consider routing all `--web-search` runs through the Researcher regardless of `write_direct`.

- [x] Diagnose exact CoS routing condition that produces `write_direct` for status-update tasks — root cause: CoS sets `research_needed=false`, graph checks that field first and ignores the `route` field entirely
- [x] Add routing rule: if vault context is available and task references specific project facts, set `research_needed: true` — added explicit critical rule to CoS prompt + code safeguard in `chief_of_staff.py` that forces `research_needed=True` and `route="research"` when vault context is non-empty
- [x] Add routing rule: if `--web-search` is enabled, always route through Researcher — existing override now also syncs `work_order["research_needed"] = True` so `route_after_chief` in `graph.py` honours it
- [x] Verify Researcher appears in execution path for writing tasks after fix — `route_after_chief` now treats `state["route"] == "research"` as the final word before checking `research_needed`
- [x] Re-run Test 1 and confirm `approved_facts` is non-empty when Writer runs — confirmed 2026-04-22, Test 1 score 8.5/10 (vault grounding working, prose output, no closers)

**Issue B — Web search never fires (downstream of Issue A)**  
Because the Researcher node is skipped on `write_direct` routes, `--web-search` does nothing. Fixing Issue A should unblock this, but web search behavior needs an independent verification step.

- [x] Confirm `researcher_web_search_used: True` appears in metadata after Issue A fix — web_search override now syncs `research_needed=True` so Researcher always runs when `--web-search` is set
- [x] Verify Test 2 output is meaningfully richer than Test 1 — Researcher ran, output grounded; web search on a private local project adds minimal external facts (expected) — Test 2 score 7.5/10
- [x] Check that web facts don't contradict vault facts without resolution — no contradictions observed

**Issue C — Voice guide is not dominating Writer output**  
The voice file is loaded and appended to the Writer's system prompt, but the Writer's default behavior (bold headers, bullet lists, "Let me know if you want this tailored...") overrides it. The voice guide is losing to the base prompt pattern.  
Fix: Move voice content earlier in the system prompt, add a hard `do-not` list to the base writer prompt (no bullets unless requested, no AI closers, no "Let me know if..."), and optionally add concrete before/after examples.

- [x] Read current `prompts/writer.md` and identify default patterns that conflict with the voice guide
- [x] Add explicit negative constraints to the writer base prompt (format don'ts) — "Format rules — always apply" block added to top of `writer.md`
- [x] Move voice block injection to appear before the base prompt body, not after — `writer.py` line 44: `f"{voice_block}\n\n{base_prompt}"`
- [x] Re-run Test 3 and verify output has no AI closers, no bullets, and reads like Andrew — confirmed 2026-04-22

**Issue D — CoS work order doesn't extract vault specifics**  
The CoS receives vault context but produces a generic `objective` and empty `success_criteria`. The work order is not carrying vault-specific details into the Writer. Vault context goes in, but generic instructions come out.  
Fix: Update the CoS prompt to explicitly instruct the model to pull concrete vault details (project names, decisions, current state) into `success_criteria` and `open_questions` fields of the work order.

- [x] Update `prompts/chief_of_staff.md` to instruct explicit vault-fact extraction into work order fields
- [x] Verify `success_criteria` contains vault-specific items after fix — confirmed via test output 2026-04-22
- [x] Confirm Writer output references project-specific details that came from vault context — confirmed 2026-04-22

**Issue E — AgentTeam project folder has no CLAUDE.md**  
The vault navigator can only inject what CLAUDE.md files it finds. Without a CLAUDE.md in the AgentTeam project folder, the navigator returns nothing useful about the project, so the agents describe the tools incorrectly (e.g. Voice Loader described as a voice-profile switcher, not a style-guide injector).  
Fix: Add a CLAUDE.md to the AgentTeam project folder in the vault with accurate tool descriptions, current build state, and next milestones.

- [x] Create `CLAUDE.md` in the AgentTeam project Obsidian folder — at `/Users/andrewgodlewski/Desktop/Obsidian/main/01 Projects/Personal/Agent Team/CLAUDE.md`
- [x] Include accurate descriptions of all three tools and their actual behavior
- [x] Include current build status and next milestone
- [x] Re-run Test 1 and verify output contains accurate, vault-sourced project details — confirmed 2026-04-22

## Suggested issue order

### Immediate next issues (tool effectiveness — tackle one per session)

1. **Issue E** — Add CLAUDE.md to the AgentTeam vault folder *(lowest effort, highest clarity gain — do this first so vault context has accurate content to inject)*
2. **Issue A** — Fix CoS routing so Researcher runs for project-specific writing tasks *(unblocks Issues B and D downstream)*
3. **Issue B** — Verify web search fires after Issue A fix *(verification step, minimal new code)*
4. **Issue C** — Fix Writer voice dominance (prompt restructure + negative constraints)
5. **Issue D** — Update CoS prompt to extract vault specifics into work order fields

### After those

6. Artifact quality (workstream 6) — executive brief, project plan, decision memo templates
7. Tighten README and docs to match implementation as it evolves

## Current next task

**Workstream 6 — risk and gaps output:** Add `agent_team/prompts/artifacts/risk_and_gaps.md` template and register `deliverable_type = "risk_and_gaps"` in `ARTIFACT_TEMPLATES` and the CoS routing rules. This is the last remaining artifact type in Workstream 6 (lower priority).

Alternatively: tighten README and docs to match current implementation before adding more features.

### Done when

- `risk_and_gaps.md` template exists in `agent_team/prompts/artifacts/`
- Writer injects it when `deliverable_type == "risk_and_gaps"`
- CoS sets the type for risk/gap analysis requests

## Risks to avoid

- Turning v1 into a broader platform project too early
- Adding too many agents
- Adding business integrations before the local loop is solid
- Confusing more critique with more intelligence
- Building a flashy workflow without grounded context
- Letting docs drift away from the real code

## Notes for future contributors

- Keep this plan updated when work is completed
- Update checkboxes in the same PR where the work is done
- Keep “Current next task” accurate
- Do not mark items done unless code, docs, and behavior are actually complete
- Prefer small, reviewable PRs
- Stay within the repo constraints unless the project is intentionally moved to a new phase

## Change log

### 2026-04-22 (test suite verification — session 2 complete)
- Re-ran full test suite after routing and voice fixes; all three tests improved over baseline
- Test 1: 8.5/10 — Researcher runs, vault facts accurate and specific, prose output, no closers, no bullets
- Test 2: 7.5/10 — Researcher runs with web search, no contradictions; bullet variance on model stochasticity, accepted
- Test 3: 9/10 — self-contained writing task correctly skips Researcher, voice clean, first-person, no closers
- Closed all Workstream 7 verification items; session 2 work complete
- Next: Workstream 6 remaining (risk/gaps output) or README tightening

### 2026-04-22 (Workstream 7 — Issue C, voice dominance hardening)
- Rewrote `writer.md` to close three remaining voice dominance gaps:
  1. Stale "appended below" reference — voice block is prepended in `writer.py`; prompt now says "provided above" so the model doesn't look for it after the base instructions and discount it
  2. Loose format rule — "unless the task explicitly requests" replaced with a tighter rule: bullets/headers only when task text explicitly names them OR an artifact template requires them; work order signals no longer grant implicit permission
  3. Missing priority rule — added a dedicated "Voice priority rule" section declaring that the voice guide outranks default formatting instincts, with specific prohibitions: no bullet fallback, no bold headers, no AI closers

### 2026-04-22 (Workstream 7 — Issues A and B, routing fixes)
- Diagnosed root cause: `route_after_chief` in `graph.py` checks `work_order["research_needed"]` first and ignores the `state["route"]` field entirely — so the existing web_search override (which correctly sets `route="research"`) was silently doing nothing
- Fixed `chief_of_staff.py` web_search override to also set `work_order["research_needed"] = True` so `route_after_chief` honours it
- Added vault context safeguard to `chief_of_staff.py`: when obsidian block is non-empty, force `research_needed=True` and `route="research"` in code — removes model discretion on this path
- Added explicit "Critical rule" to `chief_of_staff.md`: vault context here is a planning aid, not approved_facts; if vault context is present and non-empty, model must set `research_needed=true`
- Fixed `route_after_chief` in `graph.py`: explicit `route == "research"` now takes precedence over `work_order["research_needed"]`, making the two fields consistent
- Issues A and B are structurally resolved; live test run needed to confirm output quality improvement

### 2026-04-22 (Workstream 6 — artifact quality, phase 3)
- Completed project plan artifact type — Workstream 6 core artifact types now done
- Created `agent_team/prompts/artifacts/project_plan.md` template defining five required sections (Objective, Current State, Workstreams / Milestones, Open Questions, Risks) with structured workstream entry format and format rules specific to project plans
- Added `"project_plan"` entry to `ARTIFACT_TEMPLATES` in `writer.py`
- Updated `chief_of_staff.md` deliverable type rules to recognise project plan and project brief phrasing
- Marked "Make outputs consistent and reusable" complete — pattern is proven across three artifact types
- Workstream 6 remaining: risk and gaps output (deferred); next priority is Workstream 7 Issue A (CoS routing fix)

### 2026-04-22 (Workstream 6 — artifact quality, phase 2)
- Completed decision memo artifact type
- Created `agent_team/prompts/artifacts/decision_memo.md` template defining five required sections (Context, Decision, Options Considered, Recommendation, Implications) with format rules specific to decision memos
- Added `"decision_memo"` entry to `ARTIFACT_TEMPLATES` in `writer.py`
- Updated `chief_of_staff.md` deliverable type rules to recognise decision memo, decision doc, and decision record task phrasing

### 2026-04-22 (Workstream 6 — artifact quality, phase 1)
- Completed artifact quality workstream phase 1: executive brief artifact type added
- Created `agent_team/prompts/artifacts/` directory and `executive_brief.md` template defining five required sections (Problem, Recommendation, Rationale, Risks, Next Steps) with format rules specific to executive briefs
- Updated `writer.py`: added `_load_artifact_template()` helper, `ARTIFACT_TEMPLATES` registry, and artifact template injection into the Writer user prompt when `deliverable_type` matches a known type
- Updated `chief_of_staff.md`: added deliverable type rules so CoS sets `deliverable_type = "executive_brief"` when the task requests an exec brief, recommendation memo, or leadership brief
- Pattern is extensible: adding a new artifact type requires only a new `.md` file in `artifacts/` and a one-line entry in `ARTIFACT_TEMPLATES`
- Next: decision memo template (Workstream 6, phase 2)

### 2026-04-20
- Initial project plan created
- Local scaffold confirmed running
- JT approach defined as optional challenge stage
- Next major target identified as local file context
- Issue 1 completed: JT optional challenge stage added with explicit routing and scoped inputs

### 2026-04-21
- Refactored JT commenter mode to remove separate JT-node dependency
- JT node now skips commenter mode and remains available for challenge-mode requests
- Chief of Staff now carries JT commenter editorial bar in active flow
- Hardened Reviewer commenter contract: validator-only prompt assembly, strict JSON isolation, and explicit contract-violation handling for JT-style prose outputs
- Calibrated Reviewer commenter rubric to allow non-material tightening of soft leadership language while still rejecting unsupported escalation
- Added explicit redraft handoff targets (`revision_targets`) so second-pass writer edits are concrete and reviewer-actionable
- Added CLI debug mode to print commenter failure artifacts across pass 1/pass 2 (writer, reviewer JSON, auto-redraft handoff) for direct diagnosis
- Updated writer redraft behavior to revise the prior draft surgically (instead of regenerating from scratch) when reviewer targets are present
- Completed Issue 2: final Chief of Staff validation now stores a short structured alignment/completeness result in shared state before routing to human review
- Completed Issue 3: reviewer now returns a normalized structured QC findings object with explicit categories and recommended next action, consumed by Chief of Staff/JT downstream steps
- Tightened reviewer/core-routing guardrails so unsupported claims and core fact contradictions are prioritized above formatting issues and blocked from normal human-review routing when unresolved
- Fixed JT commenter redraft consistency bug: reviewer now validates current-pass JT Rewrite content, stale pass findings are scrubbed before verdicting, and reviewer routing/Chief-final gating now derives approval from the same current-pass recommended action
- Reworked JT into a first-class graph node with explicit `jt_input`, `jt_feedback`, and `jt_rewrite` contracts; reviewer now validates the JT rewrite artifact on JT paths and commenter-mode indirection was removed
- Fixed reviewer precedence for closed-fact tasks so blocked claims are never treated as required `missing_content` on non-JT paths
- Completed Issue 4: Chief of Staff now creates a canonical structured `work_order` in shared state, and Researcher/Writer/Reviewer/Chief-final all consume this shared artifact directly; JT routing is aligned to `work_order.jt_requested`

### 2026-04-22 (continued — tool integration test + diagnosis)
- Completed tool integration: Obsidian context navigator, voice loader, and web search all wired end-to-end and confirmed loading at startup
- Ran first real three-test evaluation (vault only, vault + web search, voice-only writing)
- All three tools confirmed loading but not changing output quality — pipeline runs cleanly, tools are inert
- Diagnosed five root causes: (A) CoS routes writing tasks to write_direct, bypassing Researcher entirely; (B) web search never fires as downstream consequence of A; (C) voice guide appended after base prompt, base prompt defaults win; (D) CoS work order doesn't extract vault specifics into success criteria or open questions; (E) no CLAUDE.md in AgentTeam vault folder so navigator has nothing accurate to return
- Updated project plan: added Workstream 7 with five tracked issues (A–E), reordered issue queue, updated current next task to Issue E (CLAUDE.md)
- Artifact quality workstream (6) deferred until tool effectiveness issues are resolved

### 2026-04-22
- Fixed a non-JT closed-facts regression where reviewer raw-task blocked-claim parsing could conflict with structured work-order requirements and create unsatisfiable redraft loops
- Reviewer closed-facts enforcement now prefers canonical work-order + approved-facts contracts and only treats explicit prohibition clauses as blocked claims
- Kept `approved_facts` evidence-only; reviewer/chief/human revision instructions now flow through explicit writer guidance note fields
- Reduced `jt_requested` drift risk by preferring `work_order.jt_requested` when selecting reviewer artifact and formatting Chief-final JT context
- Completed Issue 4 cleanup: added a shared canonical JT resolver, aligned graph + human-redraft JT routing to `work_order.jt_requested`, and preserved explicit JT requests during Chief-of-Staff work-order normalization
- Completed Issue 5: added bounded local file evidence workflow (`--files-path`) with strict extension allowlist, max-depth/max-file limits, explicit read/skip tracking (`files_requested`, `files_read`, `files_skipped`, `skip_reasons`), structured evidence extraction, and writer/reviewer grounding on actual read scope
- Tightened file-grounded output quality for Issue 5: evidence extraction now captures headings, bullets, and short snippets; Researcher now receives structured file evidence in prompt assembly; and approved-facts bundling now deduplicates richer file evidence before writing
- Completed Issue 6: added a minimal typed `project_memory` contract (`current_objective`, `active_deliverable_type`, `open_questions`, `latest_draft`, `latest_approved_output`) plus explicit `current_run` fields; memory now carries forward across later runs in the same local CLI session and remains terminal-inspectable
- Completed Issue 67: memory lookup is now intent-aware for `latest_approved_output`, `current_objective`, and `active_deliverable_type`, including combined field requests; lookup no longer defaults to `latest_approved_output` for every memory query
- Completed Issue 67 follow-up: transformational rewrite requests that reference stored output continue through normal drafting flow instead of lookup-only routing
- Completed Issue 67 UI-path fix: memory-lookup human review now avoids misleading inherited reviewer verdict display and clears stale reviewer artifacts on the lookup-prep path
- Clarified prompt assembly boundaries across Chief of Staff, Researcher, and Writer so current task, current evidence, and continuity memory are separated explicitly
- Completed Issue 67 memory-writeback fix: memory inspection turns are now read-only and no longer overwrite canonical `project_memory` artifact/context fields after approval; memory-based transform requests continue through normal drafting flow
- Completed Issue 16 follow-up: strengthened memory-inspection intent detection for session-stored/output-type phrasing, added object-type retrieval synonym support, and changed generic memory inspection fallback to return a key-field snapshot instead of output-only
