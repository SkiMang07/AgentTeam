# Agent Team — convenience targets
# Run all commands from the AgentTeam/ root.

.PHONY: run run-debug cli help

## Start the FastAPI dev server (hot-reload on)
run:
	cd agent_team && uvicorn app.server:app --reload

## Start with extra debug output
run-debug:
	cd agent_team && uvicorn app.server:app --reload --log-level debug

## Run a one-shot task from the CLI (pass TASK="your task here")
cli:
	cd agent_team && python -m app.main $(TASK)

help:
	@echo "make run       — start the dev server"
	@echo "make run-debug — start with debug logging"
	@echo "make cli TASK=\"your task\" — run one task via CLI"
