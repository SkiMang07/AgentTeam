# Agent Team

A local CLI-based multi-agent scaffold using:
- OpenAI Responses API
- LangGraph orchestration
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

## Human review step

Every branch pauses at Human Review:
- `Approve final output? [y/N]`
- Optional revision notes if not approved — Writer re-runs with notes, then re-reviews before returning to approval.

## Notes

- Intentionally local and CLI-based. No web app, DB, or external integrations.
- All prompts live in `prompts/` as separate `.md` files — keep them there.
- SharedState is the single source of truth — all agents read from and write to it.
