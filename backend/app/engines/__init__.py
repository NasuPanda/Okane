"""Analysis engines (brief section 8).

Every engine is a pure function: it takes the snapshot's lines (a DataFrame in the common
model), the ``Rules`` and, where needed, the analysis date, and returns ``ExceptionRecord``s or
a plain result object. No engine reads files, the database or the clock.

This module holds the helpers the engines share.
"""

from __future__ import annotations

import calendar
import hashlib
from collections.abc import Iterable
from datetime import date
from typing import Any

import pandas as pd

from app.schemas import ExceptionClass, ExceptionRecord, ExceptionType, Rules

PENDING_RUN = ""


def stable_id(type_: str, erp: str, entity: str, account: str, keys: Iterable[str] = ()) -> str:
    """Hash of type, ERP, entity, account and key documents (brief section 7).

    Stable across runs, so a person's decision on an exception survives the next run.
    """
    raw = "|".join([type_, erp, entity, account, *sorted(set(keys))])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def doc_ref(year: object, document_no: object) -> str:
    """Document reference ``DocumentNo/Year``: SAP reuses numbers across fiscal years."""
    year_text = "" if year is None or pd.isna(year) else str(int(year))  # type: ignore[arg-type]
    return f"{document_no}/{year_text}"


def doc_refs(frame: pd.DataFrame) -> list[str]:
    """Unique document references of some lines, in posting order."""
    ordered = frame.sort_values(["posting_date", "line_id"])
    seen: dict[str, None] = {}
    for year, number in zip(ordered["year"], ordered["document_no"], strict=True):
        seen.setdefault(doc_ref(year, number), None)
    return list(seen)


def month_end(day: date) -> date:
    """Last calendar day of the month of ``day``."""
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def period_end(year: int, month: int) -> date:
    return month_end(date(year, month, 1))


def period_label(year: int, month: int) -> str:
    """'2026-09' style label used in facts and timelines."""
    return f"{year:04d}-{month:02d}"


def short_money(value: float) -> str:
    """Compact amount for titles: 1838462 -> '1.84M', 513823 -> '514K'."""
    size = abs(value)
    if size >= 1_000_000:
        return f"{size / 1_000_000:.2f}M"
    if size >= 1_000:
        return f"{size / 1_000:.0f}K"
    return f"{size:.0f}"


def normal_side(rules: Rules, erp: str, account: str) -> str:
    """The side the account's balance normally sits on: "debit", "credit" or "unknown" (A43).

    The ``Rules.account_normal_side`` entry with the longest matching account prefix wins.
    """
    best: tuple[int, str] = (0, "unknown")
    for entry in rules.account_normal_side:
        prefix = entry.account_prefix
        if entry.erp == erp and account.startswith(prefix) and len(prefix) > best[0]:
            best = (len(prefix), entry.side)
    return best[1]


def balance_side(amount: float) -> str:
    """Positive amounts are debits, negative are credits (brief section 6)."""
    return "debit" if amount > 0 else "credit"


# What a gap means, by the account's normal side and the gap's direction (A43). The direction
# is where the balance sits compared with what the payment rhythm leaves: "debit" when
# balance - expected > 0 (more paid or debited), "credit" otherwise.
GAP_WORDING: dict[tuple[str, str], dict[str, str]] = {
    ("credit", "credit"): {
        "noun": "Liability", "headline": "above expected", "meaning": "",
        "explained": "The liability is above the level its payment rhythm leaves: more was "
        "accrued than paid.",
        "check": "the unmatched accrual batches listed as evidence",
    },
    ("credit", "debit"): {
        "noun": "Liability", "headline": "below expected", "meaning": "more paid than accrued",
        "explained": "The liability is below the level its payment rhythm leaves: more was paid "
        "than accrued.",
        "check": "missing or late accruals, payments booked to this account by mistake, and "
        "whether a refund is due",
    },
    ("debit", "debit"): {
        "noun": "Asset", "headline": "above expected", "meaning": "",
        "explained": "The asset is above the level its rhythm leaves: more was booked than "
        "used up or settled.",
        "check": "the open debits that were not used up or settled",
    },
    ("debit", "credit"): {
        "noun": "Asset", "headline": "below expected", "meaning": "more used up than booked",
        "explained": "The asset is below the level its rhythm leaves: more was used up or "
        "settled than booked.",
        "check": "missing debits, credits booked to this account by mistake, and whether an "
        "amount is owed back",
    },
    ("unknown", "debit"): {
        "noun": "Balance", "headline": "more debit than expected", "meaning": "",
        "explained": "The balance sits further on the debit side than its rhythm leaves.",
        "check": "the evidence documents and the batches behind the gap",
    },
    ("unknown", "credit"): {
        "noun": "Balance", "headline": "more credit than expected", "meaning": "",
        "explained": "The balance sits further on the credit side than its rhythm leaves.",
        "check": "the evidence documents and the batches behind the gap",
    },
}  # fmt: skip


def gap_wording(gap: float, balance: float, side: str) -> dict[str, str]:
    """Title and plain-language facts for a gap, by direction and normal side (A43)."""
    direction = "debit" if gap > 0 else "credit"
    words = GAP_WORDING[(side, direction)]
    title = f"{words['noun']} {short_money(gap)} {words['headline']}"
    if words["meaning"]:
        title += f": {words['meaning']}"
    held = balance_side(balance)
    wrong = side in ("debit", "credit") and held != side and balance != 0
    explained = words["explained"]
    if wrong:
        explained += f" The account has a {held} balance, the wrong side for a {side} account."
    return {
        "title": title,
        "normal_side": side,
        "gap_direction": f"toward {direction}",
        "balance_side": held,
        "wrong_side_balance": "yes" if wrong else "no",
        "gap_explained": explained,
        "check": words["check"],
    }


def is_person(user: object) -> bool:
    """``USER_###`` are people; ``BOT_*`` are automated postings (brief section 6)."""
    return isinstance(user, str) and user.upper().startswith("USER")


def account_lines(lines: pd.DataFrame, erp: str, entity: str, account: str) -> pd.DataFrame:
    return lines[
        (lines["erp"] == erp) & (lines["entity"] == entity) & (lines["account"] == account)
    ]


def first_value(frame: pd.DataFrame, column: str) -> str:
    values = frame[column].dropna()
    return str(values.iloc[0]) if len(values) else ""


def make_record(
    *,
    type_: ExceptionType,
    lines: pd.DataFrame,
    title: str,
    exposure_eur: float,
    facts: dict[str, Any],
    evidence: list[str],
    first_signal: date,
    id_keys: Iterable[str],
    expected_by: date | None = None,
    suggested_class: ExceptionClass | None = None,
) -> ExceptionRecord:
    """Build a record from the lines it is about. Lead time and score are filled in later."""
    head = lines.iloc[0]
    erp, entity, account = str(head["erp"]), str(head["entity"]), str(head["account"])
    clean_facts: dict[str, float | str] = {}
    for key, value in facts.items():
        if value is None:
            continue
        if isinstance(value, date):
            clean_facts[key] = value.isoformat()
        elif isinstance(value, bool):
            clean_facts[key] = "yes" if value else "no"
        elif isinstance(value, int | float):
            clean_facts[key] = round(float(value), 2)
        else:
            clean_facts[key] = str(value)
    return ExceptionRecord(
        id=stable_id(type_, erp, entity, account, id_keys),
        run_id=PENDING_RUN,
        type=type_,
        workgroup=head["workbook"],
        erp=erp,  # type: ignore[arg-type]
        entity=entity,
        account=account,
        account_name=first_value(lines, "account_name"),
        title=title,
        exposure_eur=round(float(exposure_eur), 2),
        facts=clean_facts,
        evidence=evidence,
        first_signal=first_signal,
        today_detection=None,
        lead_days=None,
        expected_by=expected_by,
        suggested_class=suggested_class,
        score=0.0,
        score_breakdown={},
        ai_comment=None,
        verifier="not_run",
        status="new",
        decision_reason=None,
    )
