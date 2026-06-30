"""
Live match state.

This is the single object the AI tactical engine (Phase 4) and the
Streamlit/FastAPI presentation layer (Phase 5) consume. It's built once per
poll cycle by `build_match_state()`, which takes the four raw schema objects
already fetched from `data_providers` and runs them through the
`event_processor`, `momentum_engine`, and `formation_analyzer` to produce a
fully-derived, ready-to-render/ready-to-prompt snapshot.

Deliberately pure: `build_match_state` does no I/O itself. The `services`
layer (Phase 5) is responsible for calling the data provider and feeding
its output in here — that's what keeps this module trivially unit-testable.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.core.event_processor import NormalizedEvent, normalize_events
from src.core.formation_analyzer import FormationAnalysis, analyze_formation
from src.core.momentum_engine import MomentumResult, compute_momentum
from src.data_providers.schemas import Fixture, Lineups, LiveStats, MatchEvents


class TeamSnapshot(BaseModel):
    """Everything we currently know about one team, mid-match."""

    team_id: int
    team_name: str
    score: int
    formation: FormationAnalysis | None


class MatchState(BaseModel):
    """
    A fully-derived, point-in-time snapshot of a live match.

    Holds raw context (fixture, league, minute) plus everything computed by
    the core engines: normalized events, momentum, and formation analysis
    for both teams.
    """

    fixture_id: int
    league_name: str
    minute: int
    status_label: str
    is_live: bool

    home: TeamSnapshot
    away: TeamSnapshot

    events: list[NormalizedEvent]
    momentum: MomentumResult

    @property
    def score_label(self) -> str:
        return f"{self.home.team_name} {self.home.score} - {self.away.score} {self.away.team_name}"

    def recent_events(self, lookback_minutes: int = 15) -> list[NormalizedEvent]:
        cutoff = max(0, self.minute - lookback_minutes)
        return [e for e in self.events if e.minute >= cutoff]

    def last_n_events(self, n: int = 5) -> list[NormalizedEvent]:
        return self.events[-n:]


def build_match_state(
    fixture: Fixture,
    live_stats: LiveStats,
    lineups: Lineups,
    match_events: MatchEvents,
) -> MatchState:
    """
    Pure aggregation: combine four raw data-provider objects into one
    derived `MatchState`, running event normalization, momentum computation,
    and formation analysis along the way.
    """
    home_team_id = fixture.teams.home.id
    away_team_id = fixture.teams.away.id

    normalized_events = normalize_events(match_events, home_team_id=home_team_id)

    momentum = compute_momentum(
        events=normalized_events,
        live_stats=live_stats,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_team_name=fixture.teams.home.name,
        away_team_name=fixture.teams.away.name,
        current_minute=fixture.minute,
    )

    home_formation = analyze_formation(lineups.home) if lineups.home.start_xi else None
    away_formation = analyze_formation(lineups.away) if lineups.away.start_xi else None

    home_snapshot = TeamSnapshot(
        team_id=home_team_id,
        team_name=fixture.teams.home.name,
        score=fixture.goals.home or 0,
        formation=home_formation,
    )
    away_snapshot = TeamSnapshot(
        team_id=away_team_id,
        team_name=fixture.teams.away.name,
        score=fixture.goals.away or 0,
        formation=away_formation,
    )

    return MatchState(
        fixture_id=fixture.fixture_id,
        league_name=fixture.league.name,
        minute=fixture.minute,
        status_label=fixture.fixture.status.long,
        is_live=fixture.is_live,
        home=home_snapshot,
        away=away_snapshot,
        events=normalized_events,
        momentum=momentum,
    )
