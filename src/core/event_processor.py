"""
Event normalization.

Raw `MatchEvent` objects from API-Football use API-specific vocabulary
(type="Card", detail="Yellow Card"; type="subst"; etc). This module converts
them into `NormalizedEvent` objects that:
  1. Resolve which side (HOME/AWAY) the event belongs to.
  2. Map the raw (type, detail) pair onto a single `momentum_category` key
     that lines up with `config.constants.MOMENTUM_EVENT_WEIGHTS`.
  3. Are flat and easy for both `momentum_engine` and `ai_engine.prompt_templates`
     to consume without re-parsing API quirks.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from config.constants import MOMENTUM_EVENT_WEIGHTS
from src.data_providers.schemas import MatchEvent, MatchEvents


class MatchSide(str, Enum):
    HOME = "home"
    AWAY = "away"


# Maps raw (event_type, event_detail) -> momentum_category key.
# `None` detail means "match on type alone, ignore detail".
_EVENT_CATEGORY_MAP: dict[tuple[str, str | None], str] = {
    ("Goal", "Normal Goal"): "Goal",
    ("Goal", "Penalty"): "Goal",
    ("Goal", "Own Goal"): "Goal",
    ("Card", "Yellow Card"): "Yellow Card",
    ("Card", "Red Card"): "Red Card",
    ("Card", "Second Yellow card"): "Red Card",
    ("subst", None): "Substitution",
    ("Var", None): "Substitution",  # VAR reviews are momentum-neutral by default; see note below
}


def _resolve_category(event_type: str, event_detail: str) -> str:
    """
    Resolve an event's (type, detail) pair to a momentum category key.

    Falls back to matching on type alone, then to "Dangerous Attack" as a
    safe, low-weight default for any event type we don't explicitly model
    (keeps the momentum engine from crashing on API additions we haven't
    mapped yet, while keeping its impact small).
    """
    if (event_type, event_detail) in _EVENT_CATEGORY_MAP:
        return _EVENT_CATEGORY_MAP[(event_type, event_detail)]
    if (event_type, None) in _EVENT_CATEGORY_MAP:
        return _EVENT_CATEGORY_MAP[(event_type, None)]
    return "Dangerous Attack"


class NormalizedEvent(BaseModel):
    """A `MatchEvent` enriched with side resolution and a momentum category."""

    minute: int
    minute_label: str
    side: MatchSide
    team_id: int
    team_name: str
    player_name: str | None
    assist_name: str | None
    event_type: str
    event_detail: str
    momentum_category: str
    momentum_weight: float
    comments: str | None = None

    @classmethod
    def from_raw(cls, event: MatchEvent, home_team_id: int) -> "NormalizedEvent":
        category = _resolve_category(event.type, event.detail)
        return cls(
            minute=event.time.elapsed,
            minute_label=event.minute_label,
            side=MatchSide.HOME if event.team.id == home_team_id else MatchSide.AWAY,
            team_id=event.team.id,
            team_name=event.team.name,
            player_name=event.player.name,
            assist_name=event.assist.name if event.assist else None,
            event_type=event.type,
            event_detail=event.detail,
            momentum_category=category,
            momentum_weight=MOMENTUM_EVENT_WEIGHTS.get(category, 0.0),
            comments=event.comments,
        )


def normalize_events(match_events: MatchEvents, home_team_id: int) -> list[NormalizedEvent]:
    """
    Convert a raw `MatchEvents` payload into normalized, momentum-ready events,
    sorted chronologically (API-Football usually already returns them sorted,
    but we don't trust that blindly).
    """
    normalized = [
        NormalizedEvent.from_raw(event, home_team_id=home_team_id)
        for event in match_events.events
    ]
    return sorted(normalized, key=lambda e: e.minute)
