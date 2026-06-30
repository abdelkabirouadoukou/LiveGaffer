"""
Gemini client — the fallback LLM provider.

Used automatically by `tactical_analyst.py` when Groq fails (rate limit,
outage, missing key). Google AI Studio's free tier makes this a zero-cost
safety net.

Note: uses the current unified `google-genai` SDK (`pip install google-genai`),
not the deprecated `google-generativeai` package.
"""

from __future__ import annotations

from google import genai
from google.genai import types
from google.genai.errors import APIError

from config.settings import Settings, get_settings
from src.ai_engine.base_llm_client import LLMClient
from src.ai_engine.exceptions import LLMGenerationError
from src.utils.logger import get_logger

log = get_logger(__name__)


class GeminiClient(LLMClient):
    """Async wrapper around Gemini's generate_content API, JSON-mode enabled."""

    provider_name = "gemini"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: genai.Client | None = None

    def _ensure_client(self) -> genai.Client:
        if self._client is None:
            if not self._settings.gemini_api_key:
                raise LLMGenerationError(
                    "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com",
                    provider=self.provider_name,
                )
            self._client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._client

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        client = self._ensure_client()
        try:
            response = await client.aio.models.generate_content(
                model=self._settings.gemini_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=0.4,
                    max_output_tokens=1500,
                ),
            )
        except APIError as exc:
            raise LLMGenerationError(f"Gemini API error: {exc}", provider=self.provider_name) from exc
        except TimeoutError as exc:
            raise LLMGenerationError("Gemini request timed out", provider=self.provider_name) from exc

        if not response.text:
            raise LLMGenerationError("Gemini returned an empty response", provider=self.provider_name)

        log.debug("Gemini generated {} chars", len(response.text))
        return response.text
