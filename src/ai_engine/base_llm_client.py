"""
Abstract LLM client interface.

Both `groq_client.py` and `gemini_client.py` implement this, so
`tactical_analyst.py` can treat "primary provider" and "fallback provider"
identically — same Dependency Inversion pattern as `MatchDataProvider` in
the data layer (Phase 2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Contract every LLM provider client must fulfil."""

    #: Short identifier used in logs and in TacticalAnalysis.provider_used
    provider_name: str

    @abstractmethod
    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a system+user prompt to the LLM and return its raw text response.

        The response is expected to be a JSON object (we instruct the model
        to return JSON only), but this method does not parse it — that's
        `tactical_analyst.py`'s job, so parsing/validation errors are
        handled uniformly regardless of which provider produced the text.

        Raises:
            ai_engine.exceptions.LLMGenerationError: on any provider-side failure
            (auth, network, timeout, quota).
        """
        raise NotImplementedError

    async def close(self) -> None:
        """Release any underlying resources. Optional override."""
        return None

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()
