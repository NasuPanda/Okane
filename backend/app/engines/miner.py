"""Recurring-Correction Miner (brief section 1 baselines; decided in #14, docs/ASSUMPTIONS.md A7).

A manual posting is a person-posted (USER_###) line with a document header text. Its
fingerprint is ERP, user (``Rules.miner_by_user``), account, document type and the header text,
lower-cased, with name placeholders replaced, "corr" spelled out and digits masked. Its score is
distinct entities x distinct posting months. A fingerprint reaches the Inbox when the score is
at least ``Rules.miner_min_score`` and it appears in at least ``Rules.miner_min_repeats``
months.

The card is a hypothesis, not a fact: the same posting typed by hand month after month may be
a correction whose root cause (an automated posting or a mapping) could be fixed once.
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd

from app.engines import doc_refs, is_person, make_record
from app.engines.pairs import find_pairs
from app.schemas import ExceptionRecord, Rules

NAMES = re.compile(r"NAME\d+", re.IGNORECASE)
CORR = re.compile(r"\bcorr\b\.?")
DIGITS = re.compile(r"\d+")
SPACES = re.compile(r"\s+")
HYPOTHESIS = (
    "This may be a correction made by hand every month. Check whether the automated posting "
    "or mapping can do it."
)


def fingerprint_text(text: object) -> str:
    """Header text as a pattern: names replaced, lower-case, "corr" spelled out, digits masked."""
    if not isinstance(text, str):
        return ""
    shape = NAMES.sub("<name>", text).lower()
    shape = CORR.sub("correction", shape)
    shape = DIGITS.sub("#", shape)
    return SPACES.sub(" ", shape).strip()


def visible_from(group: pd.DataFrame, rules: Rules) -> date:
    """Posting date of the line that first lifts the pattern over both Inbox thresholds."""
    months: set[str] = set()
    entities: set[str] = set()
    ordered = group.sort_values(["posting_date", "line_id"])
    for posted, month, entity in zip(
        ordered["posting_date"], ordered["month"], ordered["entity"], strict=True
    ):
        months.add(month)
        entities.add(entity)
        if len(months) >= rules.miner_min_repeats and (
            len(months) * len(entities) >= rules.miner_min_score
        ):
            return posted
    return ordered["posting_date"].iloc[-1]


def run_miner(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """One miner_cluster record per repeated manual posting, highest score first."""
    # A7 (review of 22 Nov 2026): lines that cancel in an exact pair, anywhere on the account.
    pair_id = find_pairs(lines)
    paired = pair_id.notna()
    shapes = lines["header_text"].map(fingerprint_text)
    # A7 (review of PR #75): a line is reversed when its exact-pair partner carries the same
    # header text pattern, i.e. it is the reversal of the same posting. A manual line that
    # offsets a different posting (an automated accrual, say) is paired but not reversed.
    both = pd.DataFrame({"pair_id": pair_id, "shape": shapes})[paired]
    same_text = both.groupby("pair_id")["shape"].transform("nunique").eq(1) & both["shape"].ne("")
    reversed_ = same_text.reindex(lines.index, fill_value=False)
    manual = lines[lines["user_name"].map(is_person) & lines["posting_date"].notna()].copy()
    manual["paired"] = paired[manual.index]
    manual["reversed"] = reversed_[manual.index]
    manual["shape"] = shapes[manual.index]
    manual = manual[manual["shape"] != ""]
    if manual.empty:
        return []
    manual["month"] = manual["posting_date"].map(lambda d: f"{d.year:04d}-{d.month:02d}")
    keys = ["erp", "user_name", "account", "doc_type", "shape"]
    if not rules.miner_by_user:
        keys.remove("user_name")
    who = "one person" if rules.miner_by_user else "any person"
    found = []
    for _, group in manual.groupby(keys, sort=False, dropna=False):
        months = sorted(set(group["month"]))
        entities = sorted(set(group["entity"]))
        score = len(months) * len(entities)
        if len(months) < rules.miner_min_repeats or score < rules.miner_min_score:
            continue
        # ASSUMPTION (A7): a posting typed by hand and reversed with the same header text is a
        # routine (an accrual and its reversal), not a repeated correction; when at least
        # ``miner_max_paired_share`` of the pattern's lines are reversed that way, it is dropped.
        # A manual line that exactly offsets a different posting stays: that is the correction
        # the Miner exists to show (review of PR #75).
        if float(group["reversed"].mean()) >= rules.miner_max_paired_share:
            continue
        # The record sits on the lowest entity code in the pattern; the others are listed in
        # the facts. Line counts never choose it, so the id (which hashes this entity) stays
        # the same when a later extract shifts lines between entities (CLAUDE.md rule 10).
        # ASSUMPTION (A7): a pattern spanning entities is one record.
        primary = entities[0]
        group = pd.concat([group[group["entity"] == primary], group[group["entity"] != primary]])
        found.append((score, len(months), len(group), group, months, entities))
    found.sort(key=lambda item: (-item[0], -item[1], -item[2]))

    records = []
    for score, _, _, group, months, entities in found:
        head = group.iloc[0]
        doc_type = head["doc_type"] if isinstance(head["doc_type"], str) else ""
        shape = str(head["shape"])
        refs = doc_refs(group)
        id_keys = [doc_type, shape]
        if rules.miner_by_user:
            id_keys.append(str(head["user_name"]))
        records.append(
            make_record(
                type_="miner_cluster",
                lines=group,
                title=f"Repeated manual posting: {len(months)} months",
                # A7: the net of the lines that are not cancelled by an exact pair.
                exposure_eur=float(group.loc[~group["paired"], "amount_eur"].sum()),
                facts={
                    "rule": f"The same manual posting by {who} scores at least "
                    f"{rules.miner_min_score} (entities x months) in "
                    f"{rules.miner_min_repeats}+ months",
                    "fingerprint": f"{head['erp']} / account {head['account']} / document type "
                    f'{doc_type or "-"} / {who} / header text "{shape}"',
                    "pattern": shape,
                    "doc_type": doc_type,
                    "months": len(months),
                    "entities": len(entities),
                    "entity_list": ", ".join(entities),
                    "miner_score": score,
                    "first_month": months[0],
                    "last_month": months[-1],
                    "lines": len(group),
                    "documents": len(refs),
                    "people": group["user_name"].nunique(),
                    "total_abs_eur": float(group["amount_eur"].abs().sum()),
                    "paired_lines": int(group["paired"].sum()),
                    "unpaired_net_eur": float(group.loc[~group["paired"], "amount_eur"].sum()),
                    "hint": HYPOTHESIS,
                },
                evidence=refs,
                first_signal=visible_from(group, rules),
                id_keys=id_keys,
            )
        )
    return records
