"""Payroll netting results with a live materiality parameter (brief section 7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api import AppState, get_state, require_latest_run
from app.engines.exposure import payroll_netting
from app.schemas import ExposureResponse

router = APIRouter(prefix="/api/exposure", tags=["exposure"])


@router.get("/payroll")
def payroll_exposure(
    materiality: float | None = Query(default=None, ge=0),
    state: AppState = Depends(get_state),
) -> ExposureResponse:
    """Old-rule totals and per-account netting. ``materiality`` overrides the rule for a
    what-if view (the slider); it does not change the saved rules."""
    run = require_latest_run(state)
    rules = state.db.get_rules()
    threshold = materiality if materiality is not None else rules.materiality_eur
    result = payroll_netting(state.pipeline.lines(run.snapshot_id), threshold, rules)
    # A46: an account links to the finding about its balance (the gap, or its open balance
    # when no Pulse check covers it); otherwise to its highest-scored finding.
    linked: dict[tuple[str, str, str], str] = {}
    records = state.db.list_exceptions(run.run_id)  # highest score first
    for record in records:
        if record.type in ("pulse_gap", "open_balance"):
            linked.setdefault((record.erp, record.entity, record.account), record.id)
    for record in records:
        linked.setdefault((record.erp, record.entity, record.account), record.id)
    groups = [
        g.model_copy(update={"exception_id": linked.get((g.erp, g.entity, g.account))})
        for g in result.groups
    ]
    return ExposureResponse(
        run_id=run.run_id,
        materiality_eur=threshold,
        old_rule_lines=result.old_rule_lines,
        old_rule_overdue_abs=result.old_rule_overdue_abs,
        net_eur=result.net_eur,
        groups_above=result.groups_above(),
        groups=groups,
    )
