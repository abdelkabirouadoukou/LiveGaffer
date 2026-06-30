"""
Concrete `MatchDataProvider` implementation backed by API-Football
(via RapidAPI), with a built-in local-mock mode for development.

Mode is controlled by `settings.data_source_mode`:
  - "live": real HTTP calls to RapidAPI, rate-limited + retried, free-tier safe.
  - "mock": reads static JSON fixtures from `data/mocks/`, zero network calls.

Both modes return the exact same typed Pydantic objects, so nothing
downstream (core/, ai_engine/, services/) needs to know which mode is active.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.constants import (
    API_FOOTBALL_MAX_REQUESTS_PER_MINUTE,
    API_FOOTBALL_MAX_RETRIES,
    API_FOOTBALL_REQUEST_TIMEOUT_SECONDS,
)
from config.settings import Settings, get_settings
from src.data_providers.base_provider import MatchDataProvider
from src.data_providers.exceptions import (
    FixtureNotFoundError,
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderDataValidationError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from src.data_providers.schemas import (
    Fixture,
    Lineups,
    LiveStats,
    MatchEvent,
    MatchEvents,
    TeamLineup,
    TeamStatistics,
)
from src.utils.logger import get_logger
from src.utils.rate_limiter import AsyncRateLimiter

log = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MOCKS_DIR = _PROJECT_ROOT / "data" / "mocks"

_RETRYABLE_EXCEPTIONS = (ProviderConnectionError, ProviderRateLimitError)


class APIFootballClient(MatchDataProvider):
    """
    Free-tier-aware API-Football client.

    Usage:
        async with APIFootballClient() as client:
            fixtures = await client.get_live_fixtures()
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._rate_limiter = AsyncRateLimiter(
            max_calls=API_FOOTBALL_MAX_REQUESTS_PER_MINUTE,
            period_seconds=60.0,
        )
        self._http_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _ensure_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self._settings.api_football_base_url,
                headers={
                    "x-rapidapi-key": self._settings.require_rapidapi_key(),
                    "x-rapidapi-host": self._settings.rapidapi_host,
                },
                timeout=API_FOOTBALL_REQUEST_TIMEOUT_SECONDS,
            )
        return self._http_client

    async def close(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # Low-level HTTP with retry + rate limiting (live mode only)
    # ------------------------------------------------------------------
    @retry(
        reraise=True,
        stop=stop_after_attempt(API_FOOTBALL_MAX_RETRIES),
        wait=wait_exponential(multiplier=1.0, min=1.0, max=10.0),
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    )
    async def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        """Perform a single rate-limited, retried GET against API-Football."""
        client = self._ensure_http_client()

        async with self._rate_limiter:
            try:
                response = await client.get(endpoint, params=params)
            except httpx.TimeoutException as exc:
                raise ProviderConnectionError(f"Timeout calling {endpoint}") from exc
            except httpx.RequestError as exc:
                raise ProviderConnectionError(f"Network error calling {endpoint}: {exc}") from exc

        if response.status_code == 401 or response.status_code == 403:
            raise ProviderAuthenticationError(
                "API-Football rejected the request — check RAPIDAPI_KEY."
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ProviderRateLimitError(
                "API-Football free-tier rate limit reached.",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 400:
            raise ProviderResponseError(
                f"API-Football returned {response.status_code} for {endpoint}",
                status_code=response.status_code,
            )

        try:
            payload: dict = response.json()
        except ValueError as exc:
            raise ProviderDataValidationError(f"Non-JSON response from {endpoint}") from exc

        if payload.get("errors"):
            log.warning("API-Football returned errors payload: {}", payload["errors"])

        return payload

    # ------------------------------------------------------------------
    # Mock-mode file loading
    # ------------------------------------------------------------------
    @staticmethod
    def _load_mock(filename: str) -> dict:
        mock_path = _MOCKS_DIR / filename
        if not mock_path.exists():
            raise ProviderDataValidationError(f"Mock file not found: {mock_path}")
        try:
            return json.loads(mock_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderDataValidationError(f"Malformed mock JSON: {mock_path}") from exc

    async def _fetch(self, endpoint: str, params: dict[str, Any], mock_file: str) -> dict:
        """Route to live HTTP or local mock depending on configured data source mode."""
        if self._settings.is_live_mode:
            log.debug("LIVE fetch {} params={}", endpoint, params)
            return await self._get(endpoint, params)
        log.debug("MOCK fetch <- {}", mock_file)
        return self._load_mock(mock_file)

    # ------------------------------------------------------------------
    # Public interface (MatchDataProvider)
    # ------------------------------------------------------------------
    async def get_live_fixtures(self, league_id: int | None = None) -> list[Fixture]:
        params: dict[str, Any] = {"live": "all"}
        if league_id is not None:
            params["league"] = league_id

        payload = await self._fetch(
            "/fixtures", params=params, mock_file="mock_live_fixture.json"
        )
        raw_fixtures = payload.get("response", [])

        try:
            adapter = TypeAdapter(list[Fixture])
            return adapter.validate_python(raw_fixtures)
        except ValidationError as exc:
            raise ProviderDataValidationError(f"Could not parse fixtures: {exc}") from exc

    async def get_fixture(self, fixture_id: int) -> Fixture:
        payload = await self._fetch(
            "/fixtures",
            params={"id": fixture_id},
            mock_file="mock_live_fixture.json",
        )
        raw_fixtures = payload.get("response", [])
        if not raw_fixtures:
            raise FixtureNotFoundError(f"No fixture found with id={fixture_id}")

        try:
            fixture = Fixture.model_validate(raw_fixtures[0])
        except ValidationError as exc:
            raise ProviderDataValidationError(f"Could not parse fixture {fixture_id}: {exc}") from exc

        # In mock mode the JSON file isn't actually filtered server-side (there's
        # no server), so we must enforce the id match here ourselves — otherwise
        # any fixture_id would silently return the single mock fixture on file.
        if fixture.fixture_id != fixture_id:
            raise FixtureNotFoundError(f"No fixture found with id={fixture_id}")

        return fixture

    async def get_live_stats(self, fixture_id: int) -> LiveStats:
        payload = await self._fetch(
            "/fixtures/statistics",
            params={"fixture": fixture_id},
            mock_file="mock_live_stats.json",
        )
        raw_stats = payload.get("response", [])

        try:
            adapter = TypeAdapter(list[TeamStatistics])
            teams_statistics = adapter.validate_python(raw_stats)
        except ValidationError as exc:
            raise ProviderDataValidationError(
                f"Could not parse live stats for fixture {fixture_id}: {exc}"
            ) from exc

        return LiveStats(fixture_id=fixture_id, teams_statistics=teams_statistics)

    async def get_lineups(self, fixture_id: int) -> Lineups:
        payload = await self._fetch(
            "/fixtures/lineups",
            params={"fixture": fixture_id},
            mock_file="mock_lineup.json",
        )
        raw_lineups = payload.get("response", [])
        if len(raw_lineups) < 2:
            raise ProviderDataValidationError(
                f"Expected 2 lineups for fixture {fixture_id}, got {len(raw_lineups)}"
            )

        try:
            home_lineup = TeamLineup.model_validate(raw_lineups[0])
            away_lineup = TeamLineup.model_validate(raw_lineups[1])
        except ValidationError as exc:
            raise ProviderDataValidationError(
                f"Could not parse lineups for fixture {fixture_id}: {exc}"
            ) from exc

        return Lineups(fixture_id=fixture_id, home=home_lineup, away=away_lineup)

    async def get_events(self, fixture_id: int) -> MatchEvents:
        payload = await self._fetch(
            "/fixtures/events",
            params={"fixture": fixture_id},
            mock_file="mock_events.json",
        )
        raw_events = payload.get("response", [])

        try:
            adapter = TypeAdapter(list[MatchEvent])
            events = adapter.validate_python(raw_events)
        except ValidationError as exc:
            raise ProviderDataValidationError(
                f"Could not parse events for fixture {fixture_id}: {exc}"
            ) from exc

        return MatchEvents(fixture_id=fixture_id, events=events)
