"""
Static domain constants shared across the app.

Keeping these separate from `settings.py` matters: `settings.py` holds
*environment-dependent* config (secrets, modes), while this module holds
*domain knowledge* that doesn't change between environments (a 4-3-3 is a
4-3-3 whether you're in dev or prod).
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# API-Football: well-known league IDs (free-tier accessible).
# Full reference: https://www.api-football.com/documentation-v3#tag/Leagues
# ---------------------------------------------------------------------------
LEAGUE_IDS: Final[dict[str, int]] = {
    "premier_league": 39,
    "la_liga": 140,
    "serie_a": 135,
    "bundesliga": 78,
    "ligue_1": 61,
    "champions_league": 2,
    "europa_league": 3,
    "botola_pro": 200,  # Morocco Botola Pro 1
    "world_cup": 1,
}

# Current season helper (API-Football expects the starting year of the season,
# e.g. the 2025/26 season is requested as `2025`). Override per-request if needed.
DEFAULT_SEASON: Final[int] = 2025

# ---------------------------------------------------------------------------
# Formation shapes: canonical name -> (defenders, midfielders, forwards)
# Used by core.formation_analyzer to map detected player-position clusters
# back to a human-readable formation label.
# ---------------------------------------------------------------------------
FORMATION_SHAPES: Final[dict[str, tuple[int, int, int]]] = {
    "4-4-2": (4, 4, 2),
    "4-3-3": (4, 3, 3),
    "4-2-3-1": (4, 5, 1),  # the 2-3 midfield band collapses to 5 in a flat count
    "4-1-4-1": (4, 5, 1),
    "3-5-2": (3, 5, 2),
    "3-4-3": (3, 4, 3),
    "5-3-2": (5, 3, 2),
    "5-4-1": (5, 4, 1),
    "4-5-1": (4, 5, 1),
}

# ---------------------------------------------------------------------------
# Momentum engine tuning: event weights used to compute a rolling
# "pressure index" per team (see core.momentum_engine).
# Positive = attacking pressure, scaled arbitrarily on a 0–100 display scale.
# ---------------------------------------------------------------------------
MOMENTUM_EVENT_WEIGHTS: Final[dict[str, float]] = {
    "Goal": 25.0,
    "Shot on Goal": 6.0,
    "Shot off Goal": 2.5,
    "Blocked Shot": 3.0,
    "Big Chance Missed": 8.0,
    "Corner": 3.5,
    "Dangerous Attack": 1.5,
    "Yellow Card": -2.0,
    "Red Card": -15.0,
    "Substitution": 0.0,
    "Penalty Won": 12.0,
    "Penalty Missed": -10.0,
    "Offside": -1.0,
}

# Rolling window (minutes) used by the momentum engine to decay old events
MOMENTUM_DECAY_WINDOW_MINUTES: Final[int] = 10

# Momentum index thresholds used to drive AI prompt urgency
MOMENTUM_HIGH_PRESSURE_THRESHOLD: Final[float] = 65.0
MOMENTUM_LOW_PRESSURE_THRESHOLD: Final[float] = 20.0

# ---------------------------------------------------------------------------
# Match status codes returned by API-Football (`fixture.status.short`)
# ---------------------------------------------------------------------------
LIVE_MATCH_STATUSES: Final[set[str]] = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE"}
FINISHED_MATCH_STATUSES: Final[set[str]] = {"FT", "AET", "PEN"}
NOT_STARTED_STATUSES: Final[set[str]] = {"NS", "TBD"}

# ---------------------------------------------------------------------------
# HTTP / rate-limit tuning for the free RapidAPI or API-Football tier
# (API-Football free plan: 100 requests/day, ~10 req/min burst limit)
# ---------------------------------------------------------------------------
API_FOOTBALL_MAX_REQUESTS_PER_MINUTE: Final[int] = 8  # stay safely under 10/min
API_FOOTBALL_REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0
API_FOOTBALL_MAX_RETRIES: Final[int] = 3
