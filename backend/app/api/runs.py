"""Run management and server-sent events (brief section 7)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse

from app.api import AppState, get_state
from app.schemas import Run
from app.services.pipeline import RunInProgressError

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs/latest")
def latest_run(state: AppState = Depends(get_state)) -> Run | None:
    """The most recent run (running, finished or failed), or null before the first run."""
    return state.db.latest_run(finished_only=False)


@router.get("/runs")
def list_runs(limit: int = 20, state: AppState = Depends(get_state)) -> list[Run]:
    """Recent runs, newest first."""
    return state.db.list_runs(limit)


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(wait: bool = False, state: AppState = Depends(get_state)) -> Run:
    """Start a run on the newest workbooks. ``wait=true`` returns the finished run."""
    try:
        if wait:
            return await run_in_threadpool(state.pipeline.run_now, "manual")
        return state.pipeline.run_in_background("manual")
    except RunInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/events")
async def events(request: Request, state: AppState = Depends(get_state)) -> EventSourceResponse:
    """Server-sent events: ``run_started`` and ``run_finished``."""
    queue = state.bus.subscribe()

    async def stream() -> AsyncIterator[dict[str, Any]]:
        try:
            yield {"event": "ready", "data": "{}"}
            while not await request.is_disconnected():
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    continue
        finally:
            state.bus.unsubscribe(queue)

    return EventSourceResponse(stream(), ping=15)
