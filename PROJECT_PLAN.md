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
4. Optionally run JT only when explicitly requested
5. Return a final output that is reviewable and grounded
6. Move toward local file context so outputs are more useful than a normal chat window

## Current workflow

1. Chief of Staff interprets the request
2. Researcher gathers facts and gaps when needed
3. Writer produces a draft
4. Reviewer checks the draft
5. JT runs only if explicitly requested
6. Chief of Staff does a final structure and completeness pass
7. Human review approves or sends back for revision

## Workstreams

### 1. Core workflow hardening

**Objective:** Make the existing loop cleaner, more explicit, and more reliable.

- [x] Get the local scaffold running from Terminal
- [x] Confirm GitHub repo and local clone are working
- [ ] Review and tighten shared state fields
- [ ] Improve Chief of Staff routing logic
- [ ] Add clearer reviewer output structure
- [ ] Add Chief of Staff final validation pass
- [ ] Make human review behavior explicit and easy to follow
- [ ] Ensure README matches the actual implementation

### 2. JT optional challenge stage

**Objective:** Add JT as a selective challenge stage without changing the repo into a bigger platform project.

**Rules:**
- JT runs only when explicitly requested
- JT comments only
- JT does not rewrite
- JT sees only the writer draft and reviewer findings
- Chief of Staff decides what to do with JT feedback

- [ ] Add `jt_requested` field to shared state
- [ ] Add `jt_mode` field to shared state
- [ ] Add `jt_findings` field to shared state
- [ ] Create `prompts/jt.md`
- [ ] Add JT node or JT review path
- [ ] Route JT only when `jt_requested = true`
- [ ] Return JT findings to Chief of Staff for final pass
- [ ] Document JT behavior in README if implemented

### 3. Structured handoffs

**Objective:** Make each stage work from a clearer contract instead of loose narrative handoffs.

- [ ] Define Chief of Staff work order structure
- [ ] Include objective in the work order
- [ ] Include deliverable type in the work order
- [ ] Include success criteria in the work order
- [ ] Include open questions in the work order
- [ ] Include whether JT is requested
- [ ] Make Researcher return structured findings
- [ ] Make Reviewer return structured findings

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

1. Add JT state fields and routing
2. Add Chief of Staff final validation pass
3. Structure reviewer findings
4. Define Chief of Staff work order format
5. Add first local file context workflow

### After those

6. Add evidence extraction from local files
7. Add project memory fields
8. Add first artifact templates
9. Tighten README and docs to match implementation

## Current next task

**Issue 1:** Add JT as an optional challenge stage without expanding the core architecture

### Done when

- `jt_requested` exists in state
- JT only runs when explicitly requested
- JT sees writer draft and reviewer findings only
- JT returns comments only
- Chief of Staff receives JT findings and does final pass
- Human review still remains the final approval step

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
