"""Payroll Liability Pulse (brief section 8, "Pulse").

For each account with a payment profile in ``Rules``:

1. Batches: credit lines whose Text matches the profile pattern (optionally filtered by user
   and document type), summed per period or per document; batches below the profile minimum
   are ignored.
2. Payment units: debit documents (their debit lines summed) or single debit lines, optionally
   filtered by document type, above the profile minimum.
3. Matching: for each batch in date order, try combinations of unused payment units inside
   the window and keep the best one within tolerance; record the lag in days.
4. Gap timeline: month-end balance = running sum of open items by posting month; expected
   balance = minus that month's batch (0 if none); gap = balance - expected.
5. Alerts: pulse_gap, pulse_missing_payment, pulse_spike, pulse_missing_batch, label_mismatch.

Expected (real data, C192 P20 279006): 21 batches matched, lag median 30 and 90th percentile
37, September 2026 batch expected by 21 Nov 2026, gap 1,838,462.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.engines import (
    account_lines,
    doc_ref,
    doc_refs,
    make_record,
    month_end,
    period_end,
    period_label,
    short_money,
)
from app.schemas import (
    BatchMatch,
    ExceptionRecord,
    PaymentProfile,
    PulseTimeline,
    Rules,
    TimelinePoint,
)

# ----- period parser ------------------------------------------------------------------------
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH_WORD = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)"), "ym"),  # Payroll202609
    (re.compile(_MONTH_WORD + r"[\s']*(20\d{2})(?!\d)", re.IGNORECASE), "word"),  # Jan'2025
    (re.compile(r"(?<![\d.])(0[1-9]|1[0-2])[/.](20\d{2})(?!\d)"), "my"),  # 03/2026, 07.2025
    (re.compile(r"\bP(0[1-9]|1[0-2])\s+(20\d{2})(?!\d)", re.IGNORECASE), "my"),  # P05 2021
]


def parse_period(text: object) -> tuple[int, int] | None:
    """Find a (year, month) period label in free text, or None.

    Handles "Payroll202609", "January2023", "Jan'2025", "Dec' 2025", "03/2026", "P05 2021"
    (brief section 8) and "07.2025" (the C242 batch text).
    """
    if not isinstance(text, str):
        return None
    for pattern, kind in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if kind == "ym":
            return int(match.group(1)), int(match.group(2))
        if kind == "word":
            return int(match.group(2)), _MONTHS[match.group(1)[:3].lower()]
        return int(match.group(2)), int(match.group(1))
    return None


# ----- batches and payment units ------------------------------------------------------------
@dataclass
class Batch:
    period: tuple[int, int] | None
    accrual_date: date
    amount: float  # signed (negative = credit)
    lines: pd.DataFrame

    @property
    def period_end(self) -> date | None:
        return period_end(*self.period) if self.period else None

    def anchor(self, profile: PaymentProfile) -> date:
        if profile.window_anchor == "period_end" and self.period_end is not None:
            return self.period_end
        return self.accrual_date

    def month(self) -> tuple[int, int]:
        return self.period or (self.accrual_date.year, self.accrual_date.month)


@dataclass
class PaymentUnit:
    key: str
    posting_date: date
    amount: float
    refs: list[str]
    label: str


def _period_from_batch_text(text: object, pattern: re.Pattern[str]) -> tuple[int, int] | None:
    if not isinstance(text, str):
        return None
    match = pattern.search(text)
    if match and "period" in match.groupdict():
        return parse_period(match.group("period").replace(".", "/"))
    return parse_period(text)


def extract_batches(acct: pd.DataFrame, profile: PaymentProfile) -> list[Batch]:
    """Credit lines matching the profile, grouped per period or per document."""
    pattern = re.compile(profile.batch_text_pattern)
    mask = (acct["amount_dc"] < 0) & acct["text"].map(
        lambda t: isinstance(t, str) and bool(pattern.search(t))
    )
    if profile.batch_users:
        mask &= acct["user_name"].isin(profile.batch_users)
    if profile.batch_doc_types:
        mask &= acct["doc_type"].isin(profile.batch_doc_types)
    credit = acct[mask].copy()
    credit["batch_period"] = credit["text"].map(lambda t: _period_from_batch_text(t, pattern))
    if profile.batch_group == "period":
        credit = credit[credit["batch_period"].notna()]
        keys = credit["batch_period"]
    else:
        keys = credit["year"].astype(str) + "/" + credit["document_no"]
    batches = []
    for _, group in credit.groupby(keys, sort=False):
        amount = float(group["amount_eur"].sum())
        if abs(amount) < profile.min_batch_eur:
            continue
        periods = group["batch_period"].dropna()
        batches.append(
            Batch(
                period=periods.iloc[0] if len(periods) else None,
                accrual_date=max(group["posting_date"]),
                amount=round(amount, 2),
                lines=group,
            )
        )
    return sorted(batches, key=lambda b: (b.month(), b.accrual_date))


def extract_payments(
    acct: pd.DataFrame, profile: PaymentProfile, batch_line_ids: set[int]
) -> list[PaymentUnit]:
    """Debit documents (summed) or debit lines that may settle a batch."""
    debit = acct[(acct["amount_dc"] > 0) & ~acct["line_id"].isin(batch_line_ids)]
    if profile.payment_doc_types:
        debit = debit[debit["doc_type"].isin(profile.payment_doc_types)]
    units: list[PaymentUnit] = []
    if profile.payment_unit == "document":
        grouped = debit.groupby(["year", "document_no"], sort=False)
        for (year, number), group in grouped:
            units.append(
                PaymentUnit(
                    key=doc_ref(year, number),
                    posting_date=max(group["posting_date"]),
                    amount=round(float(group["amount_eur"].sum()), 2),
                    refs=[doc_ref(year, number)],
                    label=str(group["text"].dropna().iloc[0])
                    if group["text"].notna().any()
                    else "",
                )
            )
    else:
        for row in debit.itertuples():
            units.append(
                PaymentUnit(
                    key=f"{doc_ref(row.year, row.document_no)}#{row.item}",
                    posting_date=row.posting_date,
                    amount=round(float(row.amount_eur), 2),
                    refs=[doc_ref(row.year, row.document_no)],
                    label=row.text if isinstance(row.text, str) else "",
                )
            )
    units = [u for u in units if u.amount >= profile.min_payment_eur]
    return sorted(units, key=lambda u: (u.posting_date, u.key))


def _first_text(group: pd.DataFrame) -> str:
    texts = group["text"].dropna()
    return str(texts.iloc[0]) if len(texts) else ""


# ----- matching -----------------------------------------------------------------------------
@dataclass
class Match:
    batch: Batch
    units: list[PaymentUnit] = field(default_factory=list)
    diff: float = 0.0
    lag: int = 0

    @property
    def matched(self) -> bool:
        return bool(self.units)


def match_batches(
    batches: list[Batch], units: list[PaymentUnit], profile: PaymentProfile, rules: Rules
) -> list[Match]:
    """Greedy matching in batch date order (brief section 8, "Matching").

    For each batch, combinations of unused units inside the window are tried; the one with the
    smallest difference within tolerance, then the shortest lag, wins.
    """
    # ASSUMPTION: profiles with prefer_fewest_units rank (units, difference, lag) instead of
    # the brief's (difference, lag). On the real C192 data the literal rule gives a p90 lag of
    # 59 instead of the brief's 37; the C242 Expected values need the literal rule.
    # Confirmed in #4 (docs/ASSUMPTIONS.md A12), over a single lag-first rule.
    used: set[str] = set()
    results: list[Match] = []
    for batch in batches:
        anchor = batch.anchor(profile)
        start = anchor + timedelta(days=profile.window_start_days)
        end = anchor + timedelta(days=profile.window_end_days)
        candidates = [u for u in units if u.key not in used and start <= u.posting_date <= end]
        target = abs(batch.amount)
        tolerance = max(profile.tolerance_pct * target, rules.tolerance_eur)
        best: tuple[tuple[int, float, int], tuple[PaymentUnit, ...]] | None = None
        for size in range(1, profile.max_units + 1):
            for combo in itertools.combinations(candidates, size):
                diff = round(abs(sum(u.amount for u in combo) - target), 2)
                if diff > tolerance:
                    continue
                lag = (max(u.posting_date for u in combo) - anchor).days
                key = (size if profile.prefer_fewest_units else 0, diff, lag)
                if best is None or key < best[0]:
                    best = (key, combo)
            if best is not None and profile.prefer_fewest_units:
                break
        if best is None:
            results.append(Match(batch=batch))
            continue
        (_, diff, lag), combo = best
        used.update(u.key for u in combo)
        results.append(Match(batch=batch, units=list(combo), diff=diff, lag=lag))
    return results


def lag_stats(matches: list[Match]) -> tuple[float | None, float | None]:
    """Median and 90th percentile of the payment lag over matched batches."""
    lags = [m.lag for m in matches if m.matched]
    if not lags:
        return None, None
    return float(np.median(lags)), float(np.percentile(lags, 90))


def expected_by(batch: Batch, profile: PaymentProfile, p90: float | None, rules: Rules) -> date:
    """Period end (or accrual date) + 90th-percentile lag + grace days."""
    lag = p90 if p90 is not None else float(profile.window_end_days)
    return batch.anchor(profile) + timedelta(days=round(lag) + rules.grace_days)


# ----- gap timeline -------------------------------------------------------------------------
def gap_timeline(acct: pd.DataFrame, matches: list[Match]) -> list[TimelinePoint]:
    """Month-end balance, expected balance (minus that month's batch) and gap."""
    month_keys = acct["posting_date"].map(lambda d: (d.year, d.month))
    monthly = acct.groupby(month_keys)["amount_eur"].sum().sort_index()
    if monthly.empty:
        return []
    by_month = {m.batch.month(): m for m in matches}
    first, last = monthly.index.min(), max(monthly.index.max(), *by_month.keys())
    points: list[TimelinePoint] = []
    balance = 0.0
    year, month = first
    while (year, month) <= last:
        balance += float(monthly.get((year, month), 0.0))
        match = by_month.get((year, month))
        expected = -abs(match.batch.amount) if match else 0.0
        points.append(
            TimelinePoint(
                month=period_label(year, month),
                balance=round(balance, 2),
                expected=round(expected, 2),
                gap=round(balance - expected, 2),
                batch_eur=match.batch.amount if match else None,
                batch_matched=match.matched if match else None,
            )
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return points


# ----- profile result and alerts ------------------------------------------------------------
@dataclass
class ProfileResult:
    profile: PaymentProfile
    acct: pd.DataFrame
    matches: list[Match]
    timeline: list[TimelinePoint]
    lag_median: float | None
    lag_p90: float | None

    def to_timeline(self) -> PulseTimeline:
        return PulseTimeline(
            erp=self.profile.erp,
            entity=self.profile.entity,
            account=self.profile.account,
            label=self.profile.label,
            points=self.timeline,
            batches=[_batch_match(m) for m in self.matches],
            lag_median=self.lag_median,
            lag_p90=self.lag_p90,
        )


def _batch_match(m: Match) -> BatchMatch:
    target = abs(m.batch.amount)
    paid = round(sum(u.amount for u in m.units), 2) if m.units else None
    return BatchMatch(
        period=period_label(*m.batch.period) if m.batch.period else None,
        accrual_date=m.batch.accrual_date,
        period_end=m.batch.period_end,
        batch_eur=m.batch.amount,
        lines=len(m.batch.lines),
        evidence=doc_refs(m.batch.lines),
        matched=m.matched,
        payment_eur=paid,
        payment_dates=[u.posting_date for u in m.units],
        payment_evidence=[r for u in m.units for r in u.refs],
        payment_labels=[u.label for u in m.units],
        diff_pct=round((paid - target) / target * 100, 2) if paid is not None and target else None,
        lag_days=m.lag if m.matched else None,
    )


def analyse_profile(lines: pd.DataFrame, profile: PaymentProfile, rules: Rules) -> ProfileResult:
    """Batches, payments, matching and gap timeline for one profiled account."""
    acct = account_lines(lines, profile.erp, profile.entity, profile.account)
    batches = extract_batches(acct, profile)
    batch_ids = {int(i) for b in batches for i in b.lines["line_id"]}
    units = extract_payments(acct, profile, batch_ids)
    matches = match_batches(batches, units, profile, rules)
    median, p90 = lag_stats(matches)
    return ProfileResult(profile, acct, matches, gap_timeline(acct, matches), median, p90)


def gap_alert(result: ProfileResult, rules: Rules) -> ExceptionRecord | None:
    """pulse_gap when the latest |gap| is at or above materiality."""
    points = result.timeline
    if not points or abs(points[-1].gap) < rules.materiality_eur:
        return None
    run_start = len(points) - 1
    while run_start > 0 and abs(points[run_start - 1].gap) >= rules.materiality_eur:
        run_start -= 1
    run = points[run_start:]
    lowest = min(run, key=lambda p: abs(p.gap))
    latest = points[-1]
    since = date.fromisoformat(run[0].month + "-01")
    open_batches = [m for m in result.matches if not m.matched]
    evidence = [r for m in open_batches for r in doc_refs(m.batch.lines)]
    direction = "above" if latest.gap > 0 else "below"
    return make_record(
        type_="pulse_gap",
        lines=result.acct,
        title=f"Liability {short_money(latest.gap)} {direction} expected",
        exposure_eur=latest.gap,
        facts={
            "rule": "Latest month-end gap at or above materiality",
            "gap_eur": latest.gap,
            "balance_eur": latest.balance,
            "expected_eur": latest.expected,
            "latest_month": latest.month,
            "since_month": run[0].month,
            "months_above_materiality": len(run),
            "lowest_gap_eur": lowest.gap,
            "lowest_gap_month": lowest.month,
            "materiality_eur": rules.materiality_eur,
            "unmatched_batches": len(open_batches),
        },
        evidence=evidence,
        first_signal=month_end(since),
        id_keys=[],
        suggested_class="Required Adjustment Item",
    )


def missing_payment_alerts(
    result: ProfileResult, rules: Rules, as_of: date
) -> list[ExceptionRecord]:
    """pulse_missing_payment for each batch unmatched after its expected-by date."""
    records = []
    for m in result.matches:
        if m.matched:
            continue
        due = expected_by(m.batch, result.profile, result.lag_p90, rules)
        if due >= as_of:
            continue
        refs = doc_refs(m.batch.lines)
        days_late = (as_of - due).days
        label = (
            period_label(*m.batch.period) if m.batch.period else m.batch.accrual_date.isoformat()
        )
        records.append(
            make_record(
                type_="pulse_missing_payment",
                lines=result.acct,
                title=f"No payment found for the {label} batch",
                exposure_eur=m.batch.amount,
                facts={
                    "rule": "Batch unmatched after period end + 90th-percentile lag + grace days",
                    "batch_eur": m.batch.amount,
                    "batch_period": label,
                    "batch_lines": len(m.batch.lines),
                    "accrual_date": m.batch.accrual_date,
                    "expected_by": due,
                    "lag_p90_days": result.lag_p90 if result.lag_p90 is not None else "n/a",
                    "grace_days": rules.grace_days,
                    "days_past_expected": days_late,
                },
                evidence=refs,
                first_signal=due + timedelta(days=1),
                expected_by=due,
                id_keys=refs,
                suggested_class="Timing item" if days_late <= 30 else "Required Adjustment Item",
            )
        )
    return records


def spike_alerts(result: ProfileResult, rules: Rules) -> list[ExceptionRecord]:
    """pulse_spike when a batch exceeds spike_multiple x the trailing-months median."""
    records = []
    matches = result.matches
    for i, m in enumerate(matches):
        y, mo = m.batch.month()
        window_start = (y * 12 + mo - 1) - rules.spike_lookback_months
        prior = [
            abs(p.batch.amount)
            for p in matches[:i]
            if window_start <= p.batch.month()[0] * 12 + p.batch.month()[1] - 1 < y * 12 + mo - 1
        ]
        if len(prior) < 3:
            continue
        median = float(np.median(prior))
        multiple = abs(m.batch.amount) / median if median else 0.0
        if multiple <= rules.spike_multiple:
            continue
        refs = doc_refs(m.batch.lines)
        label = period_label(y, mo)
        records.append(
            make_record(
                type_="pulse_spike",
                lines=result.acct,
                title=f"{label} batch is {multiple:.1f}x the usual size",
                exposure_eur=m.batch.amount,
                facts={
                    "rule": f"Batch above {rules.spike_multiple:g}x the trailing "
                    f"{rules.spike_lookback_months}-month median",
                    "batch_eur": m.batch.amount,
                    "batch_period": label,
                    "median_eur": median,
                    "multiple": round(multiple, 1),
                    "posting_date": m.batch.accrual_date,
                },
                evidence=refs,
                first_signal=m.batch.accrual_date,
                id_keys=refs,
            )
        )
    return records


def missing_batch_alerts(result: ProfileResult, rules: Rules) -> list[ExceptionRecord]:
    """pulse_missing_batch for a month without a batch inside the look-back window."""
    # ASSUMPTION: the brief says "when a month has no batch". Open-items extracts drop batches
    # that were fully cleared, so older months are only checked within
    # Rules.missing_batch_lookback_months of the latest batch. Confirmed in #4 (A14).
    if not result.matches:
        return []
    months = {m.batch.month() for m in result.matches}
    last = max(months)
    last_index = last[0] * 12 + last[1] - 1
    first_index = max(min(i[0] * 12 + i[1] - 1 for i in months),
                      last_index - rules.missing_batch_lookback_months + 1)  # fmt: skip
    typical = float(np.median([abs(m.batch.amount) for m in result.matches]))
    records = []
    for index in range(first_index, last_index + 1):
        year, month = divmod(index, 12)
        month += 1
        if (year, month) in months:
            continue
        label = period_label(year, month)
        records.append(
            make_record(
                type_="pulse_missing_batch",
                lines=result.acct,
                title=f"No batch posted for {label}",
                exposure_eur=0.0,
                facts={
                    "rule": "Month without a batch",
                    "missing_period": label,
                    "typical_batch_eur": typical,
                    "lookback_months": rules.missing_batch_lookback_months,
                },
                evidence=[],
                first_signal=period_end(year, month),
                id_keys=[label],
                suggested_class="Timing item",
            )
        )
    return records


def label_mismatch_alerts(result: ProfileResult) -> list[ExceptionRecord]:
    """label_mismatch when a payment's text period differs from the batch it settles."""
    records = []
    for m in result.matches:
        if not m.matched or m.batch.period is None:
            continue
        for unit in m.units:
            labelled = parse_period(unit.label)
            if labelled is None or labelled == m.batch.period:
                continue
            diff_pct = (unit.amount - abs(m.batch.amount)) / abs(m.batch.amount) * 100
            settles = period_label(*m.batch.period)
            refs = unit.refs + doc_refs(m.batch.lines)
            records.append(
                make_record(
                    type_="label_mismatch",
                    lines=result.acct,
                    title=f"Payment labelled {period_label(*labelled)} settles {settles}",
                    exposure_eur=unit.amount,
                    facts={
                        "rule": "Payment text period differs from the batch it settles",
                        "payment_eur": unit.amount,
                        "batch_eur": m.batch.amount,
                        "diff_pct": round(diff_pct, 2),
                        "label_period": period_label(*labelled),
                        "settles_period": settles,
                        "posting_date": unit.posting_date,
                        "prompt": "You may have made a mistake: the payment text names "
                        f"{period_label(*labelled)}, but the amount settles the {settles} batch.",
                    },
                    evidence=refs,
                    first_signal=unit.posting_date,
                    id_keys=unit.refs,
                    suggested_class="Timing item",
                )
            )
    return records


@dataclass
class PulseResult:
    profiles: dict[str, ProfileResult]
    records: list[ExceptionRecord]


def run_pulse(lines: pd.DataFrame, rules: Rules, as_of: date) -> PulseResult:
    """Run every payment profile in Rules and collect the five alert types."""
    profiles: dict[str, ProfileResult] = {}
    records: list[ExceptionRecord] = []
    for profile in rules.payment_profiles:
        result = analyse_profile(lines, profile, rules)
        if result.acct.empty:
            continue
        profiles[profile.key] = result
        gap = gap_alert(result, rules)
        if gap is not None:
            records.append(gap)
        records += missing_payment_alerts(result, rules, as_of)
        records += spike_alerts(result, rules)
        records += missing_batch_alerts(result, rules)
        records += label_mismatch_alerts(result)
    return PulseResult(profiles=profiles, records=records)
