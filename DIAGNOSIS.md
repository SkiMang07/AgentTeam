# Agent Team — Diagnosis & Fix Plan
_Written by Claude after a full codebase read. No files were changed._

---

## How to use this doc

Each issue below has a **severity**, a **root cause** traced to the exact file and line, the **exact fix** (what to change and where), and whether it **blocks other things**. Work through them in priority order and this covers everything you reported plus a few things you hadn't caught yet.

---

## Issue 1 — Agent knowledge layer never loads (CRITICAL, blocks Issues 5 & 6)

**What you see:** CoS feels generic. Doesn't know your agents, doesn't sound like it knows your world.  
**Terminal evidence:** Every single server startup prints:
```
[server] Warning: Agent knowledge layer not found (agent_team/agent_docs missing)
```

**Root cause — path mismatch in `server.py` line 98:**

```python
agent_knowledge_loader = AgentKnowledgeLoader(settings.obsidian_vault_path)
```

`AgentKnowledgeLoader` is initialized with your **Obsidian vault path** (`/Users/.../Obsidian/main`). Internally it appends `"agent_team/agent_docs"` to that path, so it looks for:

```
/Users/andrewgodlewski/Desktop/Obsidian/main/agent_team/agent_docs/
```

But your agent_docs files live inside the **project repo**, not the vault root:

```
/Users/.../AgentTeam/agent_team/agent_docs/
```

Also confirmed by the glob: `agent_team/agent_docs/**/*.md` returned **no files on disk** from the project root — meaning the files either don't exist locally yet (they were committed to git but may not have been created on disk in this working tree), or the previous session's agent wrote them to the wrong location.

**Fix — 2-line change in `agent_team/app/server.py`:**

Around line 98, replace:
```python
agent_knowledge_loader = AgentKnowledgeLoader(settings.obsidian_vault_path)
```
with:
```python
_project_root = Path(__file__).resolve().parents[2]  # AgentTeam/
agent_knowledge_loader = AgentKnowledgeLoader(str(_project_root))
```

`AGENT_DOCS_RELATIVE = "agent_team/agent_docs"` in the loader already appends the right suffix, so pointing it at the project root (`AgentTeam/`) makes the full resolved path correct.

**Also do:** After making that change, verify the files actually exist on disk:
```bash
ls /Users/andrewgodlewski/Desktop/Obsidian/main/01\ Projects/Personal/Agent\ Team/AgentTeam/agent_team/agent_docs/
```
If the folder is empty or missing, you'll need to pull from remote or recreate it — the git commit shows 15 CLAUDE.md files that should be there.

---

## Issue 2 — Send button silently does nothing after CoS says "Ready" (HIGH)

**What you see:** After CoS responds and shows the ready green dot, you can still type in the box but hitting Enter / Send does nothing. The placeholder even says "Add context or adjustments" but the button is dead.

**Root cause — `index.html` line ~1076–1087, two places:**

```javascript
// sendBtn click handler:
if (!text || intakePending || intakeReady) return;   // ← intakeReady blocks it

// keydown handler:
sendBtn.click();   // triggers the same broken handler
```

When `intakeReady = true` the click guard returns early. But `runIntake()` itself (lines ~1004–1068) was written to handle `intakeReady = true` — it resets the ready state and re-runs intake. The click guard is just blocking the call before it gets there.

**Fix — remove `|| intakeReady` from the click guard:**

```javascript
// Before:
if (!text || intakePending || intakeReady) return;

// After:
if (!text || intakePending) return;
```

One-word change. `runIntake()` already has the reset logic, so no other changes needed.

---

## Issue 3 — Typed text stays in the input box while CoS is "thinking" (HIGH)

**What you see:** You hit Send, your message appears in the chat, but the text also stays in the textarea until CoS replies. Feels broken.

**Root cause — `runIntake()` in `index.html` (line ~1015):**

The function appends the user bubble and then immediately calls the `/intake` fetch. It never clears `taskInput` before awaiting the response.

**Fix — add two lines immediately after `appendChatMsg('user', userText)` inside `runIntake()`:**

```javascript
appendChatMsg('user', userText);
// ADD THESE:
taskInput.value = '';
taskInput.style.height = '';   // resets the auto-resize height
intakeConversation.push(...)
```

---

## Issue 4 — CoS questions appear but can't be clicked/selected (HIGH)

**What you see:** When CoS asks clarifying questions they render as arrow-prefixed list items. The issue says "options are shown but are not selectable — actual selecting would be ideal — this would enable a series of questions like Claude does."

**Root cause — `appendChatMsg()` in `index.html` (lines ~950–963):**

Questions are rendered as plain `<li>` elements with no event handler:
```javascript
const li = document.createElement('li');
li.textContent = q;
ul.appendChild(li);
```

**Fix — add a click handler that populates the input and triggers send:**

```javascript
const li = document.createElement('li');
li.textContent = q;
li.style.cursor = 'pointer';
li.addEventListener('click', () => {
    taskInput.value = q;
    taskInput.style.height = 'auto';
    taskInput.style.height = Math.min(taskInput.scrollHeight, 180) + 'px';
    taskInput.focus();
    if (!intakePending) sendBtn.click();
});
ul.appendChild(li);
```

Also add a hover style so they look clickable. The `.cos-questions li` CSS rule should add:
```css
cursor: pointer;
transition: background 0.12s;
```
```css
.cos-questions li:hover {
    background: rgba(82,113,154,0.16);
    color: #c8daf0;
}
```

---

## Issue 5 — CoS can't read local files during intake (MEDIUM)

**What you see:** Screenshot shows CoS unable to access files. Files supplied in the Advanced panel are ignored during the CoS intake chat.

**Root cause — `/intake` endpoint and UI call both missing file support:**

In `server.py` the `IntakeRequest` model:
```python
class IntakeRequest(BaseModel):
    task: str
    branch: str = "plan"
    # no files_path field
```

In `index.html` the fetch call:
```javascript
body: JSON.stringify({ task: fullTask, branch: activeBranch() }),
// advFiles value is never included
```

And `ChiefOfStaffAgent.intake()` receives no file content — it only loads Obsidian context and agent knowledge.

**Fix — three-part change:**

1. **`server.py`** — add `files_path: str = ""` to `IntakeRequest` and load files in the handler:
```python
class IntakeRequest(BaseModel):
    task: str
    branch: str = "plan"
    files_path: str = ""

@app.post("/intake")
def intake(req: IntakeRequest):
    files_list = [f.strip() for f in req.files_path.split(",") if f.strip()]
    file_read_result = load_local_files(files_list)
    ...
    result = cos.intake(req.task, branch_hint=req.branch,
                        file_context=file_read_result["file_contents"])
    return result
```

2. **`chief_of_staff.py`** — accept and use `file_context` in `intake()`:
```python
def intake(self, task: str, branch_hint: str = "",
           file_context: dict | None = None) -> dict:
    ...
    file_block = ""
    if file_context:
        for path, content in file_context.items():
            file_block += f"\n--- {path} ---\n{content[:2000]}\n"
    raw = self._client.ask(
        system_prompt=self._intake_prompt,
        user_prompt=(
            f"Task: {task}\n\n"
            f"Branch hint: {branch_hint or 'not specified'}\n\n"
            f"Agent team knowledge:\n{agent_knowledge}\n\n"
            f"Vault context:\n{obsidian_block}"
            + (f"\n\nLocal files provided by user:\n{file_block}" if file_block else "")
        ),
    )
```

3. **`index.html`** — include the files value in the `/intake` fetch:
```javascript
body: JSON.stringify({
    task: fullTask,
    branch: activeBranch(),
    files_path: document.getElementById('advFiles')?.value || ''
}),
```

---

## Issue 6 — CoS feels generic / doesn't know you (MEDIUM, partially fixed by Issue 1)

**What you see:** CoS responses during intake feel like talking to a generic assistant. No sense it knows your projects, style, or what the team does.

**Root cause — two compounding problems:**

1. **Issue 1 (path mismatch)** means CoS never receives the agent team knowledge layer — so it literally doesn't know what agents exist.
2. The **voice/style guide** (`Voice Skill.md`) is loaded by the server and passed to the Writer, but never passed to `ChiefOfStaffAgent`. CoS intake gets vault context but not your voice profile.
3. The intake prompt (`chief_of_staff_intake.md`) doesn't explicitly instruct CoS to speak directly to Andrew by name or draw on his known context — it's written in a generic "the user" framing.

**Fixes:**

- Fix Issue 1 first — this alone will make a significant difference since CoS will actually know agent capabilities.
- Pass `voice_loader` to `ChiefOfStaffAgent.__init__()` and include it in the intake user prompt as a "Who Andrew is" block.
- Optionally update the intake prompt to be more direct and personalized: "You are talking to Andrew Godlewski. You have his vault context..."

---

## Issue 7 — `chief_of_staff_final` node card never activates in the UI (LOW)

**What you see:** The Chief of Staff Final Check card stays "waiting" during a run even while that agent is working.

**Root cause — node name mismatch in `index.html` NODE_TO_STEP map (line ~479):**

The graph's `timed_node` wrapper emits node name `"chief_of_staff_final"` (as named in `graph.py` line 308):
```python
timed_chief_final_node = timed_node("chief_of_staff_final", chief_final_node)
```

But NODE_TO_STEP uses the LangGraph node key `"chief_final"`:
```javascript
chief_final: 'chief_final',   // wrong — graph emits "chief_of_staff_final"
```

**Fix — change the key in NODE_TO_STEP:**
```javascript
// Before:
chief_final: 'chief_final',

// After:
chief_of_staff_final: 'chief_final',
```

---

## Issue 8 — Empty Draft tab after a plan run (INVESTIGATE FIRST)

**What you see:** human_review fires (approval gate appears) but the Draft tab is blank or shows placeholder.

**What I confirmed from the code:**

The server path is correct — `human_review_fn(draft, state)` receives the draft string, puts `{type: "human_review", draft: draft, ...}` in the event queue, and the SSE generator yields it. The terminal proof is the `=== Draft for human review ===` block that prints the full content.

The UI path also looks correct — `handleSseEvent` receives the event, `event.draft` is extracted, and `setViewContent('draft', draftHtml)` is called.

**The issue I can't rule out from reading alone — silent JSON parse failures:**

The SSE message listener swallows all errors silently:
```javascript
es.addEventListener('message', e => {
    try { handleSseEvent(JSON.parse(e.data)); } catch {}
    //                                              ^^^ eats everything
});
```

If `JSON.parse(e.data)` throws for any reason (malformed output from the AI inside `reviewer_findings`, unusual Unicode, etc.), `handleSseEvent` is never called, and the draft tab is never updated. You'd see the approval UI appear (which is triggered by a later event? — no, approval UI is triggered by the same `human_review` event) which would mean the event DID parse...

**Actually the most likely real cause:** If `event.draft` arrives as an **empty string**, the fallback shows "Draft was empty — check terminal for agent errors." rather than blank. But you said it's blank, which means either: (a) the `human_review` event is never received, or (b) the `branch` variable resolves wrong and `setViewContent` targets the wrong view ID.

**How to definitively diagnose — open DevTools console before your next run:**

The `console.log` diagnostic already in the code will print:
```
[human_review] draft length: N | branch: plan | isSeq: false
```

- If `draft length: 0` → server is sending empty draft → check writer agent output
- If `draft length: N` → event received correctly → DOM targeting issue, check if `[data-view="draft"]` exists
- If the log never appears → SSE event is being dropped → change the catch block to `catch(err) { console.error('[SSE]', err); }`

**Immediate fix to add while investigating — change the silent catch:**
```javascript
// Before:
try { handleSseEvent(JSON.parse(e.data)); } catch {}

// After:
try { handleSseEvent(JSON.parse(e.data)); } catch(err) {
    console.error('[SSE parse error]', err.message, e.data?.slice(0, 300));
}
```

---

## Issue 9 — Terminal logging confusion (NOT A BUG — explanation)

**What you thought:** Something changed and you can no longer see the full terminal output.

**What actually happened:**

After the git push you ran `uvicorn app.server:app --reload` from `AgentTeam/` (the repo root). This immediately crashed:
```
ModuleNotFoundError: No module named 'app'
```
because Python couldn't find the `app` module from that directory.

You then ran `cd agent_team && uvicorn app.server:app --reload` which worked fine and showed full `[server]`, `[flow]`, and `[artifact_writer]` logs. In the final `make run` session you can see those logs are still there — there just weren't any completed runs in that session (only 5 intake calls).

**The correct way to start the server is always:**
```bash
make run              # from AgentTeam/ — Makefile does the cd for you
# OR
cd agent_team && uvicorn app.server:app --reload
```

Nothing changed about logging. `make run` is the canonical command going forward.

---

## Issue 10 — Orchestration view redesign (DESIGN WORK)

**What you see:** The middle panel shows all agents in a linear trail immediately on page load, including agents that haven't been called and won't be called. You want: cards only for invoked agents, in order, each with a line explaining why.

**Current architecture:** `render()` pre-renders all steps for the selected branch as "waiting" cards on every render call. There's no mechanism to start with an empty rail and add cards as events arrive.

**Proposed approach:**

1. On page load / branch switch: show only a placeholder ("Waiting for run to start…")
2. On `node_start` event: dynamically append a card for that node, marked active
3. On `node_complete` event: mark the card complete; add a "why" line sourced from the CoS work order (`objective`, `work_order.success_criteria`)
4. On `human_review` event: add the Human Review card
5. The CoS work order is already in the SSE stream (you could emit it as a `work_order` event type from `on_node_exit("chief_of_staff", ...)` in the server)

This is the most significant UI change of the batch — best saved for after the chat flow bugs are fixed.

---

## Priority order for the morning session

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 1 | Agent knowledge layer path fix | 2 lines | Unlocks CoS intelligence |
| 2 | Send button blocked after ready | 1 word | Core UX, broken today |
| 3 | Input text stays after send | 2 lines | Feels broken immediately |
| 4 | Questions not clickable | ~10 lines | Enables the Claude-style flow you want |
| 7 | NODE_TO_STEP key mismatch | 1 line | Easy win while in the file |
| 8 | Empty draft — add error logging | 1 line | Diagnostic first, then fix |
| 5 | Files in intake | 3-file change | Needed for CoS to be useful |
| 6 | CoS personalization | Prompt work | Depends on 1 + 5 being done |
| 10 | Orchestration view redesign | Significant | Save for last |

Issues 1–4 and 7 are all small, targeted changes. Doing them together in one session is reasonable. Issue 8 needs one run with DevTools open to confirm the root cause before writing the fix.

---

## Quick reference — all file locations

| File | Path |
|------|------|
| UI (all JS + CSS + HTML) | `design/ui_prototype_v1/index.html` |
| FastAPI server | `agent_team/app/server.py` |
| LangGraph graph | `agent_team/app/graph.py` |
| Shared state schema | `agent_team/app/state.py` |
| Chief of Staff agent | `agent_team/agents/chief_of_staff.py` |
| Intake prompt | `agent_team/prompts/chief_of_staff_intake.md` |
| Agent knowledge loader | `agent_team/tools/agent_knowledge_loader.py` |
| Agent docs folder | `agent_team/agent_docs/` (verify it exists on disk) |
| Start server | `make run` from `AgentTeam/` |
