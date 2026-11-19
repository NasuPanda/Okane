"""Detection lead time (brief section 1, feature 2; decided in #16, docs/ASSUMPTIONS.md A8).

For every finding: ``first_signal`` (set by the engine: when Okane can first flag it),
``today_detection`` (when today's process would flag it; None = never) and ``lead_days``.

Today's detection date, per type:

- Ageing-rule findings (pulse_missing_payment): accrual date + the account's Ageing Allowed
  (Days), the day the ageing rule would first show it. Pension-type accounts ("No Overdue")
  are never flagged: None.
- Posting errors (sentinel_*, typo, label_mismatch, pulse_spike): the close review on the
  ``Rules.close_review_working_day`` working day after the end of the posting month. Working
  days are Monday to Friday minus ``Rules.close_review_holidays``.
- Blind spots (pulse_gap, pulse_missing_batch, miner_cluster): today's process has no check
  that sees them: None.

Okane runs weekly, so with ``Rules.lead_time_view`` = "weekly" the lead days count from the run
on or after the first signal (``Rules.weekly_run_weekday``); "daily" counts from the first
signal itself. Both figures are kept in the facts. Nothing here reads the clock.
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


def nth_working_day_after(
    day: date, n: int, holidays: set[date] | frozenset[date] = frozenset()
) -> date:
    """The n-th Monday-to-Friday day after ``day`` that is not a holiday (n >= 1)."""
    current, counted = day, 0
    while counted < max(n, 1):
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holidays:
            counted += 1
    return current


def close_review_date(posted: date, rules: Rules) -> date:
    """Today's close review of the month ``posted`` falls in (A8)."""
    return nth_working_day_after(
        month_end(posted), rules.close_review_working_day, set(rules.close_review_holidays)
    )


def next_run_on_or_after(day: date, weekday: int) -> date:
    """The weekly run on or after ``day`` (weekday 0 = Monday)."""
    return day + timedelta(days=(weekday - day.weekday()) % 7)


def badge_text(lead: int | None, basis: str, allowed_age: int | None) -> str:
    """The lead-time badge, in accountant language."""
    if lead is None:
        return "Today's process would miss this"
    what = (
        f"the {allowed_age}-day ageing rule"
        if basis == "ageing" and allowed_age is not None
        else "the close review"
    )
    days = f"{abs(lead)} day{'' if abs(lead) == 1 else 's'}"
    return f"Caught {days} before {what}" if lead >= 0 else f"Seen {days} after {what}"


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
        return close_review_date(anchor, rules), "close_review"
    return None, "never"


def apply_lead_time(
    records: list[ExceptionRecord], lines: pd.DataFrame, rules: Rules
) -> list[ExceptionRecord]:
    """Fill today_detection and lead_days, and record the basis, both figures and the badge."""
    ages = allowed_age_by_account(lines)
    out = []
    for record in records:
        allowed = ages.get((record.erp, record.entity, record.account), 365)
        detected, basis = today_detection(record, rules, allowed)
        run = next_run_on_or_after(record.first_signal, rules.weekly_run_weekday)
        facts = {**record.facts, "today_detection_basis": BASIS_TEXT[basis]}
        lead = None
        if detected is not None:
            daily = (detected - record.first_signal).days
            weekly = (detected - run).days
            lead = weekly if rules.lead_time_view == "weekly" else daily
            facts.update(
                {
                    "lead_days": float(lead),
                    "lead_days_daily": float(daily),
                    "lead_days_weekly": float(weekly),
                    "okane_run_date": run.isoformat(),
                    "lead_view": rules.lead_time_view,
                }
            )
        facts["lead_badge"] = badge_text(lead, basis, allowed)
        out.append(
            record.model_copy(
                update={"today_detection": detected, "lead_days": lead, "facts": facts}
            )
        )
    return out
