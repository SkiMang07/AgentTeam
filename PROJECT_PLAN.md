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

**Phase:** Phase 2 beginning  
**State:** Local scaffold is running in Terminal  
**Focus:** Turn the scaffold into one genuinely useful workflow

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

- [ ] Define the first allowed local file workflow
- [ ] Decide where user provided files will come from
- [ ] Add a simple local file reader
- [ ] Add bounded file selection rules
- [ ] Add evidence extraction step
- [ ] Pass evidence into Writer
- [ ] Make Reviewer check whether draft reflects evidence
- [ ] Avoid claiming the system read files it did not actually read

### 5. Project memory

**Objective:** Add simple project level memory so the system can hold onto current work across a session.

- [ ] Define a minimal project memory schema
- [ ] Save current objective
- [ ] Save active deliverable type
- [ ] Save open questions
- [ ] Save latest draft
- [ ] Save latest approved output
- [ ] Keep memory narrow and inspectable

### 6. Artifact quality

**Objective:** Move from generic text output to useful project artifacts.

- [ ] Define the first artifact types to support
- [ ] Start with executive brief
- [ ] Add project plan output
- [ ] Add decision memo output
- [ ] Add risk and gaps output
- [ ] Make outputs consistent and reusable

## Suggested issue order

### Immediate next issues

1. Define Chief of Staff work order format
2. Add first local file context workflow
3. Add evidence extraction from local files

### After those

6. Add evidence extraction from local files
7. Add project memory fields
8. Add first artifact templates
9. Tighten README and docs to match implementation

## Current next task

**Issue 5:** Make human review behavior explicit and easy to follow

### Done when

- Chief of Staff work order includes objective, deliverable type, and success criteria
- Work order includes open questions and routing context for downstream agents
- README and PROJECT_PLAN remain aligned with actual behavior

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

### 2026-04-22
- Fixed a non-JT closed-facts regression where reviewer raw-task blocked-claim parsing could conflict with structured work-order requirements and create unsatisfiable redraft loops
- Reviewer closed-facts enforcement now prefers canonical work-order + approved-facts contracts and only treats explicit prohibition clauses as blocked claims
- Kept `approved_facts` evidence-only; reviewer/chief/human revision instructions now flow through explicit writer guidance note fields
- Reduced `jt_requested` drift risk by preferring `work_order.jt_requested` when selecting reviewer artifact and formatting Chief-final JT context
