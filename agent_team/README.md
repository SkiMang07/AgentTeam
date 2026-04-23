# Agent Team

A multi-agent workflow using:
- OpenAI Responses API
- LangGraph orchestration
- FastAPI + SSE streaming web console
- python-dotenv for environment loading
- Explicit typed shared state

## Routing branches

The system has three branches after Chief of Staff:

**Plan** (default — drafting and writing tasks)
Chief of Staff → Researcher / Evidence → Writer → (JT if requested) → Reviewer → CoS Final Check → Human Review

**Build** (`--dev-pod` flag or explicit code request)
Chief of Staff → Pod Entry → Backend → Frontend → QA (bounded revision loop) → Assemble → Human Review

**Brainstorm** (`--advisor` flag or explicit advisor request)
Chief of Staff → Advisor Entry → 5 specialist clusters → Advisor Synthesis → Human Review

## Included agents

**Plan branch:** Chief of Staff, Researcher, Writer, Reviewer, JT (optional modifier)

**Build branch:** Backend, Frontend, QA

**Brainstorm branch:** Advisor (synthesis), StrategySystemsAdvisor, LeadershipCultureAdvisor, CommunicationInfluenceAdvisor, GrowthMindsetAdvisor, EntrepreneurExecutionAdvisor

## Running the web console

The web console is the primary interface. Start it from inside `agent_team/`:

```bash
cd agent_team
uvicorn app.server:app --reload
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

The console exposes three branch cards (Plan, Build, Brainstorm) and a live progress sidebar. You can run branches individually or chain them in sequence (e.g. Brainstorm → Plan, where the brainstorm output automatically becomes the plan's task input).

**Sequence mode:** Select multiple branches, enter your task once, and the system runs them in order. Each branch's final output is fed as the task to the next branch automatically.

**Human review gate:** When a branch reaches human review, the UI pauses and displays the draft. You can approve or send back with revision notes. The server holds the graph thread open (up to 10 minutes) while it waits for your response.

**Page reset:** Refreshing the browser clears all UI state, including any files path input. No separate reset button is needed.

## CLI flags

```bash
python -m app.main "your task"                        # Plan branch (default)
python -m app.main --jt "your task"                   # Plan with JT challenge stage
python -m app.main --jt-mode advisory "your task"     # Plan with JT in advisory mode
python -m app.main --dev-pod "your task"              # Build branch
python -m app.main --advisor "your task"              # Brainstorm branch
python -m app.main --web-search "your task"           # Plan with live web search
python -m app.main --files-path ../file.md "task"     # Plan with local file evidence
python -m app.main --debug "your task"                # Debug mode (prints node artifacts)
```

## Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy environment template:
   ```bash
   cp .env.example .env
   ```
4. Add your OpenAI API key to `.env`.

## Configuration

Set these environment variables in `.env`:

- `OPENAI_API_KEY` (required): your OpenAI API key.
- `OPENAI_MODEL` (optional): model name. Defaults to `gpt-4.1-mini`.
- `OBSIDIAN_VAULT_PATH` (optional): path to your Obsidian vault for task grounding.
- `VOICE_FILE_PATH` (optional): path to a voice/style guide file for the Writer.

## Server API

### `GET /run` — SSE stream

Starts a graph run and streams progress events. Query parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task` | string | required | The task to run |
| `branch` | string | `"plan"` | `"plan"`, `"build"`, or `"brainstorm"` |
| `jt_enabled` | bool | `false` | Enable JT challenge stage |
| `files_path` | string | `""` | Comma-separated local file/folder paths |
| `web_search` | bool | `false` | Enable live web search for Researcher |
| `output_format` | string | `"Chat"` | Hint to CoS for desired output format |
| `mem_session` | string | `""` | Key for carrying project memory across runs |

**SSE event types** (JSON in `data:` field):

| Event type | Fields | Description |
|---|---|---|
| `session` | `session_id` | First event — use this to send `/approve` |
| `node_start` | `node` | Graph node started |
| `node_complete` | `node`, `elapsed_ms` | Graph node finished |
| `human_review` | `draft`, `reviewer_findings` | Graph paused at human review gate |
| `final` | `output`, `status`, `execution_path`, `node_timings_ms` | Run complete |
| `error` | `message` | Run failed |
| `heartbeat` | — | Keepalive every 25 seconds |

### `POST /approve` — Human review response

Unblocks the human review gate.

```json
{ "session_id": "...", "approved": true, "notes": "" }
```

### `GET /` — Web console

Serves the live console UI from `design/ui_prototype_v1/index.html`.

### `GET /health` — Health check

Returns `{"status": "ok"}`.

## Human review step (CLI)

Every branch pauses at Human Review:
- `Approve final output? [y/N]`
- Optional revision notes if not approved — Writer re-runs with notes, then re-reviews before returning to approval.

## Notes

- All prompts live in `prompts/` as separate `.md` files — keep them there.
- SharedState is the single source of truth — all agents read from and write to it.
- Agents are cached globally at startup; the LangGraph is rebuilt per-request with per-session callbacks.
- The graph thread blocks on `threading.Event` during human review; the `/approve` endpoint releases it.
