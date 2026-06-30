"""
Abstract data provider interface.

Both `api_football_client.py` (live) and a future/implicit mock provider
implement this interface, so `services/live_match_service.py` can depend on
`MatchDataProvider` without caring which concrete implementation is wired in.
This is the Dependency Inversion piece that lets us develop against
`data/mocks/*.json` all day without burning RapidAPI or API-Football free-tier quota, then
flip `DATA_SOURCE_MODE=live` in `.env` with zero code changes downstream.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.data_providers.schemas import Fixture, Lineups, LiveStats, MatchEvents


class MatchDataProvider(ABC):
    """Contract every match-data source (live API or mock) must fulfil."""

    @abstractmethod
    async def get_live_fixtures(self, league_id: int | None = None) -> list[Fixture]:
        """Return all currently in-play fixtures, optionally filtered by league."""
        raise NotImplementedError

    @abstractmethod
    async def get_fixture(self, fixture_id: int) -> Fixture:
        """Return a single fixture by ID. Raises FixtureNotFoundError if missing."""
        raise NotImplementedError

    @abstractmethod
    async def get_live_stats(self, fixture_id: int) -> LiveStats:
        """Return both teams' live statistics for a fixture."""
        raise NotImplementedError

    @abstractmethod
    async def get_lineups(self, fixture_id: int) -> Lineups:
        """Return both teams' starting lineups and formations for a fixture."""
        raise NotImplementedError

    @abstractmethod
    async def get_events(self, fixture_id: int) -> MatchEvents:
        """Return the chronological event timeline (goals, cards, subs) for a fixture."""
        raise NotImplementedError

    async def close(self) -> None:
        """Release any underlying resources (HTTP clients, file handles). Optional override."""
        return None

    async def __aenter__(self) -> "MatchDataProvider":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()
