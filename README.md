<div align="center">

# ⚽ LiveGaffer

**Live Soccer Assistant Manager & AI Tactical Analyst**

Real-time match momentum, formation analysis, and LLM-generated tactical recommendations — built entirely on free-tier APIs.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg)](https://streamlit.io)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)](https://fastapi.tiangolo.com)

</div>

---

## What is LiveGaffer?

LiveGaffer watches a live football match and acts as a virtual assistant manager. It pulls live fixture data, computes a momentum/pressure index for each team, independently verifies each team's formation from raw lineup data, and feeds all of that into an LLM tactical analyst that returns structured, actionable recommendations — substitutions, formation tweaks, attacking or defensive adjustments — each with a priority and a rationale tied to what's actually happening in the match.

Everything runs on **100% free-tier services**: [API-Football](https://www.api-football.com/) (RapidAPI) for match data, and [Groq](https://console.groq.com) (primary) with [Gemini](https://ai.google.dev/) (fallback) for the AI engine. A bundled mock-data mode lets the entire app — UI, momentum engine, formation analyzer, and AI panel — run end-to-end with **zero API keys and zero network calls**.

## Features

- **Live momentum engine** — blends decayed recent-event weight (goals, cards, big chances) with sustained live-stat pressure (shots, corners, possession) into a 0–100 index per team
- **Independent formation analysis** — derives each team's actual shape from starting-XI positions rather than trusting the API's declared label, and flags mismatches
- **AI tactical analyst** — Groq-first, Gemini-fallback LLM pipeline that turns a match snapshot into a strict, Pydantic-validated `TacticalAnalysis`: summary, momentum read, key observations, and prioritized recommendations
- **Mock-mode by default** — every layer works offline against bundled fixture JSON, so you can develop and demo without spending any free-tier quota
- **Two presentation layers, one domain core** — a Streamlit dashboard for humans today, and an optional FastAPI REST layer ready for a Next.js (or any other) frontend tomorrow
- **TTL caching + rate limiting** — keeps the app safely inside API-Football's and the LLM providers' free-tier limits, even under repeated polling

## Architecture

LiveGaffer is built in clean, dependency-inverted layers — each one only knows about the layer directly below it:

```
┌─────────────────────────────────────────────────────────┐
│  app/            Presentation layer                     │
│    streamlit_app.py     Live dashboard                  │
│    api/                 Optional FastAPI REST layer     │
├─────────────────────────────────────────────────────────┤
│  src/services/   Orchestration + caching                │
│    live_match_service.py    data + core → MatchState    │
│    analysis_service.py      + AI engine → TacticalAnalysis│
│    cache_service.py         async TTL cache              │
├─────────────────────────────────────────────────────────┤
│  src/ai_engine/  Tactical reasoning (Groq → Gemini)      │
│  src/core/       Pure domain logic (momentum, formation) │
│  src/data_providers/  API-Football client + mock mode    │
├─────────────────────────────────────────────────────────┤
│  config/         Typed settings & domain constants       │
└─────────────────────────────────────────────────────────┘
```

- **`data_providers`** — typed Pydantic schemas mirroring API-Football's real JSON shape, behind an abstract `MatchDataProvider` interface. The concrete client transparently switches between live HTTP calls and local mock JSON with zero downstream code changes.
- **`core`** — pure, dependency-free Python: event normalization, the momentum/pressure engine, and the formation analyzer. Fully unit-testable with no I/O.
- **`ai_engine`** — an abstract `LLMClient` interface implemented by Groq (primary) and Gemini (fallback), orchestrated by `TacticalAnalyst`, which builds the prompt, handles fallback-on-failure, and validates the response against a strict output schema.
- **`services`** — wires the above together with TTL caching so a polling UI doesn't re-spend API or LLM quota on every refresh.

## Tech stack

| Layer | Technology |
|---|---|
| Match data | [API-Football](https://www.api-football.com/) via RapidAPI (free tier) |
| AI — primary | [Groq](https://console.groq.com) (Llama 3.3, free tier) |
| AI — fallback | [Google Gemini](https://ai.google.dev/) (free tier) |
| Validation | Pydantic v2 / Pydantic Settings |
| HTTP | httpx + tenacity (retry/backoff) |
| Dashboard | Streamlit |
| API (optional) | FastAPI + Uvicorn |
| Logging | Loguru |

## Getting started

### Prerequisites

- Python 3.11+
- (Optional, for live mode) a free [RapidAPI](https://rapidapi.com/api-sports/api/api-football) key for API-Football, a free [Groq](https://console.groq.com) API key, and optionally a free [Gemini](https://ai.google.dev/) API key

### Installation

```bash
git clone https://github.com/abdelkabirouadoukou/LiveGaffer.git
cd LiveGaffer

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
```

By default, `.env` sets `DATA_SOURCE_MODE=mock` — the app runs fully offline against the bundled Real Madrid vs. Barcelona fixture in `data/mocks/`. No keys required to try it.

### Run the dashboard

```bash
streamlit run app/streamlit_app.py
```

Open the URL Streamlit prints (typically `http://localhost:8501`). In mock mode, enter fixture ID `1035001` in the sidebar (it's the default) to load the sample match.

### Run the optional REST API

```bash
python -m uvicorn app.api.main:app --reload --port 8000
```

Interactive docs at `http://127.0.0.1:8000/docs`.

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check + active data-source mode |
| `GET /fixtures` | List currently live fixtures (`?league_id=` optional) |
| `GET /fixtures/{id}/state` | Full derived match state — score, momentum, formations, events |
| `GET /fixtures/{id}/analysis` | AI tactical analysis (`?force_refresh=true` to bypass cache) |

### Going live

Set real credentials in `.env` and flip the mode:

```dotenv
DATA_SOURCE_MODE=live

RAPIDAPI_KEY=your_rapidapi_key
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key   # optional fallback
```

No other code changes are needed — every layer above `data_providers` and `ai_engine` is identical in mock and live mode.

## Configuration reference

All settings are typed and validated via `config/settings.py` (Pydantic Settings), loaded from `.env`:

| Variable | Default | Description |
|---|---|---|
| `DATA_SOURCE_MODE` | `mock` | `mock` (offline) or `live` (real API-Football calls) |
| `RAPIDAPI_KEY` | — | Required when `DATA_SOURCE_MODE=live` |
| `RAPIDAPI_HOST` | `api-football-v1.p.rapidapi.com` | RapidAPI host header |
| `API_FOOTBALL_BASE_URL` | `https://api-football-v1.p.rapidapi.com/v3` | API-Football base URL |
| `GROQ_API_KEY` | — | Required for AI analysis (primary provider) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name |
| `GEMINI_API_KEY` | — | Optional fallback provider |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model name |
| `POLL_INTERVAL_SECONDS` | `60` | Suggested dashboard auto-refresh interval (5–600) |
| `CACHE_TTL_SECONDS` | `45` | TTL for cached match-data fetches (0–3600); AI analysis is cached at 2× this |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

## Project structure

```
LiveGaffer/
├── config/
│   ├── settings.py            # Typed env config (Pydantic Settings)
│   └── constants.py           # League IDs, formation shapes, momentum weights
│
├── src/
│   ├── data_providers/        # API-Football client + mock-mode + schemas
│   ├── core/                  # Pure domain logic: momentum, formations, events
│   ├── ai_engine/              # Groq/Gemini clients + tactical analyst orchestrator
│   ├── services/                # Caching + orchestration glue
│   └── utils/                   # Logging, async rate limiter
│
├── app/
│   ├── streamlit_app.py       # Live dashboard
│   └── api/                   # Optional FastAPI REST layer
│       ├── main.py
│       └── routers/
│
├── data/
│   ├── mocks/                  # Offline fixture JSON (Real Madrid vs Barcelona)
│   └── cache/                  # Runtime cache storage (gitignored)
│
└── tests/
```

## How the momentum engine works

Each team's momentum index blends two signals into a single 0–100 score:

1. **Event momentum** — recent events (goals, cards, big chances, corners) weighted by type and linearly decayed over a configurable window, so a goal two minutes ago dominates a yellow card from forty minutes ago.
2. **Snapshot pressure** — a baseline from cumulative live stats (shots on goal, total shots, corners, possession), capturing sustained territorial control even between discrete events.

The differential between both teams' indices drives how urgently the AI tactical engine recommends a change.

## How the AI tactical engine works

1. `prompt_templates` serializes the current `MatchState` (score, minute, momentum, formations, recent events) into a compact prompt with an embedded JSON schema spec.
2. `TacticalAnalyst` calls Groq first; on any provider-side failure it transparently falls back to Gemini.
3. The raw response is cleaned (stray markdown fences stripped) and validated against a strict `TacticalAnalysis` Pydantic schema — malformed or hallucinated output fails loudly rather than silently reaching the UI.
4. The result is cached per fixture so repeated dashboard polls within the TTL window don't burn extra LLM quota.

## Roadmap

- [x] Phase 1 — Foundation & configuration
- [x] Phase 2 — Data provider layer (API-Football + mock mode)
- [x] Phase 3 — Core domain logic (momentum, formations, events)
- [x] Phase 4 — AI tactical engine (Groq + Gemini)
- [x] Phase 5 — Service orchestration, Streamlit dashboard, optional FastAPI layer
- [ ] Automated test suite (`tests/`)
- [ ] Next.js frontend consuming the FastAPI layer
- [ ] Persistent cache backend (Redis) for multi-worker deployments
- [ ] Historical match review / post-match report generation

## Contributing

Issues and pull requests are welcome. Please keep new code in the same layered style — pure logic in `core/`, I/O behind an abstract interface, and orchestration in `services/`.

## License

[MIT](LICENSE)