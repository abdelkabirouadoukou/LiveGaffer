"""
Exceptions for the AI tactical engine.

Mirrors the style of `data_providers.exceptions`: precise exception types
let `tactical_analyst.py` distinguish "primary provider down, try fallback"
from "both providers failed, give up" from "got a response but couldn't
parse it into our schema".
"""

from __future__ import annotations


class AIEngineError(Exception):
    """Base class for all AI-engine-related errors."""


class LLMGenerationError(AIEngineError):
    """Raised when an LLM provider's API call fails (network, auth, quota)."""

    def __init__(self, message: str, provider: str) -> None:
        super().__init__(message)
        self.provider = provider


class LLMOutputParsingError(AIEngineError):
    """Raised when an LLM response cannot be parsed into TacticalAnalysis."""

    def __init__(self, message: str, raw_output: str) -> None:
        super().__init__(message)
        self.raw_output = raw_output


class AllProvidersExhaustedError(AIEngineError):
    """Raised when both the primary and fallback LLM providers have failed."""
