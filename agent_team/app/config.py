from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    model: str = "gpt-4.1-mini"
    # Optional: absolute path to the root of your Obsidian vault.
    # When set, CoS and Researcher navigate CLAUDE.md files to load project context.
    obsidian_vault_path: str = ""
    # Optional: absolute path to your voice/style guide file inside Obsidian (or anywhere).
    # When set, the Writer injects this into its system prompt on every draft.
    voice_file_path: str = ""


load_dotenv()


def get_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to your .env file.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    obsidian_vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    voice_file_path = os.getenv("VOICE_FILE_PATH", "").strip()

    return Settings(
        openai_api_key=api_key,
        model=model,
        obsidian_vault_path=obsidian_vault_path,
        voice_file_path=voice_file_path,
    )
