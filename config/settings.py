"""
Centralized, typed application settings.

Every other module reads configuration through this module instead of calling
os.environ directly. This keeps secrets validated in one place and makes the
app fail fast (at startup) if a required key is missing — rather than failing
deep inside an HTTP call at runtime.

Usage:
    from config.settings import get_settings
    settings = get_settings()
    settings.groq_api_key
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataSourceMode(str, Enum):
    """Controls whether the data layer hits the real API or local mocks."""

    MOCK = "mock"
    LIVE = "live"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """
    Strongly-typed environment configuration.

    All fields are loaded from a `.env` file (see `.env.example`) or from
    real environment variables, with environment variables taking precedence.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- API-Football (RapidAPI) ---------------------------------------
    rapidapi_key: str = Field(default="", description="RapidAPI key for API-Football")
    rapidapi_host: str = Field(default="api-football-v1.p.rapidapi.com")
    api_football_base_url: str = Field(
        default="https://api-football-v1.p.rapidapi.com/v3"
    )

    # --- AI Engine: Groq (primary) ---------------------------------------
    groq_api_key: str = Field(default="", description="Groq free-tier API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile")

    # --- AI Engine: Gemini (fallback) -------------------------------------
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(default="gemini-1.5-flash")

    # --- App behaviour -----------------------------------------------------
    data_source_mode: DataSourceMode = Field(default=DataSourceMode.MOCK)
    log_level: LogLevel = Field(default=LogLevel.INFO)
    poll_interval_seconds: int = Field(default=60, ge=5, le=600)
    cache_ttl_seconds: int = Field(default=45, ge=0, le=3600)

    @field_validator("rapidapi_key", "groq_api_key", "gemini_api_key")
    @classmethod
    def _strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @property
    def is_live_mode(self) -> bool:
        return self.data_source_mode is DataSourceMode.LIVE

    def require_rapidapi_key(self) -> str:
        """Raise loudly if live mode is requested without a key configured."""
        if self.is_live_mode and not self.rapidapi_key:
            raise RuntimeError(
                "DATA_SOURCE_MODE=live but RAPIDAPI_KEY is not set. "
                "Set it in your .env file or switch DATA_SOURCE_MODE=mock."
            )
        return self.rapidapi_key

    def require_groq_key(self) -> str:
        if not self.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Get a free key at https://console.groq.com"
            )
        return self.groq_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached, process-wide Settings instance.

    Cached via lru_cache so we parse the .env file once. Tests can bypass this
    by constructing `Settings(...)` directly or by calling
    `get_settings.cache_clear()`.
    """
    return Settings()
