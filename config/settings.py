from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataSourceMode(str, Enum):
    MOCK = "mock"
    LIVE = "live"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- API-Football / API-SPORTS Core Config ---
    # Accepts either the new API_FOOTBALL_KEY name or the legacy
    # RAPIDAPI_KEY name from existing .env files. AliasChoices checks
    # both, in order — a single string `validation_alias` would silently
    # disable the field-name-based (API_FOOTBALL_KEY) lookup entirely.
    api_football_key: str = Field(
        default="",
        validation_alias=AliasChoices("API_FOOTBALL_KEY", "RAPIDAPI_KEY"),
    )
    api_football_host: str = Field(default="v3.football.api-sports.io")
    api_football_base_url: str = Field(default="https://v3.football.api-sports.io")

    # --- AI Engine Configs ---
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-1.5-flash")

    # --- App behaviour ---
    data_source_mode: DataSourceMode = Field(default=DataSourceMode.MOCK)
    log_level: LogLevel = Field(default=LogLevel.INFO)
    poll_interval_seconds: int = Field(default=60, ge=5, le=600)
    cache_ttl_seconds: int = Field(default=45, ge=0, le=3600)

    @field_validator("api_football_key", "groq_api_key", "gemini_api_key")
    @classmethod
    def _strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @property
    def is_live_mode(self) -> bool:
        return self.data_source_mode is DataSourceMode.LIVE

    def require_api_football_key(self) -> str:
        if self.is_live_mode and not self.api_football_key:
            raise RuntimeError(
                "DATA_SOURCE_MODE=live but API_FOOTBALL_KEY (or RAPIDAPI_KEY) "
                "is not set. Set it in your .env file or switch DATA_SOURCE_MODE=mock."
            )
        return self.api_football_key

    def require_groq_key(self) -> str:
        if not self.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set.")
        return self.groq_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
