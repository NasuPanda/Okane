"""Upload a weekly extract (docs/ASSUMPTIONS.md A38, route a).

``POST /api/uploads?filename=Payroll.xlsx`` takes the workbook as the raw request body. The file
goes through the same intake step as the watched folder; an accepted file starts a run with
trigger ``upload``. A wrong file (422) or one already loaded (409) gets a plain message and no
run. The upload is a copy: nothing is ever written back to a source.

ASSUMPTION (A38): the raw body (not multipart) keeps the backend free of an extra dependency;
the browser sends the File object as the body.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api import AppState, get_state
from app.ingest import WORKBOOK_SUFFIXES
from app.schemas import UploadResult

router = APIRouter(prefix="/api", tags=["uploads"])

BODY_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.post("/uploads", status_code=status.HTTP_202_ACCEPTED, openapi_extra=BODY_SCHEMA)
async def upload_extract(
    request: Request,
    filename: str,
    uploaded_by: str | None = None,
    state: AppState = Depends(get_state),
) -> UploadResult:
    """Check an uploaded Payroll or Fixed assets extract, store a copy and start a run."""
    name = Path(filename).name
    if not name or name != filename or not name.lower().endswith(WORKBOOK_SUFFIXES):
        raise HTTPException(422, f"{filename} is not an Excel workbook (.xlsx, .xlsm or .xls).")
    limit = state.settings.upload_max_mb * 1024 * 1024

    tmp_root = state.settings.data_dir / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(dir=tmp_root))
    try:
        target = folder / name  # keeps the person's file name in any message
        size = 0
        with target.open("wb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        413, f"{name} is larger than {state.settings.upload_max_mb} MB."
                    )
                handle.write(chunk)
        if size == 0:
            raise HTTPException(422, f"{name} is empty.")
        result = await run_in_threadpool(
            state.pipeline.intake.accept, target, "upload", name, uploaded_by
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    if result.status == "duplicate":
        raise HTTPException(409, result.message)
    if result.status == "rejected":
        raise HTTPException(422, result.message)
    run = state.pipeline.trigger("upload")
    message = result.message + (
        " Checking it now." if run else " A check is running; this extract is checked next."
    )
    return UploadResult(
        status="accepted",
        kind=result.kind,  # type: ignore[arg-type]
        file_name=name,
        message=message,
        run=run,
    )
