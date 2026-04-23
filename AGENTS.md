# AGENTS.md

## Project goal

Build a local multi-agent system using OpenAI Responses API for model calls and LangGraph for orchestration.

The system routes tasks through one of three branches:

**Plan** — Chief of Staff → Researcher → Writer → (JT) → Reviewer → CoS Final → Human Review
**Build** — Chief of Staff → Backend → Frontend → QA → Assemble → Human Review
**Brainstorm** — Chief of Staff → 5 Advisor Clusters → Advisor Synthesis → Human Review

Current agents:
1. Chief of Staff — classifies, routes, and runs final validation pass
2. Researcher — extracts facts and gaps from vault, local files, or web
3. Writer — drafts output from approved facts
4. Reviewer — structured QC pass (Plan branch only)
5. JT — optional challenge/pressure-test modifier (Plan branch only)
6. Backend, Frontend, QA — developer pod (Build branch)
7. Advisor (synthesis) + 5 cluster sub-advisors — advisor pod (Brainstorm branch)
8. Human review step on all branches

## Build priorities

1. Keep version one simple and runnable locally
2. Prefer clear structure over cleverness
3. Use Python
4. Use LangGraph for orchestration and explicit shared state
5. Use OpenAI Responses API for model calls
6. Start with no external business integrations
7. Make the first version CLI based
8. Keep code easy to extend later

## Constraints

1. Do not overengineer — keep it runnable and understandable locally
2. Do not add Slack, HubSpot, email, calendar, or database integrations yet
3. Do not add new agents or pods without explicit approval
4. Do not add a web UI yet
5. Do not use broad autonomous behavior
6. Keep all prompts in separate files
7. Keep state explicit and typed
8. Add comments only where they help readability

## Repo expectations

1. Create a working scaffold with a clear folder structure
2. Add a README with setup and run instructions
3. Add requirements.txt
4. Add a .env.example file
5. Make the app runnable with `python -m app.main`
6. Explain what was created and any assumptions made

## Quality bar

1. The code should run
2. The graph should be understandable
3. The human  step should be real, not hand waved
4. Keep the first pass boring and solid

## Planning and task tracking

The canonical project plan lives in `PROJECT_PLAN.md` at the repo root.

When making changes:
- update `PROJECT_PLAN.md` in the same PR when project status changes
- keep checkboxes honest and current
- keep the `Current next task` section accurate
- reference the related GitHub issue in the PR when one exists
- do not mark work complete unless code, docs, and behavior are actually done

Scope discipline:
- do not add new business integrations unless explicitly requested
- do not add a UI unless explicitly requested
- do not add more core agents beyond the current architecture without explicit approval
- JT is an optional challenge stage, not a default always on core agent

Documentation discipline:
- if implementation changes behavior, update `README.md`
- if implementation changes project status or priorities, update `PROJECT_PLAN.md`
- prefer small, able PRs over large bundled changes


Branch and PR rules for this repo
- Before making changes, sync your work to the latest state of the target branch and inspect for drift.
- If there is already an open PR branch for this issue, continue updating that branch instead of creating a new overlapping branch.
- Keep changes tightly scoped to the issue. Do not modify unrelated files.
- Avoid opportunistic refactors, renames, or formatting-only edits outside the files required for the issue.
- If the target files have changed materially since the task started, stop and summarize likely conflict risk before making broad edits.
- Prefer one issue per branch or worktree. Do not mix multiple issue implementations in one branch.

## Review guidelines

When reviewing pull requests in this repo, focus on correctness, scope control, and behavior drift.

Priorities, in order:

1. Check whether the change actually solves the issue it claims to solve.
2. Check whether graph behavior is still explicit and understandable.
3. Check whether shared state remains typed, canonical, and internally consistent.
4. Check whether routing logic is deterministic where it should be deterministic.
5. Check whether human review remains a real approval step and was not weakened or bypassed.
6. Check whether JT behavior remains optional and only runs when explicitly requested.
7. Check whether the change introduced unsupported assumptions, hidden side effects, or silent behavior changes.
8. Check whether README.md and PROJECT_PLAN.md were updated when behavior or project status changed.
9. Check whether the PR stayed tightly scoped to the issue and avoided unrelated refactors.
10. Check whether tests, smoke checks, or manual validation are adequate for the risk level of the change.

Flag issues aggressively when you see any of the following:

1. State fields duplicated without a clear canonical source
2. Routing decisions based on loose prose parsing when structured state should drive them
3. Reviewer or Chief of Staff outputs being treated as authoritative without structured validation
4. Silent downgrade of explicit JT requests
5. Unsupported claims, contradictory facts, or fake grounding
6. Human review being reduced to a cosmetic step
7. Docs drifting away from real implementation
8. Broad abstractions that add complexity without clear value
9. Unrelated file churn that increases merge conflict risk
10. New integrations, UI work, or new core agents added without explicit approval

Do not spend review energy on minor style preferences unless they affect readability, maintainability, or correctness.

Prefer comments that are concrete and actionable. Call out the exact risk, why it matters, and what should change.
- When possible, minimize edits to files that are already being changed in another open PR.
- In your final response, list exactly which files changed and call out any files likely to conflict with open PRs.
