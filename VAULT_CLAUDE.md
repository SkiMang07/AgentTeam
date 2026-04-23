# AgentTeam — Obsidian Vault Context

This folder contains the AgentTeam project: a local multi-agent CLI system built by Andrew Godlewski using Python, LangGraph, and the OpenAI Responses API.

## What this project is

AgentTeam is a local-first, CLI-based multi-agent workflow. It is not a chat UI, not a SaaS product, and not a platform play. The goal is a narrow, inspectable v1 that produces better output than a plain chat window by routing tasks through specialized agents with explicit state.

Human review is always the final gate before output is used.

## Agent roster

- **Chief of Staff** — interprets the task, builds a structured work order, routes to research or direct writing, runs a final alignment pass before human review
- **Researcher** — extracts facts and identifies gaps; can access Obsidian vault context and optionally run live web search (`--web-search` flag)
- **Writer** — drafts output from approved facts and evidence; has Andrew's voice/style guide baked into its system prompt at startup
- **Reviewer** — structured QC pass; checks for unsupported claims, missing content, and format issues; returns normalized findings object
- **JT** — optional adversarial challenge stage; only runs when explicitly requested via `--jt` flag or task text

## Three tools integrated (as of 2026-04-22)

**Obsidian Context Navigator** (`tools/obsidian_context.py`)
Walks the vault to depth 3, finds all CLAUDE.md files, asks an LLM to select the 3 most relevant folders for the current task, then loads CLAUDE.md content + file snippets from those folders into the Chief of Staff and Researcher prompts. This is how the agents know about Andrew's active projects, priorities, and knowledge landscape. It degrades gracefully if no relevant folders are found.

**Voice Loader** (`tools/voice_loader.py`)
Reads Andrew's voice/style guide from `03 Resources/How To/Voice Skill.md` at startup and bakes the full content into the Writer agent's system prompt. The goal is that every draft the Writer produces sounds like Andrew wrote it — first-person, direct, no filler, no AI closers. It degrades gracefully if the file is missing.

**Web Search** (`tools/openai_client.py` → `ask_with_tools()`)
Opt-in only via `--web-search` CLI flag. When enabled, the Researcher calls the OpenAI Responses API with `web_search_preview` tool enabled to pull live external information. Never runs automatically. Only activates when `--web-search` is passed AND `research_needed` is true AND no local file evidence is already loaded.

## Current build state (as of 2026-04-23)

All three tools are wired and loading at startup. The pipeline runs end-to-end cleanly. The project now has a live web console in addition to the CLI.

**Tool effectiveness fixes shipped 2026-04-22:**
- CoS routing now sends project-specific writing tasks through the Researcher — vault context and approved facts reach the Writer
- `--web-search` flag forces routing through Researcher — web search reliably fires when the flag is passed
- Writer voice guide moved earlier in the prompt; hard format constraints added (no headers, no bullets, no AI closers unless task requires them)
- Vault walk depth increased from 2 to 3 so project-level CLAUDE.md files are discovered correctly
- CoS prompt updated to extract vault specifics into work order success criteria — Writer receives grounded, project-specific instructions rather than generic ones

**Web console shipped 2026-04-23:**
- FastAPI server (`agent_team/app/server.py`) with SSE streaming — start with `uvicorn app.server:app --reload` from `agent_team/`
- Browser UI at `http://localhost:8000` — three branch cards (Plan, Build, Brainstorm), live progress sidebar, human review approval gate
- Sequential branch execution: Brainstorm → Plan chains automatically, feeding brainstorm output as the plan task
- Developer pod (Phase 3) wired into UI — pod output pauses at browser approval gate just like plan/brainstorm

**Phase 3 Developer Pod shipped 2026-04-22:**
- Three new agents: Backend, Frontend, QA
- Internal QA revision loop (max 2 cycles) before escalating to human review
- Invoked via `--dev-pod` CLI flag or `Build` branch in web console

## What's next

- First real pod task: AgriWebb sales discovery tool
- Confirm JT still works independently on non-pod tasks (regression check pending)
- Keep CLAUDE.md files updated as the project evolves — stale context produces stale output

## Repo location

`/Users/andrewgodlewski/Desktop/Obsidian/main/01 Projects/Personal/Agent Team/AgentTeam/`
GitHub: https://github.com/SkiMang07/AgentTeam

## Project principles

- Keep v1 small and local-first
- No UI, no business integrations, no additional agents until the core loop is solid
- Human review is always required
- Prefer clarity over cleverness
- One useful workflow before adding complexity
