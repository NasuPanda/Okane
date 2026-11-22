"""Payroll netting and risk scores (brief section 8, "Payroll netting"; section 9, risk score).

Netting rule: take Payroll lines with Overdue Amount ABS above 0 (what today's 365-day report
calls overdue). Group by ERP, CoCd and Account: count, sum of Overdue Amount ABS, sum of signed
EUR. A group whose |net| is at or above materiality is a real exposure. The old-rule totals
(lines and absolute amount) are returned next to it so the UI can show "old report versus real
exposure".

Expected (real data): 5,475 lines; 145.67M absolute; net -5.69M; 4 groups at 500K, 7 at 100K.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.engines import normal_side
from app.engines.pairs import find_pairs
from app.schemas import (
    ExceptionRecord,
    ExposureGroup,
    FixedAssetExposure,
    FixedAssetGroup,
    InboxView,
    Rules,
)


@dataclass
class NettingResult:
    old_rule_lines: int
    old_rule_overdue_abs: float
    net_eur: float
    groups: list[ExposureGroup]

    def groups_above(self) -> int:
        return sum(g.above_materiality for g in self.groups)


def payroll_netting(
    lines: pd.DataFrame, materiality_eur: float, rules: Rules | None = None
) -> NettingResult:
    """Net the overdue Payroll lines per account and flag groups at or above materiality.

    Each group carries its account's normal side from ``rules`` (A43; default Rules if None).
    """
    rules = rules or Rules()
    payroll = lines[lines["workbook"] == "Payroll"].copy()
    payroll["pair_id"] = find_pairs(payroll)
    overdue = payroll[payroll["overdue_abs"].fillna(0) > 0]
    grouped = (
        overdue.groupby(["erp", "entity", "account"], sort=False)
        .agg(
            account_name=("account_name", "first"),
            lines=("line_id", "size"),
            overdue_abs=("overdue_abs", "sum"),
            net_eur=("amount_eur", "sum"),
            paired_lines=("pair_id", "count"),
        )
        .reset_index()
    )
    grouped["abs_net"] = grouped["net_eur"].abs()
    grouped = grouped.sort_values(["abs_net", "account"], ascending=[False, True])
    groups = [
        ExposureGroup(
            erp=row.erp,
            entity=row.entity,
            account=row.account,
            account_name=row.account_name if isinstance(row.account_name, str) else None,
            lines=int(row.lines),
            overdue_abs=round(float(row.overdue_abs), 2),
            net_eur=round(float(row.net_eur), 2),
            paired_lines=int(row.paired_lines),
            above_materiality=bool(row.abs_net >= materiality_eur),
            normal_side=normal_side(rules, str(row.erp), str(row.account)),
        )
        for row in grouped.itertuples()
    ]
    return NettingResult(
        old_rule_lines=len(overdue),
        old_rule_overdue_abs=round(float(overdue["overdue_abs"].sum()), 2),
        net_eur=round(float(overdue["amount_eur"].sum()), 2),
        groups=groups,
    )


# ----- Fixed assets (A47) -----------------------------------------------------------------
def fixed_asset_exposure(
    lines: pd.DataFrame, rules: Rules, extract_date: date | None, run_id: str = ""
) -> FixedAssetExposure:
    """What is really open in Fixed assets after exact pairing, per ERP, entity and account.

    Lines with an amount of 0 in document currency (FX valuations) are never paired. Unpaired
    lines posted within ``Rules.fa_recent_days`` of the extract are this month's accruals; older
    unpaired lines never matched. Reuses ``find_pairs``; no other matching.
    """
    fixed = lines[lines["workbook"] == "Fixed assets"].copy()
    if fixed.empty:
        return FixedAssetExposure(
            run_id=run_id, extract_date=extract_date, recent_days=rules.fa_recent_days,
            lines=0, zero_amount_lines=0, paired_lines=0, recent_lines=0, older_lines=0,
            net_eur=0.0, groups=[],
        )  # fmt: skip
    fixed["paired"] = find_pairs(fixed).notna()
    fixed["zero"] = fixed["amount_dc"] == 0
    cutoff = (extract_date or max(fixed["posting_date"].dropna())) - pd.Timedelta(
        days=rules.fa_recent_days
    )
    posted = fixed["posting_date"]
    fixed["recent"] = posted.notna() & posted.map(lambda d: d is not None and d >= cutoff)
    open_ = ~fixed["paired"] & ~fixed["zero"]
    fixed["recent_open"] = open_ & fixed["recent"]
    fixed["older_open"] = open_ & ~fixed["recent"]
    # FX valuations and exact pairs cancel in document currency, not always in local currency
    # or EUR; what they leave is shown as exchange differences, so the parts add up to the net.
    fixed["fx"] = ~open_

    def total(frame: pd.DataFrame, column: str, mask: str | None = None) -> float:
        part = frame[frame[mask]] if mask else frame
        return round(float(part[column].sum()), 2)

    groups = []
    keys = ["erp", "entity", "account", "currency_lc"]
    for (erp, entity, account, currency), group in fixed.groupby(keys, sort=True):
        names = group["account_name"].dropna()
        groups.append(
            FixedAssetGroup(
                erp=erp,
                entity=entity,
                account=account,
                account_name=str(names.iloc[0]) if len(names) else None,
                currency_lc=currency,
                lines=len(group),
                zero_amount_lines=int(group["zero"].sum()),
                paired_lines=int(group["paired"].sum()),
                recent_lines=int(group["recent_open"].sum()),
                recent_net_lc=total(group, "amount_lc", "recent_open"),
                recent_net_eur=total(group, "amount_eur", "recent_open"),
                older_lines=int(group["older_open"].sum()),
                older_net_lc=total(group, "amount_lc", "older_open"),
                older_net_eur=total(group, "amount_eur", "older_open"),
                fx_net_lc=total(group, "amount_lc", "fx"),
                fx_net_eur=total(group, "amount_eur", "fx"),
                net_lc=total(group, "amount_lc"),
                net_eur=total(group, "amount_eur"),
                estimated_rate=currency in rules.unconfirmed_rate_currencies,
            )
        )
    return FixedAssetExposure(
        run_id=run_id,
        extract_date=extract_date,
        recent_days=rules.fa_recent_days,
        lines=len(fixed),
        zero_amount_lines=int(fixed["zero"].sum()),
        paired_lines=int(fixed["paired"].sum()),
        recent_lines=int(fixed["recent_open"].sum()),
        older_lines=int(fixed["older_open"].sum()),
        net_eur=round(float(fixed["amount_eur"].sum()), 2),
        groups=groups,
    )


# ----- risk score ---------------------------------------------------------------------------
# Decided (#18, docs/ASSUMPTIONS.md A9): the brief gives the weights (exposure 40, days past
# expected 20, penalty account 20, error type 10, repeats 10). Each component is scaled to 0..1
# with parameters from Rules, multiplied by its weight, and summed (0..100).
def score_components(
    record: ExceptionRecord, rules: Rules, as_of: date, miner_months: int
) -> dict[str, float]:
    """Each component on a 0..1 scale (see docs/ASSUMPTIONS.md A9)."""
    cap = max(rules.exposure_cap_multiple * rules.materiality_eur, 1.0)
    exposure = min(abs(record.exposure_eur) / cap, 1.0)
    # A gap has no expected-by date; it counts from the month-end it first crossed materiality.
    due = record.first_signal if record.type == "pulse_gap" else record.expected_by
    days_past = 0.0
    if due is not None and as_of > due:
        days_past = min((as_of - due).days / max(rules.days_past_expected_cap, 1), 1)
    key = f"{record.erp}/{record.entity}/{record.account}"
    penalty = 1.0 if key in rules.penalty_accounts else 0.0
    error_type = float(rules.error_type_severity.get(record.type, 0.0))
    repeats = 1.0 if miner_months >= rules.repeats_min_months else 0.0
    return {
        "exposure": exposure,
        "days_past_expected": days_past,
        "penalty_account": penalty,
        "error_type": error_type,
        "repeats": repeats,
    }


def miner_months(records: list[ExceptionRecord]) -> dict[str, int]:
    """Months of the Miner pattern behind each record, read from the Miner's ``months`` fact.

    A Miner card has its own months. Any other finding takes the longest Miner pattern on the
    same ERP, account and company code (a pattern lists its company codes in ``entity_list``),
    or 0 when there is none (A9).
    """
    by_account: dict[tuple[str, str, str], int] = {}
    for r in records:
        if r.type != "miner_cluster":
            continue
        months = int(float(r.facts.get("months", 0)))
        for entity in str(r.facts.get("entity_list", r.entity)).split(", "):
            key = (r.erp, entity, r.account)
            by_account[key] = max(by_account.get(key, 0), months)
    return {
        r.id: int(float(r.facts.get("months", 0)))
        if r.type == "miner_cluster"
        else by_account.get((r.erp, r.entity, r.account), 0)
        for r in records
    }


def score_records(
    records: list[ExceptionRecord], rules: Rules, as_of: date
) -> list[ExceptionRecord]:
    """Fill ``score`` (0..100) and ``score_breakdown`` (points per weight) from Rules weights."""
    months = miner_months(records)
    scored = []
    for record in records:
        components = score_components(record, rules, as_of, months[record.id])
        breakdown = {
            name: round(rules.weights.get(name, 0) * value, 1) for name, value in components.items()
        }
        scored.append(
            record.model_copy(
                update={"score": round(sum(breakdown.values()), 1), "score_breakdown": breakdown}
            )
        )
    return sorted(scored, key=lambda r: (-r.score, r.id))


# ----- inbox views --------------------------------------------------------------------------
# Decided (#21, docs/ASSUMPTIONS.md A25): mistake prompts and repeated manual postings have
# their own inbox tabs; the default tab holds findings at or above materiality and the types in
# Rules.inbox_always_types.
PROMPT_TYPES = frozenset({"typo", "label_mismatch"})


def inbox_view(record: ExceptionRecord, rules: Rules) -> InboxView:
    """The inbox tab a finding sits on (A25)."""
    if record.type in PROMPT_TYPES:
        return "prompts"
    if record.type == "miner_cluster":
        return "repeats"
    if abs(record.exposure_eur) >= rules.materiality_eur or record.type in rules.inbox_always_types:
        return "attention"
    return "other"
