"""Pulse account status and gap timelines (brief section 7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api import AppState, get_state, require_latest_run
from app.schemas import PulseTimeline

router = APIRouter(prefix="/api/pulse", tags=["pulse"])


@router.get("/accounts")
def pulse_accounts(state: AppState = Depends(get_state)) -> list[str]:
    """Accounts with a payment profile in the latest run (``ERP/entity/account``)."""
    return [p.key for p in state.db.get_rules().payment_profiles]


@router.get("/{erp}/{entity}/{account}/timeline")
def timeline(
    erp: str, entity: str, account: str, state: AppState = Depends(get_state)
) -> PulseTimeline:
    """Month-end balance, expected balance and gap, plus each batch and its payments."""
    run = require_latest_run(state)
    payload = state.db.get_artifact(run.run_id, "timeline", f"{erp}/{entity}/{account}")
    if payload is None:
        raise HTTPException(
            status_code=404, detail="No payment profile for this account in the latest run"
        )
    return PulseTimeline.model_validate_json(payload)
