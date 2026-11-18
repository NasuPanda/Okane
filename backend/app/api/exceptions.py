"""Exception inbox, detail, decisions and AI comment (brief section 7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.ai.client import draft_comment
from app.api import AppState, get_state, require_latest_run
from app.database import utcnow
from app.schemas import (
    Comment,
    DecisionEntry,
    DecisionUpdate,
    EvidenceLine,
    ExceptionDetail,
    ExceptionRecord,
    ExceptionType,
    PulseTimeline,
    Status,
    Workgroup,
)

router = APIRouter(prefix="/api/exceptions", tags=["exceptions"])
MAX_EVIDENCE_LINES = 500


@router.get("")
def list_exceptions(
    type: ExceptionType | None = None,
    workgroup: Workgroup | None = None,
    entity: str | None = None,
    min_exposure: float | None = None,
    status: Status | None = None,
    state: AppState = Depends(get_state),
) -> list[ExceptionRecord]:
    """Exceptions of the latest run, highest score first, with optional filters."""
    run = require_latest_run(state)
    records = state.db.list_exceptions(run.run_id)
    if type is not None:
        records = [r for r in records if r.type == type]
    if workgroup is not None:
        records = [r for r in records if r.workgroup == workgroup]
    if entity is not None:
        records = [r for r in records if r.entity == entity]
    if min_exposure is not None:
        records = [r for r in records if abs(r.exposure_eur) >= min_exposure]
    if status is not None:
        records = [r for r in records if r.status == status]
    return records


def _get(state: AppState, exception_id: str) -> ExceptionRecord:
    run = require_latest_run(state)
    record = state.db.get_exception(run.run_id, exception_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Exception not found in the latest run")
    return record


def _evidence_lines(state: AppState, record: ExceptionRecord) -> list[EvidenceLine]:
    run = require_latest_run(state)
    lines = state.pipeline.lines(run.snapshot_id)
    refs = lines["document_no"] + "/" + lines["year"].astype("string")
    mask = (
        refs.isin(record.evidence)
        & (lines["erp"] == record.erp)
        & (lines["entity"] == record.entity)
        & (lines["account"] == record.account)
    )
    chosen = lines[mask].sort_values(["posting_date", "line_id"]).head(MAX_EVIDENCE_LINES)
    return [
        EvidenceLine(
            document=f"{row.document_no}/{row.year}",
            posting_date=row.posting_date,
            doc_type=row.doc_type,
            user_name=row.user_name,
            text=row.text,
            amount_eur=float(row.amount_eur),
            currency_dc=row.currency_dc,
            amount_dc=float(row.amount_dc),
        )
        for row in chosen.itertuples()
    ]


@router.get("/{exception_id}")
def get_exception(exception_id: str, state: AppState = Depends(get_state)) -> ExceptionDetail:
    """One exception with its evidence lines, gap chart series and decision history."""
    record = _get(state, exception_id)
    key = f"{record.erp}/{record.entity}/{record.account}"
    payload = state.db.get_artifact(record.run_id, "timeline", key)
    timeline = PulseTimeline.model_validate_json(payload).points if payload else None
    return ExceptionDetail(
        exception=record,
        evidence_lines=_evidence_lines(state, record),
        timeline=timeline,
        decisions=state.db.decisions_for(record.id),
    )


@router.patch("/{exception_id}")
def decide(
    exception_id: str, update: DecisionUpdate, state: AppState = Depends(get_state)
) -> ExceptionRecord:
    """Set status, class, reason or an edited comment. A decision always needs a reason."""
    record = _get(state, exception_id)
    status = update.status or record.status
    # an unchanged status keeps its earlier reason (e.g. when only the comment is edited)
    reason = update.decision_reason
    if reason is None and update.status is None:
        reason = record.decision_reason
    if status != "new" and not (reason or "").strip():
        raise HTTPException(
            status_code=422,
            detail="A reason is required to explain, dismiss or escalate an exception.",
        )
    entry = DecisionEntry(
        exception_id=record.id,
        status=status,
        decision_reason=(reason or "").strip() or None,
        decided_class=update.decided_class or record.decided_class,
        edited_comment=update.edited_comment
        if update.edited_comment is not None
        else record.edited_comment,
        decided_by=update.decided_by or state.settings.default_user,
        decided_at=utcnow(),
    )
    state.db.save_decision(entry)
    return _get(state, exception_id)


@router.post("/{exception_id}/comment")
async def comment(
    exception_id: str, refresh: bool = False, state: AppState = Depends(get_state)
) -> Comment:
    """AI draft with the verifier result (cached by exception id and facts)."""
    record = _get(state, exception_id)
    result = await run_in_threadpool(draft_comment, record, state.db, state.settings, refresh)
    state.db.update_exception_comment(record.run_id, record.id, result.comment, result.verifier)
    return result
