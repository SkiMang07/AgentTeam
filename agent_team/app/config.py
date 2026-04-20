from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    model: str = "gpt-4.1-mini"


load_dotenv()


def get_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to your .env file.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    return Settings(openai_api_key=api_key, model=model)
