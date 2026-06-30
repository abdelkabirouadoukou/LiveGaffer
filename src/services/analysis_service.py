"""
Analysis service.

Wires `LiveMatchService` (data + core, see `live_match_service.py`) to the
AI tactical engine (`TacticalAnalyst`, Phase 4), with its own — deliberately
longer — TTL cache layer so repeated UI polls within the same window don't
re-spend Groq/Gemini free-tier quota generating near-identical analysis a
few seconds apart.

This is the single entry point the presentation layer (Streamlit app and
FastAPI routers) is expected to depend on.
"""

from __future__ import annotations

from config.settings import Settings, get_settings
from src.ai_engine.output_schemas import TacticalAnalysis
from src.ai_engine.tactical_analyst import TacticalAnalyst
from src.core.match_state import MatchState
from src.data_providers.schemas import Fixture
from src.services.cache_service import TTLCache
from src.services.live_match_service import LiveMatchService
from src.utils.logger import get_logger

log = get_logger(__name__)

# AI analysis costs real LLM-provider quota, unlike a raw data fetch, so it
# is cached for longer than the underlying match-state fetch by default.
_ANALYSIS_CACHE_TTL_MULTIPLIER = 2.0


class AnalysisService:
    """High-level use-case API: 'live tactical analysis for fixture X'."""

    def __init__(
        self,
        match_service: LiveMatchService | None = None,
        analyst: TacticalAnalyst | None = None,
        settings: Settings | None = None,
        cache: TTLCache | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._match_service = match_service or LiveMatchService(settings=self._settings)
        self._analyst = analyst or TacticalAnalyst()
        self._cache = cache or TTLCache(
            default_ttl_seconds=self._settings.cache_ttl_seconds * _ANALYSIS_CACHE_TTL_MULTIPLIER
        )

    # ------------------------------------------------------------------
    # Pass-through match-data use cases (UI shouldn't need to import
    # LiveMatchService directly — this keeps one dependency surface).
    # ------------------------------------------------------------------
    async def list_live_fixtures(self, league_id: int | None = None) -> list[Fixture]:
        return await self._match_service.list_live_fixtures(league_id=league_id)

    async def get_match_state(self, fixture_id: int) -> MatchState:
        return await self._match_service.get_match_state(fixture_id)

    # ------------------------------------------------------------------
    # AI tactical analysis
    # ------------------------------------------------------------------
    async def get_tactical_analysis(
        self, fixture_id: int, force_refresh: bool = False
    ) -> TacticalAnalysis:
        """
        Return cached AI tactical analysis for `fixture_id`, generating a
        fresh one (via `TacticalAnalyst.analyze`) on a cache miss or when
        `force_refresh=True`.
        """
        cache_key = f"tactical_analysis:{fixture_id}"

        if force_refresh:
            await self._cache.invalidate(cache_key)

        async def _generate() -> TacticalAnalysis:
            match_state = await self._match_service.get_match_state(fixture_id)
            log.info(
                "Generating tactical analysis for fixture {} (minute {})",
                fixture_id,
                match_state.minute,
            )
            return await self._analyst.analyze(match_state)

        return await self._cache.get_or_set(cache_key, _generate)

    async def close(self) -> None:
        await self._match_service.close()
        await self._analyst.close()

    async def __aenter__(self) -> AnalysisService:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()