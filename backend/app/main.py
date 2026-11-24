"""FastAPI application.

``create_app()`` wires settings, the DuckDB database, the pipeline, the event bus and the jobs
(folder watcher and Monday scheduler). In production (``make serve``) it also serves the built
frontend from ``frontend/dist`` on the same port.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai.client import assistant_status, load_seed
from app.api import AppState, exceptions, exposure, kpis, pulse, rules, runs, uploads
from app.config import Settings, get_settings
from app.database import Database
from app.jobs import Jobs
from app.schemas import AssistantState
from app.services.pipeline import EventBus, Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("okane")


def _startup_run(state: AppState) -> None:
    if state.db.latest_run(finished_only=False) is None:
        threading.Thread(
            target=state.pipeline.trigger, args=("startup",), daemon=True, name="okane-startup"
        ).start()


def _load_ai_seed(settings: Settings, db: Database) -> None:
    """Hosted demo: seed the comment cache with drafts made earlier on the sample (A48)."""
    path = settings.ai_seed_path
    if path is None:
        return
    if not path.is_file():
        log.warning("AI seed %s not found; comments fall back to the model or the template", path)
        return
    try:
        added = load_seed(path, db)
    except (OSError, ValueError) as exc:
        log.warning("AI seed not loaded: %s", exc)
        return
    log.info("AI seed: %d cached outcomes added from %s", added, path.name)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Settings are read once, at creation."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.db_path)
        _load_ai_seed(settings, db)
        bus = EventBus()
        state = AppState(settings=settings, db=db, bus=bus, pipeline=Pipeline(db, settings, bus))
        app.state.okane = state
        jobs = Jobs(settings, state.pipeline.trigger)
        jobs.start()
        if settings.run_on_startup:
            _startup_run(state)
        try:
            yield
        finally:
            jobs.stop()
            db.close()

    app = FastAPI(
        title="Okane",
        version="0.1.0",
        description="Read-only reconciliation copilot. Amounts are scaled EUR.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["*"],
    )
    for module in (runs, uploads, exceptions, exposure, pulse, rules, kpis):
        app.include_router(module.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness probe. It calls nothing else: the hosted demo leaves it open (A41)."""
        return {"status": "ok"}

    @app.get("/api/assistant", tags=["meta"])
    def assistant() -> AssistantState:
        """Whether the assistant can draft notes (A45)."""
        return assistant_status(settings)

    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    """Serve the built single-page app, falling back to index.html for client routes."""
    dist = settings.frontend_dist
    index = dist / "index.html"
    if not index.exists():
        return
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
