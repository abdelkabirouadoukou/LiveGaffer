"""
Match-data endpoints: live fixtures list + derived match state.

All routes here are read-only and delegate entirely to the process-wide
`AnalysisService` built in `app.api.main`'s lifespan — routers never talk
to `data_providers` or `core` directly.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.data_providers.exceptions import DataProviderError, FixtureNotFoundError
from src.services.analysis_service import AnalysisService

router = APIRouter(prefix="/fixtures", tags=["matches"])


def _service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


@router.get("")
async def list_live_fixtures(request: Request, league_id: int | None = None) -> list[dict]:
    """Return all currently in-play fixtures, optionally filtered by `league_id`."""
    service = _service(request)
    try:
        fixtures = await service.list_live_fixtures(league_id=league_id)
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [fixture.model_dump(mode="json") for fixture in fixtures]


@router.get("/{fixture_id}/state")
async def get_match_state(fixture_id: int, request: Request) -> dict:
    """Return the fully-derived `MatchState` (momentum, formations, events) for one fixture."""
    service = _service(request)
    try:
        state = await service.get_match_state(fixture_id)
    except FixtureNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return state.model_dump(mode="json")