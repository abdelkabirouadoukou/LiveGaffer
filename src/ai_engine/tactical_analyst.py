"""
Tactical analyst orchestrator.

This is the single entry point the `services` layer (Phase 5) calls:

    analyst = TacticalAnalyst()
    analysis = await analyst.analyze(match_state)

Internally it:
  1. Builds the system + user prompts from the MatchState (`prompt_templates`).
  2. Calls the primary LLM client (Groq); on failure, falls back to Gemini.
  3. Strips any stray markdown fences and parses the response into the
     strict `TacticalAnalysis` schema.
  4. Raises `AllProvidersExhaustedError` only if BOTH providers fail.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from src.ai_engine.base_llm_client import LLMClient
from src.ai_engine.exceptions import (
    AllProvidersExhaustedError,
    LLMGenerationError,
    LLMOutputParsingError,
)
from src.ai_engine.gemini_client import GeminiClient
from src.ai_engine.groq_client import GroqClient
from src.ai_engine.output_schemas import TacticalAnalysis
from src.ai_engine.prompt_templates import build_system_prompt, build_user_prompt
from src.core.match_state import MatchState
from src.utils.logger import get_logger

log = get_logger(__name__)


def _strip_markdown_fences(raw: str) -> str:
    """
    Defensive cleanup: some models wrap JSON in ```json ... ``` even when
    explicitly told not to. Strip it before parsing rather than failing.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class TacticalAnalyst:
    """
    High-level orchestrator combining prompt construction, primary/fallback
    LLM invocation, and structured-output validation into one call.
    """

    def __init__(
        self,
        primary_client: LLMClient | None = None,
        fallback_client: LLMClient | None = None,
    ) -> None:
        self._primary = primary_client or GroqClient()
        self._fallback = fallback_client or GeminiClient()

    async def analyze(self, match_state: MatchState) -> TacticalAnalysis:
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(match_state)

        raw_output, provider_used = await self._generate_with_fallback(system_prompt, user_prompt)
        return self._parse_output(raw_output, match_state, provider_used)

    async def _generate_with_fallback(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        try:
            log.info("Requesting tactical analysis from primary provider: {}", self._primary.provider_name)
            raw = await self._primary.generate_json(system_prompt, user_prompt)
            return raw, self._primary.provider_name
        except LLMGenerationError as primary_error:
            log.warning(
                "Primary provider '{}' failed: {}. Falling back to '{}'.",
                self._primary.provider_name,
                primary_error,
                self._fallback.provider_name,
            )
            try:
                raw = await self._fallback.generate_json(system_prompt, user_prompt)
                return raw, self._fallback.provider_name
            except LLMGenerationError as fallback_error:
                raise AllProvidersExhaustedError(
                    f"Both providers failed. Primary ({self._primary.provider_name}): "
                    f"{primary_error} | Fallback ({self._fallback.provider_name}): {fallback_error}"
                ) from fallback_error

    @staticmethod
    def _parse_output(raw_output: str, match_state: MatchState, provider_used: str) -> TacticalAnalysis:
        cleaned = _strip_markdown_fences(raw_output)

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMOutputParsingError(
                f"LLM response was not valid JSON: {exc}", raw_output=raw_output
            ) from exc

        # The model may omit context fields we already know deterministically;
        # backfill them rather than relying on the LLM to echo them correctly.
        payload.setdefault("fixture_id", match_state.fixture_id)
        payload.setdefault("generated_at_minute", match_state.minute)
        payload["provider_used"] = provider_used

        try:
            return TacticalAnalysis.model_validate(payload)
        except ValidationError as exc:
            raise LLMOutputParsingError(
                f"LLM response did not match TacticalAnalysis schema: {exc}", raw_output=raw_output
            ) from exc

    async def close(self) -> None:
        await self._primary.close()
        await self._fallback.close()

    async def __aenter__(self) -> "TacticalAnalyst":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()
