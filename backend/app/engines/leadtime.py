"""Detection lead time (brief section 1, feature 2; section 9, "Lead time").

For every finding: ``first_signal`` (set by the engine: when Okane can first flag it),
``today_detection`` (when today's process would flag it; None = never) and
``lead_days = today_detection - first_signal``.

ASSUMPTION (the brief does not define today's detection date per type):

- Ageing-rule findings (pulse_missing_payment): today's process sees an unpaid accrual only
  when it turns overdue under the 365-day rule, i.e. accrual date + the account's
  Ageing Allowed (Days). Pension-type accounts ("No Overdue") are never flagged: None.
- Posting errors (sentinel_*, typo, label_mismatch, pulse_spike): the month-end close review
  of the posting month, i.e. month end + ``Rules.close_review_days``. The badge reads
  "N days before the close review".
- Blind spots (pulse_gap, pulse_missing_batch, miner_cluster): today's process has no check
  that sees them: None.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.engines import month_end
from app.schemas import ExceptionRecord, Rules

AGEING_TYPES = {"pulse_missing_payment"}
CLOSE_REVIEW_TYPES = {
    "sentinel_outlier", "sentinel_two_currencies", "sentinel_currency_code", "sentinel_reversal",
    "typo", "label_mismatch", "pulse_spike",
}  # fmt: skip
BLIND_TYPES = {"pulse_gap", "pulse_missing_batch", "miner_cluster"}
BASIS_TEXT = {
    "ageing": "365-day ageing rule",
    "close_review": "month-end close review",
    "never": "not detected by today's process",
}


def allowed_age_by_account(lines: pd.DataFrame) -> dict[tuple[str, str, str], int | None]:
    """Most common Ageing Allowed (Days) per account; None for exempt (pension-type) accounts.

    Fixed assets sheets have no such column; they default to 365 (today's rule).
    """
    out: dict[tuple[str, str, str], int | None] = {}
    for key, group in lines.groupby(["erp", "entity", "account"], sort=False):
        values = group["allowed_age"]
        if group["workbook"].iloc[0] != "Payroll":
            out[key] = 365
        elif values.notna().sum() >= values.isna().sum():
            out[key] = int(values.dropna().mode().iloc[0])
        else:
            out[key] = None
    return out


def today_detection(
    record: ExceptionRecord, rules: Rules, allowed_age: int | None
) -> tuple[date | None, str]:
    """Return (today's detection date, basis) for one record."""
    if record.type in AGEING_TYPES:
        accrual = record.facts.get("accrual_date")
        if allowed_age is None or not isinstance(accrual, str):
            return None, "never"
        return date.fromisoformat(accrual) + timedelta(days=allowed_age), "ageing"
    if record.type in CLOSE_REVIEW_TYPES:
        posted = record.facts.get("posting_date")
        anchor = date.fromisoformat(posted) if isinstance(posted, str) else record.first_signal
        return month_end(anchor) + timedelta(days=rules.close_review_days), "close_review"
    return None, "never"


def apply_lead_time(
    records: list[ExceptionRecord], lines: pd.DataFrame, rules: Rules
) -> list[ExceptionRecord]:
    """Fill today_detection and lead_days, and record the basis in the facts."""
    ages = allowed_age_by_account(lines)
    out = []
    for record in records:
        allowed = ages.get((record.erp, record.entity, record.account), 365)
        detected, basis = today_detection(record, rules, allowed)
        lead = (detected - record.first_signal).days if detected is not None else None
        facts = {**record.facts, "today_detection_basis": BASIS_TEXT[basis]}
        if lead is not None:
            facts["lead_days"] = float(lead)
        out.append(
            record.model_copy(
                update={"today_detection": detected, "lead_days": lead, "facts": facts}
            )
        )
    return out
