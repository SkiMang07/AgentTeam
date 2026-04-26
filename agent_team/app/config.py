from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    # Global fallback model — used by any agent that does not have its own override.
    model: str = "gpt-4.1-mini"

    # ── Per-agent model overrides ─────────────────────────────────────────────
    # Set any of these in .env to pin a specific agent to a specific model.
    # An empty string means "use the global `model` fallback above."
    #
    # Plan branch
    model_chief_of_staff: str = ""   # Chief of Staff (intake + routing + final check)
    model_researcher: str = ""        # Researcher
    model_writer: str = ""            # Writer
    model_reviewer: str = ""          # Reviewer
    model_jt: str = ""                # JT challenge agent
    # Build pod
    model_backend: str = ""           # Backend agent
    model_frontend: str = ""          # Frontend agent
    model_qa: str = ""                # QA agent
    # Brainstorm pod
    model_advisor_router: str = ""    # Advisor Router
    model_advisor: str = ""           # Advisor synthesis agent
    model_advisor_clusters: str = ""  # All 5 advisor cluster agents (shared override)

    # Optional: absolute path to the root of your Obsidian vault.
    # When set, CoS and Researcher navigate CLAUDE.md files to load project context.
    obsidian_vault_path: str = ""
    # Optional: absolute path to your voice/style guide file inside Obsidian (or anywhere).
    # When set, the Writer injects this into its system prompt on every draft.
    voice_file_path: str = ""
    # Optional: default directory where agent output files are written.
    # Set OUTPUT_DIR in your .env to make every run save files there automatically.
    # The UI can override this per-run via the Output folder field.
    output_dir: str = ""
    # Path to the session persistence file.
    # Saves ProjectMemory (objective, approved output, open questions, etc.) across
    # restarts so the team can pick up where it left off.
    # Resolution order: SESSION_FILE env var → OUTPUT_DIR/session_memory.json → ~/.agent_team/session_memory.json
    session_file: str = ""

    def agent_model(self, agent: str) -> str:
        """Return the resolved model string for the named agent.

        Priority: per-agent override → global ``model`` fallback.
        The five advisor cluster agents share a single override key
        (``model_advisor_clusters``) for convenience.
        """
        _map: dict[str, str] = {
            "chief_of_staff": self.model_chief_of_staff,
            "researcher": self.model_researcher,
            "writer": self.model_writer,
            "reviewer": self.model_reviewer,
            "jt": self.model_jt,
            "backend": self.model_backend,
            "frontend": self.model_frontend,
            "qa": self.model_qa,
            "advisor_router": self.model_advisor_router,
            "advisor": self.model_advisor,
            # "advisor_clusters" is a convenience display key used in model printouts;
            # the five cluster agent keys below are the canonical resolution paths.
            "advisor_clusters": self.model_advisor_clusters,
            "strategy_systems_advisor": self.model_advisor_clusters,
            "leadership_culture_advisor": self.model_advisor_clusters,
            "communication_influence_advisor": self.model_advisor_clusters,
            "growth_mindset_advisor": self.model_advisor_clusters,
            "entrepreneur_execution_advisor": self.model_advisor_clusters,
        }
        return _map.get(agent, "") or self.model


load_dotenv()


def get_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to your .env file.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    obsidian_vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    voice_file_path = os.getenv("VOICE_FILE_PATH", "").strip()
    output_dir = os.getenv("OUTPUT_DIR", "").strip()

    # ── Session persistence file path ─────────────────────────────────────────
    # Resolution order: SESSION_FILE env var → OUTPUT_DIR/session_memory.json
    #                   → ~/.agent_team/session_memory.json
    session_file = os.getenv("SESSION_FILE", "").strip()
    if not session_file:
        if output_dir:
            session_file = str(Path(output_dir) / "session_memory.json")
        else:
            session_file = str(Path.home() / ".agent_team" / "session_memory.json")

    return Settings(
        openai_api_key=api_key,
        model=model,
        # Per-agent overrides — default to empty string (falls back to global model)
        model_chief_of_staff=os.getenv("MODEL_CHIEF_OF_STAFF", "gpt-4.1").strip(),
        model_researcher=os.getenv("MODEL_RESEARCHER", "").strip(),
        model_writer=os.getenv("MODEL_WRITER", "").strip(),
        model_reviewer=os.getenv("MODEL_REVIEWER", "").strip(),
        model_jt=os.getenv("MODEL_JT", "").strip(),
        model_backend=os.getenv("MODEL_BACKEND", "").strip(),
        model_frontend=os.getenv("MODEL_FRONTEND", "").strip(),
        model_qa=os.getenv("MODEL_QA", "").strip(),
        model_advisor_router=os.getenv("MODEL_ADVISOR_ROUTER", "").strip(),
        model_advisor=os.getenv("MODEL_ADVISOR", "").strip(),
        model_advisor_clusters=os.getenv("MODEL_ADVISOR_CLUSTERS", "").strip(),
        obsidian_vault_path=obsidian_vault_path,
        voice_file_path=voice_file_path,
        output_dir=output_dir,
        session_file=session_file,
    )
