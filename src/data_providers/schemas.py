"""
Typed schemas for raw match data.

These models intentionally mirror API-Football's v3 JSON shape (using
`alias` so we can parse their payloads directly with `model_validate`),
while exposing clean, snake_case, well-typed Python attributes to the rest
of the app. The mock JSON files in `data/mocks/` follow this exact shape,
so the same schemas validate both mock and live data — the rest of the
codebase never needs to know which one it's looking at.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _APIModel(BaseModel):
    """Base model: allows population by field name OR API alias, ignores extras."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


# ---------------------------------------------------------------------------
# Fixture status / metadata
# ---------------------------------------------------------------------------
class MatchStatus(_APIModel):
    long: str
    short: str
    elapsed: int | None = None


class TeamRef(_APIModel):
    """Lightweight reference to a team (used in fixtures, events, lineups)."""

    id: int
    name: str
    logo: str | None = None
    winner: bool | None = None


class League(_APIModel):
    id: int
    name: str
    country: str
    season: int
    round: str | None = None


class Goals(_APIModel):
    home: int | None = None
    away: int | None = None

class Venue(_APIModel):
    id: int | None = None
    name: str | None = None
    city: str | None = None


class FixtureInfo(_APIModel):
    id: int
    referee: str | None = None
    timezone: str = "UTC"
    date: datetime
    venue: Venue | None = None
    status: MatchStatus

    @property
    def venue_name(self) -> str | None:
        """Kept for backward compatibility with any existing `.venue_name` call sites."""
        return self.venue.name if self.venue else None

class FixtureTeams(_APIModel):
    home: TeamRef
    away: TeamRef


class Fixture(_APIModel):
    """A single match: teams, score, status, competition context."""

    fixture: FixtureInfo
    league: League
    teams: FixtureTeams
    goals: Goals

    @property
    def fixture_id(self) -> int:
        return self.fixture.id

    @property
    def is_live(self) -> bool:
        from config.constants import LIVE_MATCH_STATUSES

        return self.fixture.status.short in LIVE_MATCH_STATUSES

    @property
    def is_finished(self) -> bool:
        from config.constants import FINISHED_MATCH_STATUSES

        return self.fixture.status.short in FINISHED_MATCH_STATUSES

    @property
    def minute(self) -> int:
        return self.fixture.status.elapsed or 0


# ---------------------------------------------------------------------------
# Live statistics
# ---------------------------------------------------------------------------
class StatItem(_APIModel):
    type: str
    value: int | float | str | None = None


class TeamStatistics(_APIModel):
    team: TeamRef
    statistics: list[StatItem] = Field(default_factory=list)

    def get(self, stat_type: str) -> int | float | str | None:
        """Look up a single stat by its API-Football label, e.g. 'Ball Possession'."""
        for item in self.statistics:
            if item.type == stat_type:
                return item.value
        return None


class LiveStats(_APIModel):
    """Both teams' statistics for a single fixture."""

    fixture_id: int
    teams_statistics: list[TeamStatistics] = Field(default_factory=list)

    def for_team(self, team_id: int) -> TeamStatistics | None:
        for team_stats in self.teams_statistics:
            if team_stats.team.id == team_id:
                return team_stats
        return None


# ---------------------------------------------------------------------------
# Lineups & formations
# ---------------------------------------------------------------------------
class PlayerGridPosition(_APIModel):
    """Raw 'x:y' grid string from API-Football, parsed into (row, col)."""

    raw: str

    @property
    def row(self) -> int:
        return int(self.raw.split(":")[0])

    @property
    def col(self) -> int:
        return int(self.raw.split(":")[1])


class LineupPlayer(_APIModel):
    id: int
    name: str
    number: int | None = None
    position: str | None = None  # G, D, M, F
    grid: str | None = None

    @property
    def grid_position(self) -> PlayerGridPosition | None:
        return PlayerGridPosition(raw=self.grid) if self.grid else None


class LineupPlayerEntry(_APIModel):
    player: LineupPlayer


class TeamLineup(_APIModel):
    team: TeamRef
    formation: str | None = None
    start_xi: list[LineupPlayerEntry] = Field(default_factory=list, alias="startXI")
    substitutes: list[LineupPlayerEntry] = Field(default_factory=list)
    coach: dict | None = None


class Lineups(_APIModel):
    """Both teams' lineups for a fixture."""

    fixture_id: int
    home: TeamLineup
    away: TeamLineup


# ---------------------------------------------------------------------------
# Match events (goals, cards, subs, VAR)
# ---------------------------------------------------------------------------
class EventType(str, Enum):
    GOAL = "Goal"
    CARD = "Card"
    SUBSTITUTION = "subst"
    VAR = "Var"


class EventTime(_APIModel):
    elapsed: int
    extra: int | None = None


class EventPlayerRef(_APIModel):
    id: int | None = None
    name: str | None = None


class MatchEvent(_APIModel):
    time: EventTime
    team: TeamRef
    player: EventPlayerRef
    assist: EventPlayerRef | None = None
    type: str
    detail: str
    comments: str | None = None

    @property
    def minute_label(self) -> str:
        if self.time.extra:
            return f"{self.time.elapsed}+{self.time.extra}'"
        return f"{self.time.elapsed}'"


class MatchEvents(_APIModel):
    """Chronological list of events for a fixture."""

    fixture_id: int
    events: list[MatchEvent] = Field(default_factory=list)

    def since_minute(self, minute: int) -> list[MatchEvent]:
        return [e for e in self.events if e.time.elapsed >= minute]

    def for_team(self, team_id: int) -> list[MatchEvent]:
        return [e for e in self.events if e.team.id == team_id]
