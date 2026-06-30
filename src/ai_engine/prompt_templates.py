"""
Prompt construction for the tactical analyst.

`build_system_prompt()` establishes the persona (elite tactical analyst),
the output contract (strict JSON matching `output_schemas.TacticalAnalysis`),
and ground rules (be specific, tie every recommendation to evidence in the
match state, don't invent players who aren't in the lineup).

`build_user_prompt()` serializes a `MatchState` into a compact, structured
text block — score, minute, momentum breakdown, formations, and a
chronological event log — which is everything the model needs and nothing
it doesn't (keeping token usage low matters on free-tier rate limits).
"""

from __future__ import annotations

from src.core.match_state import MatchState

_JSON_SCHEMA_SPEC = """
Respond with ONLY a single JSON object (no markdown fences, no prose before
or after it) matching exactly this shape:

{
  "fixture_id": <int>,
  "generated_at_minute": <int>,
  "match_summary": "<2-3 sentence summary of the match so far>",
  "momentum_assessment": "<plain-language read of which team has momentum and why>",
  "key_observations": ["<sharp tactical observation>", ...],
  "recommendations": [
    {
      "target_team": "<exact team name from the match data>",
      "category": "<one of: substitution, formation_change, attacking_adjustment, defensive_adjustment, tactical_instruction>",
      "priority": "<one of: low, medium, high, urgent>",
      "description": "<the concrete action to take>",
      "rationale": "<why, tied to specific evidence from the match state>"
    }
  ],
  "confidence": <float between 0.0 and 1.0>
}
""".strip()


def build_system_prompt() -> str:
    """The persona + output-contract prompt, reused identically across requests."""
    return f"""You are an elite football (soccer) tactical analyst and assistant
manager, with the analytical rigor of a top-level data scout and the
in-game instincts of a world-class coach. You are advising the coaching
staff of BOTH teams in a live match, in real time.

Ground rules:
- Base every observation and recommendation strictly on the match data
  provided below. Never invent players, stats, or events not present in it.
- Reference actual player names and team names from the data when relevant.
- Prioritize recommendations that are actionable *right now*, given the
  current minute — a tactical tweak suggested at minute 85 should differ in
  urgency from one at minute 20.
- Consider momentum, formation matchups, numerical/positional imbalances
  (e.g. a team a man down, a mismatched midfield), and recent events
  (goals, cards, substitutions already made).
- Give 2-4 recommendations total, spread across both teams as relevant —
  don't pad with low-value suggestions just to hit a count.
- Priority "urgent" is reserved for genuinely game-changing moments (e.g. a
  red card, a sudden two-goal swing, a team collapsing defensively).

{_JSON_SCHEMA_SPEC}"""


def _format_momentum_section(state: MatchState) -> str:
    m = state.momentum
    dominant = m.dominant_side.value if m.dominant_side else "no clear dominant side"
    return (
        f"MOMENTUM (0-100 index, blends recent events + sustained pressure):\n"
        f"  {m.home.team_name}: {m.home.index} ({m.home.pressure_label})\n"
        f"  {m.away.team_name}: {m.away.index} ({m.away.pressure_label})\n"
        f"  Currently dominant: {dominant} (differential: {m.differential:+.1f})"
    )


def _format_formation_section(state: MatchState) -> str:
    lines = ["FORMATIONS:"]
    for snapshot in (state.home, state.away):
        if snapshot.formation is None:
            lines.append(f"  {snapshot.team_name}: lineup not yet available")
            continue
        f = snapshot.formation
        flag = "" if f.matches_declared else "  [NOTE: declared formation may not match actual shape on pitch]"
        lines.append(f"  {snapshot.team_name}: {f.detected_formation_label}{flag}")
    return "\n".join(lines)


def _format_events_section(state: MatchState) -> str:
    if not state.events:
        return "EVENTS: none recorded yet."
    lines = ["EVENTS (chronological):"]
    for e in state.events:
        assist = f" (assist: {e.assist_name})" if e.assist_name else ""
        lines.append(f"  {e.minute_label} [{e.team_name}] {e.event_type} - {e.event_detail}: {e.player_name}{assist}")
    return "\n".join(lines)


def build_user_prompt(state: MatchState) -> str:
    """Serialize a MatchState into the compact context block sent to the LLM."""
    sections = [
        f"COMPETITION: {state.league_name}",
        f"MATCH: {state.score_label}",
        f"MINUTE: {state.minute}' ({state.status_label})",
        "",
        _format_momentum_section(state),
        "",
        _format_formation_section(state),
        "",
        _format_events_section(state),
    ]
    return "\n".join(sections)
