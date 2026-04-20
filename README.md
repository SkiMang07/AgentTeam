# Agent Team

A local multi agent scaffold built with OpenAI for model calls and LangGraph for orchestration.

This project is the first practical version of an agent team system. The goal is not to build a giant autonomous circus on day one. The goal is to build a small, clear, usable foundation that can grow.

## What this does

Version one includes:

1. A **Chief of Staff** agent that interprets the task and routes work
2. A **Researcher** agent that extracts facts and gaps
3. A **Writer** agent that drafts output using approved facts
4. A **human review** step before finalization
5. A local **CLI** entry point for testing workflows

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
human review pauses the flow
final output is approved or sent back for revision
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

You should then be prompted to enter a task for the agent team.

Example prompts:

Prepare a one page brief for tomorrow’s leadership meeting
Summarize the key risks and gaps in this project approach
Turn these notes into a clear executive update
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
no tracing or eval framework yet
Next likely steps

After the scaffold is running, the most sensible next steps are:

add structured output validation
improve routing behavior in Chief of Staff
add local file retrieval from project docs
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
