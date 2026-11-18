"""Dashboard statistics (brief section 7): median days earlier and exceptions by type."""

from __future__ import annotations

import statistics
from collections import Counter

from fastapi import APIRouter, Depends

from app.api import AppState, get_state
from app.schemas import Kpis

router = APIRouter(prefix="/api", tags=["kpis"])


@router.get("/kpis")
def kpis(state: AppState = Depends(get_state)) -> Kpis:
    """Header numbers for the latest run (zeros before the first run)."""
    run = state.db.latest_run()
    if run is None:
        return Kpis(
            run_id=None, exceptions=0, open_exceptions=0, median_days_earlier=None,
            blind_spots=0, by_type={}, old_rule_lines=0, old_rule_overdue_abs=0.0,
            exposure_groups_above=0,
        )  # fmt: skip
    records = state.db.list_exceptions(run.run_id)
    leads = [r.lead_days for r in records if r.lead_days is not None]
    from app.engines.exposure import payroll_netting

    netting = payroll_netting(
        state.pipeline.lines(run.snapshot_id), state.db.get_rules().materiality_eur
    )
    return Kpis(
        run_id=run.run_id,
        exceptions=len(records),
        open_exceptions=sum(r.status in {"new", "escalated"} for r in records),
        median_days_earlier=float(statistics.median(leads)) if leads else None,
        blind_spots=sum(r.today_detection is None for r in records),
        by_type=dict(Counter(r.type for r in records)),
        old_rule_lines=netting.old_rule_lines,
        old_rule_overdue_abs=netting.old_rule_overdue_abs,
        exposure_groups_above=netting.groups_above(),
    )
