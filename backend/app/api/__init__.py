"""API routers, one module per area (brief section 7 endpoint table)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import Settings
from app.database import Database
from app.schemas import Run
from app.services.pipeline import EventBus, Pipeline


@dataclass
class AppState:
    settings: Settings
    db: Database
    bus: EventBus
    pipeline: Pipeline


def get_state(request: Request) -> AppState:
    """FastAPI dependency: the shared application state."""
    return request.app.state.okane  # type: ignore[no-any-return]


def require_latest_run(state: AppState) -> Run:
    """The latest finished run, or 404 with a helpful message."""
    run = state.db.latest_run()
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="No finished run yet. Start one with POST /api/runs or drop a workbook "
            "in data/inbox/.",
        )
    return run
