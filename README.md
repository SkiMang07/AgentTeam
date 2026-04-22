# Agent Team

A local multi agent scaffold built with OpenAI for model calls and LangGraph for orchestration.

This project is the first practical version of an agent team system. The goal is not to build a giant autonomous circus on day one. The goal is to build a small, clear, usable foundation that can grow.

## What this does

Version one includes:

1. A **Chief of Staff** agent that interprets the task and routes work
2. A **Researcher** agent that extracts facts and gaps
3. A **Writer** agent that drafts output using approved facts
4. A **Reviewer** agent that runs a structured quality-control pass on the draft
5. An optional **JT** agent stage for explicit JT requests
6. A **human review** step before finalization
7. A local **CLI** entry point for testing workflows

## Current scope

This is intentionally narrow.

Included in version one:

- Python project scaffold
- OpenAI Responses API model calls
- LangGraph state graph
- Explicit shared state
- Prompt files stored separately from code
- CLI based execution

Not included yet:

- HubSpot integration
- Slack integration
- email or calendar actions
- database persistence
- web UI
- vector search
- complex toolchains
- more than three agents

## Why this exists

The purpose of this repo is to create a real agent orchestration foundation that is:

- understandable
- extendable
- safe
- boring in the right ways

The system should use small specialized roles, explicit state, and review gates instead of pretending we built an AI company org chart because the internet said so.

## Project structure

agent_team/
  app/
    main.py
    graph.py
    state.py
    config.py
  agents/
    chief_of_staff.py
    researcher.py
    writer.py
  tools/
    openai_client.py
  prompts/
    chief_of_staff.md
    researcher.md
    writer.md
  requirements.txt
  .env.example
  README.md
  AGENTS.md

Agent roles
Chief of Staff

Responsibilities:

understand the user request
determine what type of workflow is needed
route work to the right next step
keep the process structured
avoid guessing when research is needed
Researcher

Responsibilities:

extract factual claims
identify known gaps
return structured findings
separate fact from assumption
Writer

Responsibilities:

draft output from approved facts
avoid inventing details
produce a clean usable deliverable
stay within the provided evidence
Workflow shape

The initial workflow is:

user submits task
Chief of Staff classifies and routes
Researcher gathers facts if needed
Writer drafts the response
Reviewer runs a structured QC pass and returns normalized findings
JT node runs only when explicitly requested (`--jt`, `--jt-mode advisory`, `--jt-mode full_challenge`, or task text)
JT returns structured feedback plus a rewritten artifact (`jt_feedback`, `jt_rewrite`) in shared state
Reviewer validates the JT rewrite artifact on JT paths (and writer draft on non-JT paths)
Chief of Staff runs a final pass and can request one final redraft
The final Chief of Staff pass stores a short structured alignment/completeness validation result in shared state
human review pauses the flow as the final approval gate
final output is approved or sent back for revision

Project memory (session-local, explicit, narrow):

- Shared state now separates **current run state** (`current_run`) from **carried project memory** (`project_memory`).
- `project_memory` contract fields:
  - `current_objective`
  - `active_deliverable_type`
  - `open_questions`
  - `latest_draft`
  - `latest_approved_output`
- Memory is carried only within the same local CLI process and printed in the terminal for inspection.
- Chief of Staff may use memory as continuity context for planning, but memory is not treated as grounded evidence/fact by default.
- If a task explicitly asks to inspect stored session memory (for example, asks for `latest_approved_output`), routing switches to a memory-lookup path that reads the stored memory value directly instead of paraphrasing the current prompt.
- Memory lookup is intent-aware for supported fields: `latest_approved_output`, `current_objective`, and `active_deliverable_type` (including combined field requests).
- Transformational requests (for example, “rewrite the latest approved output…”) continue through normal drafting flow and do not force lookup-only routing.

What project memory does in v1:

- Carries objective/deliverable/open questions forward into the next run in the same local session.
- Carries latest draft and latest approved output across runs in the same local session.
- Supports explicit same-session retrieval of `project_memory.latest_approved_output` and returns the stored artifact value when present.
- Supports explicit same-session retrieval of `project_memory.current_objective` and `project_memory.active_deliverable_type` when asked.
- Keeps the memory contract explicit and typed in shared state.

What project memory does not do in v1:

- No database storage.
- No vector store or embeddings.
- No cross-process persistence after CLI exit.
- No hidden autonomous retrieval or background memory updates.

Chief of Staff structured work order (canonical shared contract):

- `objective` (string)
- `deliverable_type` (string)
- `success_criteria` (list of strings)
- `research_needed` (boolean)
- `open_questions` (list of strings)
- `jt_requested` (boolean)

JT routing precedence:

- `work_order.jt_requested` is the canonical routing source.
- The top-level `jt_requested` field is maintained for compatibility and derived flow state, but routing decisions should resolve from the canonical work order value.
- Explicit JT requests from CLI flags or explicit task text are preserved through normalization and cannot be silently downgraded by model output.

Reviewer structured contract (canonical QC artifact in shared state):

Reviewer is a QC validator only: it identifies issues and recommends next action; it does not produce rewrites.

- `overall_assessment` (string)
- `missing_content` (list of strings)
- `unsupported_claims` (list of strings)
- `contradictions_or_logic_problems` (list of strings)
- `format_or_structure_issues` (list of strings)
- `recommended_next_action` (`approve` | `revise` | `reject`)

Downstream use of reviewer findings:

- Graph routing continues using deterministic approval + feedback fields derived from the structured reviewer findings
- Chief of Staff final pass consumes the structured reviewer findings block directly
- JT challenge stage (when requested) consumes the same structured reviewer findings block
- Unsupported claims and core fact contradictions are treated as higher-priority blockers than cosmetic format polish
Design principles

This repo follows a few simple rules:

Keep state explicit
Prefer simple over clever
Separate reasoning from control flow
Keep prompts out of Python files
Require human review for final output
Build one useful workflow before adding complexity
Requirements
Python 3.11 or later recommended
OpenAI API key
virtual environment support
Setup
1. Create a virtual environment

Mac or Linux:

python -m venv .venv
source .venv/bin/activate

Windows PowerShell:

python -m venv .venv
.venv\Scripts\Activate.ps1
2. Install dependencies
pip install -r requirements.txt
3. Set environment variables

Copy the example file:

cp .env.example .env

Then add your OpenAI API key and preferred model to .env.

Example:

OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-5.4
Running the app

Run the local CLI:

python -m app.main

When you run without a quoted task argument, the CLI supports multi-run local sessions and will ask whether to continue after each run. This is how session-local `project_memory` is carried to later runs in v1.

Optional JT challenge stage:

python -m app.main --jt "your task here"

Optional JT mode label:

python -m app.main --jt-mode advisory "your task here"

Optional debug mode:

python -m app.main --debug --jt-mode advisory "your task here"


Optional bounded local file evidence input:

python -m app.main --files-path ../README.md "Summarize the local project setup"

Multiple explicit evidence paths:

python -m app.main --files-path ../PROJECT_PLAN.md --files-path ../README.md "Draft a concise project status update"

To run explicit JT challenge routing:

python -m app.main --jt-mode full_challenge "your task here"

You can also explicitly request JT in task text (for example: `JT requested: true`, `JT mode: full_challenge`).

For local JT regression coverage on external communication and edit quality, use the prompts and scoring rubric in `JT Tests.md`.

You should then be prompted to enter a task for the agent team.

Example prompts:

Prepare a one page brief for tomorrow’s leadership meeting
Summarize the key risks and gaps in this project approach
Turn these notes into a clear executive update

Local file evidence workflow (v1)

You can pass explicit local file or folder paths through `--files-path`.

Bounded behavior in this first version:
- Allowed file types: `.md`, `.txt`, `.py`, `.json`, `.yaml`, `.yml`, `.csv`
- Folder traversal depth: max depth `1`
- Max files read per run: `8`
- Read scope is explicit only: the system reads only the paths you provide and files that pass these bounds.

State fields captured each run:
- `files_requested`
- `files_read`
- `files_skipped`
- `skip_reasons`

The graph builds a structured evidence bundle from files actually read and includes:
- headings
- bullet lines
- short key content snippets
- non-empty line counts

Researcher and Writer both consume this evidence bundle so facts and drafts are grounded in selected local files rather than generic responses.
Reviewer validates both content grounding and file-scope honesty.
The system should not claim it read files that were skipped or unsupported.

Expected behavior

Depending on the request, the system may:

route directly to drafting
do a research pass first
pause for human review before finalizing

That pause is intentional. It is there so the system does not act more confident than it deserves.

Environment variables
Required
OPENAI_API_KEY
Your OpenAI API key
Optional
OPENAI_MODEL
Model name to use for Responses API calls
Default can be set in code if omitted
Version one limitations

Be honest about what this is.

Current limitations:

research is still lightweight and local to the current flow
no real external retrieval yet
no persistence beyond the current run unless added later
no UI beyond CLI
no business system integrations
no tracing or automated eval framework yet (manual JT regression checks live in `JT Tests.md`)
Next likely steps

After the scaffold is running, the most sensible next steps are:

add structured output validation
improve routing behavior in Chief of Staff
add simple persistence or checkpoint visibility
introduce one real integration only after the local flow is stable
Development notes

This repo should evolve in phases.

Phase 1

Get the scaffold working locally.

Phase 2

Improve prompts, routing, and structure.

Phase 3

Add limited retrieval from local files.

Phase 4

Add one real external system if needed.

Phase 5

Expand carefully, not because it sounds cool.

Contributing to the repo

When making changes:

keep version one small
avoid extra abstraction unless it earns its keep
prefer clarity over framework cleverness
explain any non obvious design decision
do not add major integrations casually

Also, read AGENTS.md before making changes. That file is the standing instruction layer for this repo.
