"""
Live match service.

Glues the data-provider layer (Phase 2) to the core domain logic (Phase 3):
fetch the four raw schema objects for a fixture — fixture, live stats,
lineups, events — concurrently, then combine them via
`core.match_state.build_match_state` into one derived `MatchState`
snapshot, with TTL caching so repeated polls (Streamlit reruns, API
clients) don't re-spend API-Football free-tier quota every few seconds.

This is the only place outside `data_providers` itself that talks to a
`MatchDataProvider` directly — everything above this layer (analysis
service, UI, API routers) goes through here instead.
"""

from __future__ import annotations

import asyncio

from config.settings import Settings, get_settings
from src.core.match_state import MatchState, build_match_state
from src.data_providers.api_football_client import APIFootballClient
from src.data_providers.base_provider import MatchDataProvider
from src.data_providers.schemas import Fixture
from src.services.cache_service import TTLCache
from src.utils.logger import get_logger

log = get_logger(__name__)


class LiveMatchService:
    """High-level use-case API: 'live fixtures right now' / 'match state for fixture X'."""

    def __init__(
        self,
        provider: MatchDataProvider | None = None,
        settings: Settings | None = None,
        cache: TTLCache | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._provider = provider or APIFootballClient(self._settings)
        self._cache = cache or TTLCache(default_ttl_seconds=self._settings.cache_ttl_seconds)

    async def list_live_fixtures(self, league_id: int | None = None) -> list[Fixture]:
        """Return all currently in-play fixtures, optionally filtered by league. Cached."""
        cache_key = f"live_fixtures:{league_id if league_id is not None else 'all'}"
        return await self._cache.get_or_set(
            cache_key, lambda: self._provider.get_live_fixtures(league_id=league_id)
        )

    async def get_match_state(self, fixture_id: int) -> MatchState:
        """
        Fetch fixture + live stats + lineups + events concurrently for
        `fixture_id`, then build and return the derived `MatchState`.

        The four underlying calls and the resulting derived state are
        cached as a single unit per fixture, so a UI polling every few
        seconds doesn't trigger four fresh API calls each time — only one
        full refresh per `cache_ttl_seconds` window.
        """
        cache_key = f"match_state:{fixture_id}"

        async def _build() -> MatchState:
            log.info("Building match state for fixture {}", fixture_id)
            fixture, live_stats, lineups, events = await asyncio.gather(
                self._provider.get_fixture(fixture_id),
                self._provider.get_live_stats(fixture_id),
                self._provider.get_lineups(fixture_id),
                self._provider.get_events(fixture_id),
            )
            return build_match_state(fixture, live_stats, lineups, events)

        return await self._cache.get_or_set(cache_key, _build)

    async def invalidate_fixture(self, fixture_id: int) -> None:
        """Force the next `get_match_state` call for this fixture to hit the provider again."""
        await self._cache.invalidate(f"match_state:{fixture_id}")

    async def close(self) -> None:
        await self._provider.close()

    async def __aenter__(self) -> LiveMatchService:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()