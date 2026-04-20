# Agent Team (v1 scaffold)

A local CLI-based multi-agent scaffold using:
- OpenAI Responses API
- LangGraph orchestration
- python-dotenv for environment loading
- Explicit typed shared state

## Included agents
1. Chief of Staff
2. Researcher
3. Writer
4. Reviewer

## What v1 does
- Accepts a user task from CLI input.
- Chief of Staff classifies and routes the task.
- Researcher extracts structured facts and gaps.
- Writer drafts output from approved facts.
- Reviewer performs a quality/factuality pass on the draft.
- If Reviewer flags issues, the system performs one automatic redraft before human review.
- Human review pauses before finalization.

## Project structure

```text
agent_team/
  app/
    main.py
    graph.py
    state.py
    config.py
  agents/
    chief_of_staff.py
    researcher.py
    reviewer.py
    writer.py
  tools/
    openai_client.py
  prompts/
    chief_of_staff.md
    researcher.md
    reviewer.md
    writer.md
  requirements.txt
  .env.example
  README.md
```

## Setup

1. Create and activate a virtual environment.
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

Set these environment variables in `.env` (loaded via `python-dotenv`):

- `OPENAI_API_KEY` (required): your OpenAI API key.
- `OPENAI_MODEL` (optional): model name to use. Defaults to `gpt-4.1-mini`.

The default `OPENAI_MODEL` value is a starter setting for local v1 usage convenience, not a recommendation of the “best” model.

## Run

From `agent_team/`:

```bash
python -m app.main "Draft a short policy memo about remote work expectations"
```

Or run without arguments and enter a task interactively:

```bash
python -m app.main
```

## Human review step

The graph pauses after draft generation and asks:
- Approve final output? `[y/N]`
- Optional revision notes when not approved

If notes are provided, Writer runs one more time with the reviewer note added to approved facts.
That human-note redraft is then reviewed again by Reviewer before returning to human approval.

## Notes

- This is intentionally simple and local.
- No web app, DB, or external integrations are included in v1.
- Future iterations can add tool-using research, richer review loops, and persistent state.
