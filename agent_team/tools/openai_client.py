from __future__ import annotations

from openai import OpenAI

from app.config import Settings


class ResponsesClient:
    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.model

    def ask(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.output_text.strip()
