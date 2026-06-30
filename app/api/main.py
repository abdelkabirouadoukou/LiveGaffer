"""
FastAPI presentation layer (optional, future-Next.js-ready backend).

This exposes the exact same `AnalysisService` used by `streamlit_app.py`
as a small REST API, so a future Next.js (or any other) frontend can
consume live match state and AI tactical analysis without touching Python.

Run locally from the project root (so the `app`/`config`/`src` packages
resolve correctly):

    python -m uvicorn app.api.main:app --reload --port 8000

Then browse to http://127.0.0.1:8000/docs for interactive API docs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import analysis, matches
from config.settings import get_settings
from src.services.analysis_service import AnalysisService
from src.utils.logger import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Build one long-lived `AnalysisService` (and its underlying HTTP/AI
    clients) for the life of the process, instead of one per request.

    Unlike the Streamlit app — which reruns its whole script per
    interaction and therefore rebuilds services per call to stay
    event-loop-safe — a FastAPI app under uvicorn runs a single, stable
    event loop for its whole lifetime, so a persistent service here is
    both correct and what makes the TTL cache and rate limiter actually
    do their job across requests.
    """
    settings = get_settings()
    log.info("Starting API in '{}' data-source mode", settings.data_source_mode.value)
    app.state.analysis_service = AnalysisService(settings=settings)
    try:
        yield
    finally:
        await app.state.analysis_service.close()
        log.info("AnalysisService closed.")


app = FastAPI(
    title="Live Soccer AI Manager API",
    description="Free-tier live match data + AI tactical analysis, ready for a Next.js frontend.",
    version="0.1.0",
    lifespan=lifespan,
)

# Permissive CORS for local frontend development. Tighten `allow_origins`
# to specific domains before deploying this anywhere public.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches.router)
app.include_router(analysis.router)


@app.get("/health", tags=["meta"])
async def health_check() -> dict[str, str]:
    """Lightweight liveness/readiness check, including which data-source mode is active."""
    settings = get_settings()
    return {"status": "ok", "data_source_mode": settings.data_source_mode.value}