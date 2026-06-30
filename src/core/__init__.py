"""
Core domain logic.

Everything in this package is pure, deterministic Python with NO external
I/O (no HTTP, no file reads, no LLM calls). It only operates on typed
Pydantic objects handed to it — either real ones from `data_providers`, or
synthetic ones built in unit tests. This is what makes it trivially testable
and reusable regardless of which presentation layer (Streamlit, FastAPI,
Next.js backend) eventually drives it.
"""
