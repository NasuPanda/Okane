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

from app.schemas import ExceptionClass, ExceptionRecord, ExceptionType

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
