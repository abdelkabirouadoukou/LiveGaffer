"""
Structured output schemas for the AI tactical engine.

The LLM is prompted to return JSON matching this exact shape (see
`prompt_templates.build_system_prompt`, which embeds this schema as text).
Validating the response through these models means a malformed or
hallucinated LLM response fails loudly and explicitly (`LLMOutputParsingError`)
rather than silently propagating bad data into the UI.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RecommendationCategory(str, Enum):
    SUBSTITUTION = "substitution"
    FORMATION_CHANGE = "formation_change"
    ATTACKING_ADJUSTMENT = "attacking_adjustment"
    DEFENSIVE_ADJUSTMENT = "defensive_adjustment"
    TACTICAL_INSTRUCTION = "tactical_instruction"


class RecommendationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TacticalRecommendation(BaseModel):
    """A single actionable suggestion for one team's coaching staff."""

    target_team: str = Field(description="Name of the team this recommendation is for")
    category: RecommendationCategory
    priority: RecommendationPriority
    description: str = Field(description="The concrete action to take, in plain language")
    rationale: str = Field(description="Why this is recommended right now, tied to match state")


class TacticalAnalysis(BaseModel):
    """The full structured output of one AI tactical analysis pass."""

    fixture_id: int
    generated_at_minute: int
    match_summary: str = Field(description="2-3 sentence summary of the match so far")
    momentum_assessment: str = Field(
        description="Plain-language read of which team currently has momentum and why"
    )
    key_observations: list[str] = Field(
        default_factory=list, description="3-5 sharp tactical observations"
    )
    recommendations: list[TacticalRecommendation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, description="Model's self-reported confidence")
    provider_used: str = Field(default="unknown", description="Which LLM provider produced this")

    def high_priority_recommendations(self) -> list[TacticalRecommendation]:
        return [
            r
            for r in self.recommendations
            if r.priority in (RecommendationPriority.HIGH, RecommendationPriority.URGENT)
        ]
