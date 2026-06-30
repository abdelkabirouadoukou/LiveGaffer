"""
AI tactical-analysis endpoint.

Thin HTTP wrapper around `AnalysisService.get_tactical_analysis`. Every
exception type the service layer can raise (data-provider failures,
missing fixtures, both LLM providers exhausted, unparseable LLM output)
is mapped to a distinct, specific HTTP status so a frontend can react
appropriately instead of treating every failure as a generic 500.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.ai_engine.exceptions import AllProvidersExhaustedError, LLMOutputParsingError
from src.data_providers.exceptions import DataProviderError, FixtureNotFoundError
from src.services.analysis_service import AnalysisService

router = APIRouter(prefix="/fixtures", tags=["analysis"])


def _service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


@router.get("/{fixture_id}/analysis")
async def get_tactical_analysis(
    fixture_id: int,
    request: Request,
    force_refresh: bool = Query(
        default=False, description="Bypass the cache and regenerate a fresh analysis."
    ),
) -> dict:
    """Return the AI tactical analyst's latest structured read on a fixture."""
    service = _service(request)
    try:
        analysis = await service.get_tactical_analysis(fixture_id, force_refresh=force_refresh)
    except FixtureNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=f"Match data unavailable: {exc}") from exc
    except AllProvidersExhaustedError as exc:
        raise HTTPException(status_code=503, detail=f"All AI providers failed: {exc}") from exc
    except LLMOutputParsingError as exc:
        raise HTTPException(status_code=502, detail=f"AI response could not be parsed: {exc}") from exc
    except RuntimeError as exc:
        # Missing GROQ_API_KEY / GEMINI_API_KEY surfaces as a plain
        # RuntimeError from config.settings — treat as a server
        # configuration problem (503), not an unhandled 500.
        raise HTTPException(status_code=503, detail=f"AI engine is not configured: {exc}") from exc
    return analysis.model_dump(mode="json")