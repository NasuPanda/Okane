"""Account balances (review of 22 Nov 2026, fix 4; docs/ASSUMPTIONS.md A46).

Two findings about whole payroll accounts, next to Pulse (which covers only the profiled
accounts):

- ``open_balance``: a payroll netting group (overdue lines, brief section 8) at or above
  materiality on an account with no Pulse finding. It gives the Exposure page's "really open"
  accounts a finding to open. Today's ageing report already lists these lines one by one, so it
  is not a blind spot; Okane adds the net.
- ``wrong_side_balance``: the account's full balance (every open line, not only overdue ones)
  sits on the wrong side of its normal side (A43) by at least materiality: a liability in
  debit or an asset in credit. Where the account already has a Pulse gap, the wrong-side fact
  goes on the gap record instead of a second record.

Payroll only: Fixed assets accounts carry no ageing or netting, and A3 keeps them out of Pulse.
Pure functions: lines and Rules in, records out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.engines import (
    balance_side,
    doc_ref,
    make_record,
    normal_side,
    short_money,
)
from app.engines.exposure import payroll_netting
from app.schemas import ExceptionRecord, Rules

PULSE_TYPES = frozenset(
    {"pulse_gap", "pulse_missing_payment", "pulse_spike", "pulse_missing_batch", "label_mismatch"}
)
# ASSUMPTION (A46): the documents listed as evidence, those that move the balance most.
EVIDENCE_DOCS = 10

Key = tuple[str, str, str]


def _key(erp: object, entity: object, account: object) -> Key:
    return str(erp), str(entity), str(account)


def top_documents(frame: pd.DataFrame, sign: float, limit: int = EVIDENCE_DOCS) -> list[str]:
    """The documents whose lines move the balance furthest in the direction of ``sign``."""
    if frame.empty:
        return []
    refs = [doc_ref(y, n) for y, n in zip(frame["year"], frame["document_no"], strict=True)]
    sums = frame.assign(ref=refs).groupby("ref", sort=False)["amount_eur"].sum()
    sums = sums[sums * sign > 0]
    return list((sums * sign).sort_values(ascending=False).index[:limit])


def net_wording(side: str, net: float) -> str:
    """Title for an open net, by the account's normal side (A43)."""
    amount = short_money(net)
    held = balance_side(net)
    if side == "credit":
        return (
            f"Liability {amount} still owed after matching"
            if held == "credit"
            else f"Liability in debit: {amount} paid more than booked, after matching"
        )
    if side == "debit":
        return (
            f"Asset {amount} not yet used up after matching"
            if held == "debit"
            else f"Asset in credit: {amount} used up more than booked, after matching"
        )
    return f"Open {held} balance {amount} after matching"


def open_balance_alerts(
    lines: pd.DataFrame, rules: Rules, pulse_accounts: set[Key]
) -> list[ExceptionRecord]:
    """open_balance: a netting group at or above materiality with no Pulse finding."""
    payroll = lines[lines["workbook"] == "Payroll"].copy()
    if payroll.empty:
        return []
    overdue = payroll[payroll["overdue_abs"].fillna(0) > 0]
    netting = payroll_netting(lines, rules.materiality_eur, rules)
    records = []
    for group in netting.groups:
        key = _key(group.erp, group.entity, group.account)
        if not group.above_materiality or key in pulse_accounts:
            continue
        acct = overdue[
            (overdue["erp"] == group.erp)
            & (overdue["entity"] == group.entity)
            & (overdue["account"] == group.account)
        ]
        dated = acct[acct["posting_date"].notna()]
        # ASSUMPTION (A46): first signal = the day the newest of these lines turned overdue
        # (posting date + its own allowed age), when the ageing report first listed all of them.
        # Only lines with an allowed age count (the brief: never assume 365); when none has one,
        # the newest posting date is used.
        aged = dated[dated["allowed_age"].notna()]
        turned = [
            p + timedelta(days=int(a))
            for p, a in zip(aged["posting_date"], aged["allowed_age"], strict=True)
        ]
        if turned:
            first_signal = max(turned)
        elif len(dated):
            first_signal = max(dated["posting_date"])
        else:
            first_signal = date.min
        side = group.normal_side
        records.append(
            make_record(
                type_="open_balance",
                lines=acct,
                title=net_wording(side, group.net_eur),
                exposure_eur=group.net_eur,
                facts={
                    "rule": "Overdue lines of an account net to at least materiality, and no "
                    "payment-rhythm check covers the account",
                    "net_eur": group.net_eur,
                    "overdue_abs_eur": group.overdue_abs,
                    "lines": group.lines,
                    "paired_lines": group.paired_lines,
                    "debit_eur": float(acct.loc[acct["amount_eur"] > 0, "amount_eur"].sum()),
                    "credit_eur": float(acct.loc[acct["amount_eur"] < 0, "amount_eur"].sum()),
                    "normal_side": side,
                    "balance_side": balance_side(group.net_eur),
                    "oldest_posting_date": min(dated["posting_date"]) if len(dated) else None,
                    "newest_posting_date": max(dated["posting_date"]) if len(dated) else None,
                    "materiality_eur": rules.materiality_eur,
                },
                evidence=top_documents(acct, 1.0 if group.net_eur > 0 else -1.0),
                first_signal=first_signal,
                id_keys=[],
            )
        )
    return records


@dataclass
class WrongSide:
    """One account whose full balance sits on the wrong side by at least materiality."""

    key: Key
    lines: pd.DataFrame
    side: str
    balance: float
    crossed_on: date
    since: pd.DataFrame  # lines from the last crossing on


def wrong_side_accounts(lines: pd.DataFrame, rules: Rules) -> list[WrongSide]:
    """Payroll accounts whose full balance is on the wrong side by at least materiality."""
    payroll = lines[(lines["workbook"] == "Payroll") & lines["posting_date"].notna()]
    found = []
    for (erp, entity, account), acct in payroll.groupby(["erp", "entity", "account"], sort=False):
        side = normal_side(rules, str(erp), str(account))
        balance = float(acct["amount_eur"].sum())
        if side == "unknown" or abs(balance) < rules.materiality_eur:
            continue
        if balance_side(balance) == side or balance == 0:
            continue
        ordered = acct.sort_values(["posting_date", "line_id"])
        running = ordered["amount_eur"].cumsum().round(2)
        wrong = running > 0 if side == "credit" else running < 0
        # The line after which the running balance last moved to the wrong side.
        flips = wrong & ~wrong.shift(1, fill_value=False)
        start = int(flips.to_numpy().nonzero()[0][-1])
        found.append(
            WrongSide(
                key=_key(erp, entity, account),
                lines=acct,
                side=side,
                balance=round(balance, 2),
                crossed_on=ordered["posting_date"].iloc[start],
                since=ordered.iloc[start:],
            )
        )
    return found


def wrong_side_facts(found: WrongSide) -> dict[str, object]:
    held = balance_side(found.balance)
    return {
        "balance_eur": found.balance,
        "balance_abs_eur": abs(found.balance),
        "normal_side": found.side,
        "balance_side": held,
        "wrong_side_since": found.crossed_on,
    }


def wrong_side_alerts(
    found: list[WrongSide], rules: Rules, gap_accounts: set[Key]
) -> list[ExceptionRecord]:
    """wrong_side_balance for each account without a Pulse gap (the gap carries the fact)."""
    records = []
    for item in found:
        if item.key in gap_accounts:
            continue
        held = balance_side(item.balance)
        noun = "Liability" if item.side == "credit" else "Asset"
        sign = 1.0 if item.balance > 0 else -1.0
        records.append(
            make_record(
                type_="wrong_side_balance",
                lines=item.lines,
                title=f"{noun} in {held}: {short_money(item.balance)} on the wrong side",
                exposure_eur=item.balance,
                facts={
                    "rule": f"The account's full balance is on the wrong side of its normal "
                    f"({item.side}) side by at least materiality",
                    **wrong_side_facts(item),
                    "lines": len(item.lines),
                    "posting_date": item.crossed_on,
                    "materiality_eur": rules.materiality_eur,
                    "prompt": f"You may have made a mistake: this {item.side} account holds a "
                    f"{held} balance since {item.crossed_on:%d %b %Y}.",
                },
                evidence=top_documents(item.since, sign),
                first_signal=item.crossed_on,
                id_keys=[],
                suggested_class="Required Adjustment Item",
            )
        )
    return records


def run_balances(
    lines: pd.DataFrame, rules: Rules, pulse_records: list[ExceptionRecord]
) -> tuple[list[ExceptionRecord], list[ExceptionRecord]]:
    """Return (Pulse records, with wrong-side facts on their gaps; new balance records)."""
    pulse_accounts = {
        _key(r.erp, r.entity, r.account) for r in pulse_records if r.type in PULSE_TYPES
    }
    gap_accounts = {
        _key(r.erp, r.entity, r.account) for r in pulse_records if r.type == "pulse_gap"
    }
    found = wrong_side_accounts(lines, rules)
    by_key = {item.key: item for item in found}
    updated = []
    for record in pulse_records:
        item = by_key.get(_key(record.erp, record.entity, record.account))
        if record.type == "pulse_gap" and item is not None:
            facts = {**record.facts, "wrong_side_since": item.crossed_on.isoformat()}
            record = record.model_copy(update={"facts": facts})
        updated.append(record)
    new = open_balance_alerts(lines, rules, pulse_accounts)
    new += wrong_side_alerts(found, rules, gap_accounts)
    return updated, new
