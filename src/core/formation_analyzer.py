"""
Formation analysis.

API-Football usually supplies a `formation` string directly (e.g. "4-3-3"),
but we don't take it on faith — broadcasters and data providers occasionally
mislabel a hybrid shape. This module independently derives the formation
from each starting player's `position` (G/D/M/F) and cross-checks it against
the declared string, flagging a mismatch so the AI tactical engine can reason
about *actual* defensive/midfield/attacking lines rather than a label.
"""

from __future__ import annotations

from pydantic import BaseModel

from config.constants import FORMATION_SHAPES
from src.data_providers.schemas import TeamLineup


class FormationAnalysis(BaseModel):
    """Result of analyzing one team's starting XI shape."""

    team_id: int
    team_name: str
    declared_formation: str | None
    detected_shape: tuple[int, int, int]  # (defenders, midfielders, forwards)
    detected_formation_label: str
    matches_declared: bool
    defenders: int
    midfielders: int
    forwards: int
    goalkeepers: int


def _count_outfield_positions(lineup: TeamLineup) -> dict[str, int]:
    """Tally starting XI players by their `position` field (G/D/M/F)."""
    counts = {"G": 0, "D": 0, "M": 0, "F": 0}
    for entry in lineup.start_xi:
        position = (entry.player.position or "").upper()
        if position in counts:
            counts[position] += 1
    return counts


def _closest_formation_label(shape: tuple[int, int, int]) -> str:
    """
    Map a detected (D, M, F) shape onto the closest known label in
    FORMATION_SHAPES. Exact match wins; otherwise we report it as a
    custom/hybrid shape rather than forcing a misleading label.
    """
    for label, known_shape in FORMATION_SHAPES.items():
        if known_shape == shape:
            return label
    d, m, f = shape
    return f"{d}-{m}-{f} (custom/hybrid)"


def analyze_formation(lineup: TeamLineup) -> FormationAnalysis:
    """
    Derive the actual formation shape from a team's starting XI and compare
    it against the API-declared formation string.

    Pure function — no I/O, deterministic given the lineup data.
    """
    counts = _count_outfield_positions(lineup)
    shape = (counts["D"], counts["M"], counts["F"])
    detected_label = _closest_formation_label(shape)

    declared = lineup.formation
    matches = declared is not None and declared.strip() == detected_label

    return FormationAnalysis(
        team_id=lineup.team.id,
        team_name=lineup.team.name,
        declared_formation=declared,
        detected_shape=shape,
        detected_formation_label=detected_label,
        matches_declared=matches,
        defenders=counts["D"],
        midfielders=counts["M"],
        forwards=counts["F"],
        goalkeepers=counts["G"],
    )
