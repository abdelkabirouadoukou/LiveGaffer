"""
Groq client — the primary LLM provider.

Groq's free tier is used as the primary engine because it's fast (LPU
inference) and has generous free rate limits, which matters for a *live*
assistant that may re-analyze the match every poll cycle.
"""

from __future__ import annotations

from groq import APIConnectionError, APIStatusError, AsyncGroq, RateLimitError

from config.settings import Settings, get_settings
from src.ai_engine.base_llm_client import LLMClient
from src.ai_engine.exceptions import LLMGenerationError
from src.utils.logger import get_logger

log = get_logger(__name__)


class GroqClient(LLMClient):
    """Async wrapper around Groq's chat completions API, JSON-mode enabled."""

    provider_name = "groq"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: AsyncGroq | None = None

    def _ensure_client(self) -> AsyncGroq:
        if self._client is None:
            self._client = AsyncGroq(api_key=self._settings.require_groq_key())
        return self._client

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        client = self._ensure_client()
        try:
            response = await client.chat.completions.create(
                model=self._settings.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                # JSON mode: Groq guarantees syntactically valid JSON output when
                # the word "JSON" also appears in the prompt (it does, in our schema spec).
                response_format={"type": "json_object"},
                temperature=0.4,
                max_tokens=1500,
            )
        except RateLimitError as exc:
            raise LLMGenerationError(f"Groq rate limit hit: {exc}", provider=self.provider_name) from exc
        except APIConnectionError as exc:
            raise LLMGenerationError(f"Groq connection error: {exc}", provider=self.provider_name) from exc
        except APIStatusError as exc:
            raise LLMGenerationError(
                f"Groq API error (status {exc.status_code}): {exc}", provider=self.provider_name
            ) from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMGenerationError("Groq returned an empty response", provider=self.provider_name)

        log.debug("Groq generated {} chars", len(content))
        return content

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
