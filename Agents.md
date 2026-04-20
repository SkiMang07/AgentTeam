# AGENTS.md

## Project goal

Build a local multi agent system using OpenAI Responses API for model calls and LangGraph for orchestration.

This project is an early stage scaffold for an "Agent Team" system with:
1. Chief of Staff agent
2. Researcher agent
3. Writer agent
4. Human review step

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

1. Do not overengineer version one
2. Do not add Slack, HubSpot, email, calendar, or database integrations yet
3. Do not add extra agents beyond Chief of Staff, Researcher, and Writer
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
3. The human review step should be real, not hand waved
4. Keep the first pass boring and solid