"""
AI tactical engine.

Turns a `core.match_state.MatchState` into a structured tactical analysis
using a free-tier LLM (Groq primary, Gemini fallback). The LLM clients are
swappable behind `base_llm_client.LLMClient`; `tactical_analyst.py` is the
only module that knows about the primary/fallback wiring.
"""
