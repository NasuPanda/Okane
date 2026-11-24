"""Paths, settings and environment.

Every setting can be overridden with an ``OKANE_``-prefixed environment variable or a
``backend/.env`` file (see ``backend/.env.example``). Business thresholds do NOT live here:
they belong to the controller-owned ``Rules`` model (brief section 7).
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
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
    # The watched folder (A38 route b). It may be a synced shared folder; Okane only reads and
    # copies from it, never moves or deletes anything there.
    inbox_dir: Path = REPO_ROOT / "data" / "inbox"
    # Okane's own store of the current extract per kind, and the archive of replaced extracts.
    # Empty means "under data_dir", so a temp data_dir keeps everything in one place.
    extracts_dir: Path | None = None
    archive_dir: Path | None = None
    sample_dir: Path = REPO_ROOT / "data" / "sample"
    rates_path: Path = REPO_ROOT / "data" / "rates.csv"
    db_path: Path = REPO_ROOT / "data" / "okane.duckdb"
    fixtures_dir: Path = REPO_ROOT / "fixtures"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    # Analysis date override. Empty means the day the Payroll extract was taken (A38), or today
    # when no extract date can be worked out; set it to replay a past Monday.
    as_of: date | None = None

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_timeout_s: float = 60.0
    ai_enabled: bool = True
    # Draft comments during a run for this many top-ranked exceptions (0 = only on demand).
    ai_predraft_top: int = 3
    # Hosted demo only: comments drafted earlier on the SYNTHETIC sample (``make ai-seed``),
    # loaded into the comment cache at startup so a host without a model still shows checked
    # drafts. Empty means no seed. The file must carry the ``"synthetic": true`` marker.
    ai_seed_path: Path | None = None

    cors_origins: list[str] = ["http://localhost:5173"]

    enable_watcher: bool = True
    enable_scheduler: bool = True
    run_on_startup: bool = True
    schedule_day_of_week: str = "mon"
    schedule_hour: int = 6
    schedule_minute: int = 0
    watcher_debounce_s: float = 2.0

    default_user: str = "controller"
    upload_max_mb: int = 50

    @model_validator(mode="after")
    def _store_under_data_dir(self) -> Settings:
        if self.extracts_dir is None:
            self.extracts_dir = self.data_dir / "extracts"
        if self.archive_dir is None:
            self.archive_dir = self.data_dir / "archive"
        return self

    @property
    def store_dir(self) -> Path:
        """``extracts_dir`` after validation (never None)."""
        assert self.extracts_dir is not None
        return self.extracts_dir

    @property
    def archive_path(self) -> Path:
        """``archive_dir`` after validation (never None)."""
        assert self.archive_dir is not None
        return self.archive_dir

    def today(self) -> date:
        """The override, else the real date. The pipeline prefers the extract date (A38)."""
        return self.as_of or date.today()


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance; tests clear the cache after changing the environment."""
    return Settings()
