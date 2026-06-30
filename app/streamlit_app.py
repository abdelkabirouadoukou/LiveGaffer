"""
Live Soccer Assistant Manager & AI Analyst — Streamlit dashboard.

Run from the project root:

    streamlit run app/streamlit_app.py

Polls (or, on demand, re-fetches) live match data through
`AnalysisService` and renders:
  - the live score / status header
  - a momentum/pressure comparison
  - formation analysis for both teams (declared vs detected)
  - a recent-events timeline
  - the AI tactical analyst's recommendations panel

Defaults to `DATA_SOURCE_MODE=mock` (see `.env.example`), so the whole
dashboard works end-to-end with zero API keys and zero network calls —
flip to `live` once real RapidAPI / Groq / Gemini keys are configured.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Make the project root importable regardless of the working directory
# `streamlit run` was invoked from (Streamlit only auto-adds the script's
# own directory to sys.path, not the project root).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st  # noqa: E402

from config.settings import DataSourceMode, get_settings  # noqa: E402
from src.ai_engine.exceptions import (  # noqa: E402
    AllProvidersExhaustedError,
    LLMOutputParsingError,
)
from src.ai_engine.output_schemas import RecommendationPriority, TacticalAnalysis  # noqa: E402
from src.core.match_state import MatchState  # noqa: E402
from src.data_providers.exceptions import DataProviderError, FixtureNotFoundError  # noqa: E402
from src.services.analysis_service import AnalysisService  # noqa: E402

# Mock-mode default fixture: Real Madrid vs Barcelona (data/mocks/mock_live_fixture.json)
_DEFAULT_MOCK_FIXTURE_ID = 1035001

_PRIORITY_BADGE = {
    RecommendationPriority.URGENT: "🔴 URGENT",
    RecommendationPriority.HIGH: "🟠 HIGH",
    RecommendationPriority.MEDIUM: "🟡 MEDIUM",
    RecommendationPriority.LOW: "🟢 LOW",
}


# ---------------------------------------------------------------------------
# Async bridge
# ---------------------------------------------------------------------------
def run_async(coro):
    """
    Run an async coroutine to completion from Streamlit's sync script model.

    Deliberately uses a fresh event loop per call (via `asyncio.run`)
    rather than holding a persistent service/event-loop pair across
    reruns: Streamlit reruns the whole script top-to-bottom on every
    interaction, and a cached async HTTP client created in one event loop
    cannot safely be reused from another. Building/closing a fresh
    `AnalysisService` per call is cheap (no real connections are opened
    until first used) and keeps this correct under Streamlit's model.
    """
    return asyncio.run(coro)


async def _fetch_match_state(fixture_id: int) -> MatchState:
    async with AnalysisService() as service:
        return await service.get_match_state(fixture_id)


async def _fetch_tactical_analysis(fixture_id: int, force_refresh: bool) -> TacticalAnalysis:
    async with AnalysisService() as service:
        return await service.get_tactical_analysis(fixture_id, force_refresh=force_refresh)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def render_sidebar() -> tuple[int, bool, int]:
    settings = get_settings()

    st.sidebar.title("⚽ Match Controls")

    mode_badge = "🟢 MOCK (offline, free)" if settings.data_source_mode is DataSourceMode.MOCK else "🔴 LIVE (real API calls)"
    st.sidebar.markdown(f"**Data source:** {mode_badge}")
    st.sidebar.caption(
        "Switch via `DATA_SOURCE_MODE` in `.env`. Mock mode never calls "
        "RapidAPI/Groq/Gemini — safe to leave on by default."
    )

    fixture_id = st.sidebar.number_input(
        "Fixture ID",
        min_value=1,
        value=_DEFAULT_MOCK_FIXTURE_ID,
        step=1,
        help="In mock mode, only the bundled Real Madrid vs Barcelona "
        f"fixture ({_DEFAULT_MOCK_FIXTURE_ID}) resolves.",
    )

    st.sidebar.divider()

    auto_refresh = st.sidebar.checkbox("Auto-refresh", value=False)
    poll_interval = st.sidebar.slider(
        "Poll interval (seconds)",
        min_value=5,
        max_value=600,
        value=settings.poll_interval_seconds,
        step=5,
        disabled=not auto_refresh,
    )

    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh now", use_container_width=True):
        st.session_state["force_refresh"] = True

    return int(fixture_id), auto_refresh, poll_interval


def render_header(state: MatchState) -> None:
    st.title("⚽ Live Soccer Assistant Manager & AI Analyst")
    st.caption(f"{state.league_name} · {state.status_label}")

    col1, col2, col3 = st.columns([3, 1, 3])
    with col1:
        st.metric(state.home.team_name, state.home.score)
    with col2:
        st.metric("Minute", f"{state.minute}'")
    with col3:
        st.metric(state.away.team_name, state.away.score)


def render_momentum(state: MatchState) -> None:
    st.subheader("📊 Momentum")
    momentum = state.momentum

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**{momentum.home.team_name}** — {momentum.home.pressure_label}")
        st.progress(min(max(momentum.home.index / 100, 0.0), 1.0), text=f"{momentum.home.index:.1f} / 100")
    with col2:
        st.write(f"**{momentum.away.team_name}** — {momentum.away.pressure_label}")
        st.progress(min(max(momentum.away.index / 100, 0.0), 1.0), text=f"{momentum.away.index:.1f} / 100")

    dominant = momentum.dominant_side
    if dominant is not None:
        leader_name = momentum.home.team_name if dominant.value == "home" else momentum.away.team_name
        st.info(f"**{leader_name}** currently has the upper hand (momentum differential: {momentum.differential:+.1f}).")
    else:
        st.caption("Momentum is too close to call right now.")


def render_formations(state: MatchState) -> None:
    st.subheader("🧩 Formations")
    col1, col2 = st.columns(2)

    for col, snapshot in ((col1, state.home), (col2, state.away)):
        with col:
            st.write(f"**{snapshot.team_name}**")
            formation = snapshot.formation
            if formation is None:
                st.caption("No lineup data available yet.")
                continue
            st.write(f"Declared: `{formation.declared_formation or 'unknown'}`")
            st.write(f"Detected: `{formation.detected_formation_label}`")
            if formation.matches_declared:
                st.caption("✅ Detected shape matches the declared formation.")
            else:
                st.caption("⚠️ Detected shape differs from the declared formation.")
            st.caption(
                f"GK {formation.goalkeepers} · DEF {formation.defenders} · "
                f"MID {formation.midfielders} · FWD {formation.forwards}"
            )


def render_events(state: MatchState, lookback_minutes: int = 20) -> None:
    st.subheader("📋 Recent Events")
    recent = state.recent_events(lookback_minutes=lookback_minutes)
    if not recent:
        st.caption(f"No events in the last {lookback_minutes} minutes.")
        return

    for event in reversed(recent):
        side_icon = "🏠" if event.side.value == "home" else "✈️"
        player = event.player_name or "Unknown player"
        st.write(f"`{event.minute_label}` {side_icon} **{event.team_name}** — {event.event_detail} ({player})")


def render_ai_panel(fixture_id: int, force_refresh: bool) -> None:
    st.subheader("🧠 AI Tactical Analysis")

    settings = get_settings()
    if not settings.groq_api_key and not settings.gemini_api_key and settings.data_source_mode is DataSourceMode.LIVE:
        st.warning("No GROQ_API_KEY or GEMINI_API_KEY configured — AI analysis will fail in live mode.")

    with st.spinner("Consulting the tactical analyst..."):
        try:
            analysis = run_async(_fetch_tactical_analysis(fixture_id, force_refresh))
        except FixtureNotFoundError as exc:
            st.error(f"Fixture not found: {exc}")
            return
        except DataProviderError as exc:
            st.error(f"Could not load match data: {exc}")
            return
        except AllProvidersExhaustedError as exc:
            st.error(f"Both AI providers failed: {exc}")
            return
        except LLMOutputParsingError as exc:
            st.error(f"AI response could not be parsed: {exc}")
            return
        except RuntimeError as exc:
            # `Settings.require_groq_key()` / a missing-fallback-key guard
            # raises a plain RuntimeError, not an `AIEngineError` subclass —
            # caught separately so a missing-key setup mistake reads as
            # actionable guidance instead of an unhandled-exception crash.
            st.error(f"AI engine is not configured: {exc}")
            return

    st.caption(f"Generated by **{analysis.provider_used}** · confidence {analysis.confidence:.0%}")
    st.write(analysis.match_summary)

    st.markdown(f"**Momentum read:** {analysis.momentum_assessment}")

    if analysis.key_observations:
        st.markdown("**Key observations**")
        for observation in analysis.key_observations:
            st.markdown(f"- {observation}")

    if analysis.recommendations:
        st.markdown("**Recommendations**")
        for rec in analysis.recommendations:
            badge = _PRIORITY_BADGE.get(rec.priority, rec.priority.value.upper())
            with st.expander(f"{badge} · {rec.target_team} · {rec.category.value.replace('_', ' ').title()}"):
                st.write(f"**Action:** {rec.description}")
                st.write(f"**Why:** {rec.rationale}")
    else:
        st.caption("No specific recommendations at this time.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Live Soccer AI Manager", page_icon="⚽", layout="wide")

    fixture_id, auto_refresh, poll_interval = render_sidebar()
    force_refresh = st.session_state.pop("force_refresh", False)

    try:
        with st.spinner("Loading match state..."):
            state = run_async(_fetch_match_state(fixture_id))
    except FixtureNotFoundError as exc:
        st.error(f"Fixture not found: {exc}")
        st.info(f"In mock mode, try fixture ID **{_DEFAULT_MOCK_FIXTURE_ID}**.")
        return
    except DataProviderError as exc:
        st.error(f"Could not load match data: {exc}")
        return

    render_header(state)
    st.divider()

    col_left, col_right = st.columns([3, 2])
    with col_left:
        render_momentum(state)
        st.divider()
        render_formations(state)
        st.divider()
        render_events(state)
    with col_right:
        render_ai_panel(fixture_id, force_refresh)

    st.caption(f"Last updated: {time.strftime('%H:%M:%S')}")

    if auto_refresh:
        time.sleep(poll_interval)
        st.rerun()


if __name__ == "__main__":
    main()