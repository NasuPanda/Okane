"""Paths, settings and environment.

Every setting can be overridden with an ``OKANE_``-prefixed environment variable or a
``backend/.env`` file (see ``backend/.env.example``). Business thresholds do NOT live here:
they belong to the controller-owned ``Rules`` model (brief section 7).
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings read from the environment with sensible local defaults."""

    model_config = SettingsConfigDict(
        env_prefix="OKANE_",
        env_file=REPO_ROOT / "backend" / ".env",
        extra="ignore",
    )

    data_dir: Path = REPO_ROOT / "data"
    inbox_dir: Path = REPO_ROOT / "data" / "inbox"
    sample_dir: Path = REPO_ROOT / "data" / "sample"
    rates_path: Path = REPO_ROOT / "data" / "rates.csv"
    db_path: Path = REPO_ROOT / "data" / "okane.duckdb"
    fixtures_dir: Path = REPO_ROOT / "fixtures"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    # Analysis date. Empty means "today"; set it to replay a past Monday.
    as_of: date | None = None

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_timeout_s: float = 60.0
    ai_enabled: bool = True

    cors_origins: list[str] = ["http://localhost:5173"]

    enable_watcher: bool = True
    enable_scheduler: bool = True
    run_on_startup: bool = True
    schedule_day_of_week: str = "mon"
    schedule_hour: int = 6
    schedule_minute: int = 0
    watcher_debounce_s: float = 2.0

    default_user: str = "controller"

    def today(self) -> date:
        """The analysis date used by every engine (``as_of`` or the real date)."""
        return self.as_of or date.today()


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance; tests clear the cache after changing the environment."""
    return Settings()
