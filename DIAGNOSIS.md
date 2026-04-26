# Agent Team — Diagnosis & Fix Plan
_Originally written by Claude after a full codebase read. Updated 2026-04-26 to reflect current state._

---

## How to use this doc

Each issue has a **severity**, **current status**, and the relevant context. Issues that are resolved are marked ✅. Issues that have been superseded by a different implementation are marked 🔄. Open issues retain their original detail.

---

## Issue 1 — Agent knowledge layer never loads ✅ RESOLVED

**Root cause (original):** `AgentKnowledgeLoader` was initialized with `settings.obsidian_vault_path` instead of the project root, so it looked for `agent_docs` in the vault instead of the repo.

**Fix applied:** `server.py` now uses `_project_root = Path(__file__).resolve().parents[2]` to point the loader at the correct project root. The `agent_docs/` folder exists on disk with 15 agent CLAUDE.md descriptors covering all agents.

**Verification:** Server startup prints `[server] Agent knowledge layer loaded: .../AgentTeam/agent_team/agent_docs` when working correctly.

---

## Issue 2 — Send button silently does nothing after CoS says "Ready" ✅ RESOLVED

**Fix applied:** Removed `|| intakeReady` from the `sendBtn` click guard in `index.html`. Guard is now `if (!text || intakePending) return;`.

---

## Issue 3 — Typed text stays in input box while CoS is thinking ✅ RESOLVED

**Fix applied:** `runIntake()` now clears `taskInput.value` and resets height immediately after `appendChatMsg('user', userText)`.

---

## Issue 4 — CoS questions appear but can't be clicked ✅ RESOLVED

**Fix applied (2026-04-26):** Questions (`<li>` elements in `.cos-questions`) now have a click handler that fills `taskInput` with the question text and auto-sends. Hover styles added (`cursor: pointer`, background highlight). Options chips were already clickable; this brings questions to parity.

---

## Issue 5 — CoS can't read local files during intake 🔄 SUPERSEDED

**Original plan:** Add `files_path` field to `IntakeRequest` and wire it through the intake call.

**What actually happened:** This was superseded by `VaultSessionLoader` (commit `be55e77`), which auto-loads all CLAUDE.md files from the entire Obsidian vault on every intake and run call. CoS now receives full vault orientation automatically — no manual file field needed. The Local Files field was removed from the UI and replaced with Priority Folders (pin specific vault folders to the full-content tier).

**Current behavior:** Vault context is always-on. Priority Folders let Andrew elevate specific projects to full-content tier. No action needed.

---

## Issue 6 — CoS feels generic / doesn't know Andrew ✅ RESOLVED

**Fixes applied:**
1. Agent knowledge layer path fix (Issue 1) — CoS now loads all 15 agent descriptors.
2. `voice_loader` is passed to `ChiefOfStaffAgent.__init__()` in `server.py` and is included in intake user prompts as "Andrew's voice and style guide."
3. `VaultSessionLoader` (Issue 5 superseding fix) gives CoS full vault context on every call.

---

## Issue 7 — `chief_of_staff_final` node card never activates in UI ✅ RESOLVED

**Fix applied:** `NODE_TO_STEP` in `index.html` now uses `chief_of_staff_final: 'chief_final'` (was `chief_final: 'chief_final'`).

---

## Issue 8 — Empty Draft tab after a plan run ✅ RESOLVED (diagnostic)

**Fix applied:** The silent `catch {}` in the SSE listener is now `catch(err) { console.error('[SSE parse error]', err.message, e.data?.slice(0, 300)); }`. If the draft tab is blank, open DevTools console — the error and the raw event data will be printed.

**Note:** The draft tab issue has not recurred since the logging was added. If it does, check:
- `[human_review] draft length: N` — if 0, the writer produced empty output
- `[SSE parse error]` — if present, the event payload is malformed

---

## Issue 9 — Terminal logging confusion ✅ NOT A BUG

The correct server start command is always `make run` from `AgentTeam/` (or `cd agent_team && uvicorn app.server:app --reload`). Running `uvicorn` from the repo root causes a module import failure. No code change needed.

---

## Issue 10 — Orchestration view redesign ⏳ DEFERRED

**What you see:** The middle panel pre-renders all agent cards for the selected branch on page load, including agents that won't run. You want cards to appear dynamically as agents are invoked, each with a "why" line from the CoS work order.

**Proposed approach:**
1. On page load: show only "Waiting for run to start…"
2. On `node_start` event: dynamically append a card, marked active
3. On `node_complete` event: mark complete; add "why" line from `work_order.success_criteria`
4. Emit a `work_order` SSE event type from `on_node_exit("chief_of_staff", ...)` in `server.py`

**Status:** Saved for after chat flow and context bugs are resolved. This is the most significant UI change remaining.

---

## Uncommitted changes as of 2026-04-26

The following improvements were made in recent sessions and are staged but not yet committed:

| File | Change |
|------|--------|
| `agent_team/agents/chief_of_staff.py` | Vault context fallback: if `ObsidianContextTool` returns nothing, CoS falls back to the server-preloaded `vault_context` from `model_metadata`. Prevents silent context loss on slow/failed LLM calls. |
| `agent_team/app/graph.py` | Evidence extract safety net: if no research facts and no file evidence, injects `latest_approved_output` from project memory as fallback context for the Writer. |
| `agent_team/agents/base_sub_advisor.py` | Cluster signal mandate: all sub-advisors now required to close with a `[CLUSTER SIGNAL]` block (Stance, Top Priority, Disagrees With). |
| `agent_team/prompts/advisor.md` | Synthesis agent updated to read and act on `[CLUSTER SIGNAL]` blocks — surfaces genuine disagreements between clusters by name instead of vague "some advisors urge caution." |
| `agent_team/prompts/{4 advisor prompts}` | `[CLUSTER SIGNAL]` format block appended to each cluster advisor prompt. |

These should be committed together as a single "feat: cluster signals + context hardening" commit.

---

## Cleanup needed

**5 wrong-named advisor folders** were created in `agent_team/agent_docs/` and need to be manually deleted:
- `communication_influence_advisor/` → correct name is `advisor_communication_influence/`
- `entrepreneur_execution_advisor/` → correct name is `advisor_entrepreneur_execution/`
- `growth_mindset_advisor/` → correct name is `advisor_growth_mindset/`
- `leadership_culture_advisor/` → correct name is `advisor_leadership_culture/`
- `strategy_systems_advisor/` → correct name is `advisor_strategy_systems/`

These are untracked (won't affect git) but should be removed to avoid confusing the `AgentKnowledgeLoader`.

To delete:
```bash
cd agent_team/agent_docs
rm -rf communication_influence_advisor entrepreneur_execution_advisor growth_mindset_advisor leadership_culture_advisor strategy_systems_advisor
```

---

## Priority order for remaining work

| # | Item | Effort | Status |
|---|------|--------|--------|
| — | Commit uncommitted changes | 5 min | Ready to commit |
| — | Delete 5 wrong-named agent_doc folders | 1 min | Manual bash needed |
| 10 | Orchestration view redesign | Significant | Deferred |
