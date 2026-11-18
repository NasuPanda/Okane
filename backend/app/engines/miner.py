"""Recurring-Correction Miner (brief section 1 baselines; section 9, "CC06").

ASSUMPTION (no spec; the CC06 definition is unknown): a manual correction is a line posted by
a person (USER_###). Its fingerprint is ERP, entity, account, document type and the text with
name placeholders and digits removed. A fingerprint seen in at least ``miner_min_repeats``
different posting months is a recurring correction: someone fixes the same thing by hand every
month, so the root cause (usually the automated posting it corrects) should be fixed once.
"""

from __future__ import annotations

import re

import pandas as pd

from app.engines import doc_refs, is_person, make_record
from app.schemas import ExceptionRecord, Rules

DIGITS = re.compile(r"\d+")
NAMES = re.compile(r"NAME\d+", re.IGNORECASE)
SPACES = re.compile(r"\s+")


def fingerprint_text(text: object) -> str:
    """Text with names and digits replaced, lower-case: the shape of the correction."""
    if not isinstance(text, str):
        return ""
    shape = NAMES.sub("<name>", text)
    shape = DIGITS.sub("#", shape)
    return SPACES.sub(" ", shape).strip().lower()


def run_miner(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """One miner_cluster record per recurring manual correction."""
    min_repeats = rules.miner_min_repeats
    manual = lines[lines["user_name"].map(is_person)].copy()
    manual["shape"] = manual["text"].map(fingerprint_text)
    manual = manual[manual["shape"] != ""]
    manual["month"] = manual["posting_date"].map(lambda d: f"{d.year:04d}-{d.month:02d}")
    records = []
    keys = ["erp", "entity", "account", "doc_type", "shape"]
    for (_, _, _, doc_type, shape), group in manual.groupby(keys, sort=False, dropna=False):
        months = sorted(set(group["month"]))
        if len(months) < min_repeats:
            continue
        refs = doc_refs(group)
        # the posting that made the pattern visible: first line of the min_repeats-th month
        signal_month = months[min_repeats - 1]
        first_signal = min(group[group["month"] == signal_month]["posting_date"])
        users = sorted(set(group["user_name"]))
        records.append(
            make_record(
                type_="miner_cluster",
                lines=group,
                title=f"Same manual correction repeated in {len(months)} months",
                exposure_eur=float(group["amount_eur"].sum()),
                facts={
                    "rule": f"Manual correction with the same shape in {min_repeats}+ months",
                    "pattern": shape,
                    "doc_type": doc_type if isinstance(doc_type, str) else "",
                    "months": len(months),
                    "first_month": months[0],
                    "last_month": months[-1],
                    "lines": len(group),
                    "documents": len(refs),
                    "people": len(users),
                    "total_abs_eur": float(group["amount_eur"].abs().sum()),
                    "hint": "The same fix is made by hand every month. Check the automated "
                    "posting or mapping it corrects and fix it once at the source.",
                },
                evidence=refs,
                first_signal=first_signal,
                id_keys=[str(doc_type), shape],
            )
        )
    return records
