"""
Momentum / pressure index engine.

Combines two signals into a single 0-100 "momentum index" per team:

  1. EVENT MOMENTUM — recent normalized events (goals, cards, etc.), weighted
     by `config.constants.MOMENTUM_EVENT_WEIGHTS` and decayed linearly over
     `MOMENTUM_DECAY_WINDOW_MINUTES` so a goal 2 minutes ago matters far more
     than a yellow card 40 minutes ago.

  2. SNAPSHOT PRESSURE — a baseline derived from current cumulative live
     stats (shots on goal, corners, possession), which reflects sustained
     territorial dominance even between discrete events.

The two are blended into a final index, and the *differential* between both
teams' indices is what `ai_engine.prompt_templates` leans on most heavily to
decide how urgently to recommend a tactical change.
"""

from __future__ import annotations

from pydantic import BaseModel

from config.constants import (
    MOMENTUM_DECAY_WINDOW_MINUTES,
    MOMENTUM_HIGH_PRESSURE_THRESHOLD,
    MOMENTUM_LOW_PRESSURE_THRESHOLD,
)
from src.core.event_processor import MatchSide, NormalizedEvent
from src.data_providers.schemas import LiveStats, TeamStatistics

# Snapshot-pressure stat weights: how much each cumulative stat contributes
# to the baseline pressure score, before normalization.
_STAT_WEIGHTS: dict[str, float] = {
    "Shots on Goal": 4.0,
    "Total Shots": 1.0,
    "Corner Kicks": 2.0,
    "Ball Possession": 0.4,  # multiplied against the numeric percentage
}


class TeamMomentum(BaseModel):
    """Momentum breakdown for a single team."""

    team_id: int
    team_name: str
    side: MatchSide
    event_score: float  # decayed, weighted recent-event contribution
    snapshot_score: float  # stats-based sustained pressure contribution
    index: float  # final blended 0-100 index
    pressure_label: str  # "High Pressure" | "Balanced" | "Low Pressure"


class MomentumResult(BaseModel):
    """Both teams' momentum, plus the differential (home - away)."""

    home: TeamMomentum
    away: TeamMomentum

    @property
    def differential(self) -> float:
        """Positive => home dominating; negative => away dominating."""
        return self.home.index - self.away.index

    @property
    def dominant_side(self) -> MatchSide | None:
        if abs(self.differential) < 5.0:
            return None  # too close to call a clear dominant side
        return MatchSide.HOME if self.differential > 0 else MatchSide.AWAY


def _decay_weight(event_minute: int, current_minute: int, window: int) -> float:
    """
    Linear decay: an event at the current minute has full weight (1.0);
    an event `window` minutes old or older has zero weight.
    """
    age = current_minute - event_minute
    if age <= 0:
        return 1.0
    if age >= window:
        return 0.0
    return 1.0 - (age / window)


def _event_score_for_team(
    events: list[NormalizedEvent],
    team_id: int,
    current_minute: int,
    window: int,
) -> float:
    score = 0.0
    for event in events:
        if event.team_id != team_id:
            continue
        decay = _decay_weight(event.minute, current_minute, window)
        score += event.momentum_weight * decay
    return score


def _snapshot_score_for_team(team_stats: TeamStatistics | None) -> float:
    if team_stats is None:
        return 0.0

    score = 0.0
    for stat_label, weight in _STAT_WEIGHTS.items():
        value = team_stats.get(stat_label)
        if value is None:
            continue
        numeric = _coerce_numeric(value)
        score += numeric * weight
    return score


def _coerce_numeric(value: int | float | str) -> float:
    """API-Football returns possession as a string like '53%'; normalize to a float."""
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = value.strip().rstrip("%")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _label_for_index(index: float) -> str:
    if index >= MOMENTUM_HIGH_PRESSURE_THRESHOLD:
        return "High Pressure"
    if index <= MOMENTUM_LOW_PRESSURE_THRESHOLD:
        return "Low Pressure"
    return "Balanced"


def _normalize_to_100(home_raw: float, away_raw: float) -> tuple[float, float]:
    """
    Rescale two raw, unbounded scores onto a shared 0-100 scale so the higher
    of the two never exceeds 100, while preserving their relative gap.
    A floor of 50/50 is used when both raw scores are ~0 (kickoff state).
    """
    total = home_raw + away_raw
    if total <= 1e-9:
        return 50.0, 50.0
    home_index = round((home_raw / total) * 100, 1)
    away_index = round((away_raw / total) * 100, 1)
    return home_index, away_index


def compute_momentum(
    events: list[NormalizedEvent],
    live_stats: LiveStats,
    home_team_id: int,
    away_team_id: int,
    home_team_name: str,
    away_team_name: str,
    current_minute: int,
    decay_window_minutes: int = MOMENTUM_DECAY_WINDOW_MINUTES,
) -> MomentumResult:
    """
    Compute the full momentum breakdown for both teams at `current_minute`.

    Pure function: no I/O, fully deterministic given its inputs — easy to
    unit test against a fixed event list and a fixed minute.
    """
    home_event_score = _event_score_for_team(events, home_team_id, current_minute, decay_window_minutes)
    away_event_score = _event_score_for_team(events, away_team_id, current_minute, decay_window_minutes)

    home_snapshot_score = _snapshot_score_for_team(live_stats.for_team(home_team_id))
    away_snapshot_score = _snapshot_score_for_team(live_stats.for_team(away_team_id))

    # Blend: events matter more in the short term, snapshot stats provide
    # the sustained baseline. Raw (unbounded) combined scores...
    home_raw = home_event_score + home_snapshot_score
    away_raw = away_event_score + away_snapshot_score

    home_index, away_index = _normalize_to_100(home_raw, away_raw)

    home_momentum = TeamMomentum(
        team_id=home_team_id,
        team_name=home_team_name,
        side=MatchSide.HOME,
        event_score=round(home_event_score, 2),
        snapshot_score=round(home_snapshot_score, 2),
        index=home_index,
        pressure_label=_label_for_index(home_index),
    )
    away_momentum = TeamMomentum(
        team_id=away_team_id,
        team_name=away_team_name,
        side=MatchSide.AWAY,
        event_score=round(away_event_score, 2),
        snapshot_score=round(away_snapshot_score, 2),
        index=away_index,
        pressure_label=_label_for_index(away_index),
    )

    return MomentumResult(home=home_momentum, away=away_momentum)
