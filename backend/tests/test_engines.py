"""Engine unit tests on small hand-built frames, plus synthetic end-to-end checks."""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import pytest

from app.engines import doc_ref, short_money, stable_id
from app.engines.exposure import payroll_netting, score_records
from app.engines.leadtime import apply_lead_time
from app.engines.miner import fingerprint_text, run_miner
from app.engines.pairs import find_pairs
from app.engines.pulse import (
    analyse_profile,
    gap_timeline,
    match_batches,
    months_before,
    parse_period,
    run_pulse,
)
from app.engines.sentinel import (
    ISO_CURRENCIES,
    REPLACED_BY_EURO,
    currency_code_alerts,
    outlier_hits,
    run_sentinel,
    two_currency_alerts,
)
from app.engines.typos import run_typos
from app.schemas import ExceptionRecord, PaymentProfile, Rules

AS_OF = date(2026, 11, 18)


def frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Lines in the common model with sensible defaults."""
    base: dict[str, object] = {
        "workbook": "Payroll", "erp": "P20", "sheet": "P20", "source_row": 2, "entity": "C192",
        "account": "279006", "account_name": "Social security", "document_no": "0000000001",
        "item": 1, "year": 2026, "period": 1, "doc_type": "P0", "posting_date": date(2026, 1, 31),
        "doc_date": date(2026, 1, 31), "amount_dc": -100.0, "currency_dc": "EUR",
        "amount_lc": -100.0, "currency_lc": "EUR", "amount_eur": -100.0, "eur_rate": 1.0,
        "partner": None, "user_name": "BOT_UPLOAD_001", "text": "", "header_text": None,
        "reference": None, "assignment": None, "age_days": 10, "allowed_age": 365,
        "overdue_abs": 0.0, "reversal": None,
    }  # fmt: skip
    out = []
    for i, row in enumerate(rows):
        line = {**base, **row, "line_id": i}
        if "amount_dc" in row and "amount_lc" not in row:
            line["amount_lc"] = line["amount_eur"] = row["amount_dc"]
        if "posting_date" in row:
            line["year"] = row["posting_date"].year  # type: ignore[attr-defined]
        out.append(line)
    return pd.DataFrame(out)


# ----- helpers ------------------------------------------------------------------------------
def test_stable_id_ignores_key_order_and_run() -> None:
    a = stable_id("typo", "P20", "C192", "279006", ["2", "1"])
    assert a == stable_id("typo", "P20", "C192", "279006", ["1", "2", "1"])
    assert a != stable_id("typo", "P20", "C192", "279007", ["1", "2"])


def test_doc_ref_keeps_leading_zeros() -> None:
    assert doc_ref(2024, "0012345678") == "0012345678/2024"


def test_short_money() -> None:
    assert short_money(1_838_462) == "1.84M"
    assert short_money(-513_823) == "514K"


# ----- pairs --------------------------------------------------------------------------------
def test_pairs_rank_by_posting_date_within_key() -> None:
    lines = frame([
        {"amount_dc": 50.0, "posting_date": date(2026, 1, 1)},
        {"amount_dc": -50.0, "posting_date": date(2026, 1, 5)},
        {"amount_dc": 50.0, "posting_date": date(2026, 2, 1)},
        {"amount_dc": -50.004, "posting_date": date(2026, 3, 1)},  # rounds to 50.00
        {"amount_dc": 50.0, "posting_date": date(2026, 4, 1)},  # third debit: no partner
        {"amount_dc": -50.0, "currency_dc": "USD", "posting_date": date(2026, 4, 2)},
        {"amount_dc": 0.0, "posting_date": date(2026, 4, 3)},
    ])  # fmt: skip
    pairs = find_pairs(lines)
    assert pairs.notna().tolist() == [True, True, True, True, False, False, False]
    assert pairs[0] == pairs[1] and pairs[2] == pairs[3] and pairs[0] != pairs[2]


# ----- netting ------------------------------------------------------------------------------
def test_netting_uses_overdue_lines_and_live_materiality() -> None:
    lines = frame([
        {"account": "A", "amount_dc": -600.0, "overdue_abs": 600.0},
        {"account": "A", "amount_dc": 50.0, "overdue_abs": 50.0},
        {"account": "B", "amount_dc": 200.0, "overdue_abs": 200.0},
        {"account": "B", "amount_dc": 9_999.0, "overdue_abs": 0.0},  # not overdue
        {"account": "C", "amount_dc": -900.0, "overdue_abs": 900.0, "workbook": "Fixed assets"},
    ])  # fmt: skip
    result = payroll_netting(lines, materiality_eur=500)
    assert result.old_rule_lines == 3
    assert result.old_rule_overdue_abs == 850.0
    assert result.net_eur == -350.0
    assert [(g.account, g.net_eur, g.above_materiality) for g in result.groups] == [
        ("A", -550.0, True), ("B", 200.0, False),
    ]  # fmt: skip
    assert payroll_netting(lines, materiality_eur=100).groups_above() == 2


@pytest.mark.parametrize(
    ("erp", "account", "side"),
    [
        ("P20", "279006", "credit"), ("P20", "179003", "debit"), ("BPP", "34900015", "credit"),
        ("BPP", "48900004", "credit"), ("BPP", "23900002", "debit"), ("BPP", "13900001", "debit"),
        ("P20", "119001", "debit"), ("P20", "999999", "unknown"),
    ],
)  # fmt: skip
def test_normal_side_by_prefix(erp: str, account: str, side: str) -> None:
    from app.engines import normal_side

    assert normal_side(Rules(), erp, account) == side


def test_normal_side_longest_prefix_wins() -> None:
    from app.engines import normal_side
    from app.schemas import NormalSide

    rules = Rules(
        account_normal_side=[
            NormalSide(erp="P20", account_prefix="2", side="credit"),
            NormalSide(erp="P20", account_prefix="279", side="debit"),
        ]
    )
    assert normal_side(rules, "P20", "279006") == "debit"
    assert normal_side(rules, "P20", "200001") == "credit"


@pytest.mark.parametrize(
    ("side", "gap", "balance", "title", "wrong"),
    [
        ("credit", -1_838_462, -2_000_000, "Liability 1.84M above expected", "no"),
        ("credit", 1_838_462, 1_324_638, "Liability 1.84M below expected: more paid than accrued",
         "yes"),
        ("credit", 600_000, -100_000, "Liability 600K below expected: more paid than accrued",
         "no"),
        ("debit", 700_000, 900_000, "Asset 700K above expected", "no"),
        ("debit", -700_000, -50_000, "Asset 700K below expected: more used up than booked", "yes"),
        ("unknown", 700_000, 900_000, "Balance 700K more debit than expected", "no"),
    ],
)  # fmt: skip
def test_gap_wording_by_direction_and_side(
    side: str, gap: float, balance: float, title: str, wrong: str
) -> None:
    from app.engines import gap_wording

    words = gap_wording(gap, balance, side)
    assert words["title"] == title
    assert words["wrong_side_balance"] == wrong
    assert words["gap_direction"] == ("toward debit" if gap > 0 else "toward credit")


def test_netting_groups_carry_normal_side() -> None:
    lines = frame([
        {"account": "279006", "amount_dc": 900.0, "overdue_abs": 900.0},
        {"account": "179003", "amount_dc": 900.0, "overdue_abs": 900.0},
    ])  # fmt: skip
    sides = {g.account: g.normal_side for g in payroll_netting(lines, 500).groups}
    assert sides == {"279006": "credit", "179003": "debit"}


def test_wrong_side_balance_first_signal_is_the_last_crossing() -> None:
    """A46: a liability (credit-normal) that went into debit, back to credit, then into debit
    again is flagged from the last crossing; one with a Pulse gap gets no second record."""
    from app.engines.balances import run_balances

    lines = frame([
        {"account": "279002", "amount_dc": 800.0, "posting_date": date(2026, 1, 10)},
        {"account": "279002", "amount_dc": -900.0, "posting_date": date(2026, 2, 10)},
        {"account": "279002", "amount_dc": 700.0, "posting_date": date(2026, 9, 15)},
        {"account": "279002", "amount_dc": 400.0, "posting_date": date(2026, 10, 1)},
        {"account": "179004", "amount_dc": 900.0, "posting_date": date(2026, 3, 1)},  # normal
    ])  # fmt: skip
    _, new = run_balances(lines, Rules(materiality_eur=500), [])
    [record] = [r for r in new if r.type == "wrong_side_balance"]
    assert (record.account, record.first_signal, record.exposure_eur) == (
        "279002", date(2026, 9, 15), 1_000.0)  # fmt: skip
    assert record.title == "Liability in debit: 1K on the wrong side"
    gap = _finding(type_="pulse_gap", account="279002")
    updated, new = run_balances(lines, Rules(materiality_eur=500), [gap])
    assert not [r for r in new if r.type == "wrong_side_balance"]
    assert updated[0].facts["wrong_side_since"] == "2026-09-15"


def test_open_balance_skips_accounts_pulse_covers() -> None:
    """A46: an open net on an account Pulse covers is explained by the Pulse finding."""
    from app.engines.balances import run_balances

    lines = frame([
        {"account": "279014", "amount_dc": -900.0, "overdue_abs": 900.0},
        {"account": "279006", "amount_dc": -900.0, "overdue_abs": 900.0},
    ])  # fmt: skip
    pulse = [_finding(type_="pulse_missing_batch", account="279006")]
    _, new = run_balances(lines, Rules(materiality_eur=500), pulse)
    opened = [r for r in new if r.type == "open_balance"]
    assert [(r.account, r.exposure_eur, r.title) for r in opened] == [
        ("279014", -900.0, "Liability 900 still owed after matching")]  # fmt: skip


def test_miner_drops_patterns_that_are_mostly_exact_pairs() -> None:
    """A7 (review of 22 Nov 2026): an accrual and its reversal typed by hand every month pair up
    line for line; the pattern is dropped. A one-sided pattern stays, its exposure the net of
    its unpaired lines."""
    from app.engines.miner import run_miner

    rows: list[dict[str, object]] = []
    for month in range(1, 7):
        for entity in ("C101", "C102"):
            for sign in (1, -1):  # the accrual and its reversal
                rows.append({"entity": entity, "account": "119001",
                             "amount_dc": sign * 1000.0 * month,
                             "posting_date": date(2026, month, 10 + (sign < 0)),
                             "user_name": "USER_901", "header_text": "IC accrual",
                             "doc_type": "SA"})  # fmt: skip
            rows.append({"entity": entity, "account": "279030", "amount_dc": 50.0 * month,
                         "posting_date": date(2026, month, 20), "user_name": "USER_902",
                         "header_text": "Corr. reclass", "doc_type": "SA"})  # fmt: skip
    for entity in ("C101", "C102"):  # one accrual not reversed yet, per company code
        rows.append({"entity": entity, "account": "119001", "amount_dc": 777.0,
                     "posting_date": date(2026, 6, 25), "user_name": "USER_901",
                     "header_text": "IC accrual", "doc_type": "SA"})  # fmt: skip
    lines = frame(rows)
    cards = run_miner(lines, Rules())
    assert [c.account for c in cards] == ["279030"]
    assert cards[0].exposure_eur == 2 * 50.0 * sum(range(1, 7))
    assert cards[0].facts["paired_lines"] == 0
    everything = run_miner(lines, Rules(miner_max_paired_share=1.0))
    assert sorted(c.account for c in everything) == ["119001", "279030"]
    routine = next(c for c in everything if c.account == "119001")
    assert routine.exposure_eur == 2 * 777.0, "only the accruals not reversed are left"


def test_gap_note_and_prompt_use_the_direction() -> None:
    from app.ai.prompts import next_check, template_comment, user_prompt
    from app.engines import gap_wording

    words = gap_wording(1_838_461.53, 1_324_638.17, "credit")
    record = _finding(exposure=1_838_461.53).model_copy(
        update={
            "type": "pulse_gap",
            "facts": {
                "gap_eur": 1_838_461.53, "balance_eur": 1_324_638.17,
                "balance_abs_eur": 1_324_638.17, "expected_eur": -513_823.36,
                "latest_month": "2026-09", "since_month": "2025-05",
                "lowest_gap_eur": 1_058_373.0, "lowest_gap_month": "2025-07",
                **{k: v for k, v in words.items() if k != "title"},
            },
        }
    )  # fmt: skip
    note = template_comment(record)
    assert "more was paid than accrued" in note
    assert "debit balance of 1,324,638 EUR" in note
    assert "unmatched accrual batches" not in note
    assert next_check(record).startswith("missing or late accruals")
    prompt = user_prompt(record)
    assert "more was paid than accrued" in prompt and "missing or late accruals" in prompt


# ----- pulse --------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Payroll202609", (2026, 9)),
        ("January2023", (2023, 1)),
        ("URSSAF/ASSEDIC SITE03 - Jan'2025", (2025, 1)),
        ("Dec' 2025", (2025, 12)),
        ("03/2026", (2026, 3)),
        ("P05 2021", (2021, 5)),
        ("Auszahl. Rente_07.2025", (2025, 7)),
        ("URSSAF - Sept 2024", (2024, 9)),
        ("July'2024", (2024, 7)),
        ("CFE Q3 2025", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_period(text: object, expected: tuple[int, int] | None) -> None:
    assert parse_period(text) == expected


def _profile(**kw: object) -> PaymentProfile:
    defaults: dict[str, object] = dict(
        erp="P20", entity="C192", account="279006", label="test",
        batch_text_pattern=r"^Payroll(?P<period>\d{6})$", min_batch_eur=0,
        min_payment_eur=0, max_units=2, window_start_days=-5, window_end_days=70,
        tolerance_pct=0.02, prefer_fewest_units=True,
    )  # fmt: skip
    return PaymentProfile(**{**defaults, **kw})  # type: ignore[arg-type]


def _pulse_lines() -> pd.DataFrame:
    rows = []
    batches = {(2026, 1): 1000.0, (2026, 2): 1000.0, (2026, 4): 1000.0, (2026, 5): 5000.0}
    for (y, m), amount in batches.items():
        posted = date(y, m, 28)
        rows += [
            {"text": f"Payroll{y}{m:02d}", "amount_dc": -amount / 2, "posting_date": posted,
             "document_no": f"10{m:08d}"},
            {"text": f"Payroll{y}{m:02d}", "amount_dc": -amount / 2, "posting_date": posted,
             "document_no": f"10{m:08d}"},
        ]  # fmt: skip
    # Jan paid exactly 30 days after period end; Feb paid (0.5% short) but labelled January;
    # Apr and May unpaid.
    rows.append({"text": "URSSAF Jan'2026", "amount_dc": 1000.0, "doc_type": "P1",
                 "posting_date": date(2026, 3, 2), "document_no": "2000000001"})  # fmt: skip
    rows.append({"text": "URSSAF Jan'2026", "amount_dc": 995.0, "doc_type": "P1",
                 "posting_date": date(2026, 3, 30), "document_no": "2000000002"})  # fmt: skip
    return frame(rows)


def test_matching_window_tolerance_and_lag() -> None:
    lines = _pulse_lines()
    result = analyse_profile(lines, _profile(), Rules(tolerance_eur=0))
    matched = {m.batch.period: m for m in result.matches}
    assert matched[(2026, 1)].matched and matched[(2026, 1)].lag == 30
    assert matched[(2026, 2)].matched and matched[(2026, 2)].lag == 30
    assert not matched[(2026, 4)].matched and not matched[(2026, 5)].matched
    assert result.lag_median == 30


def test_matching_prefers_fewest_units_or_smallest_difference() -> None:
    lines = frame([
        {"text": "Payroll202601", "amount_dc": -1000.0, "posting_date": date(2026, 1, 31)},
        {"amount_dc": 990.0, "posting_date": date(2026, 2, 10), "document_no": "2000000001"},
        {"amount_dc": 600.0, "posting_date": date(2026, 2, 11), "document_no": "2000000002"},
        {"amount_dc": 400.0, "posting_date": date(2026, 2, 12), "document_no": "2000000003"},
    ])  # fmt: skip
    rules = Rules(tolerance_eur=0)
    fewest = analyse_profile(lines, _profile(prefer_fewest_units=True), rules).matches[0]
    closest = analyse_profile(lines, _profile(prefer_fewest_units=False), rules).matches[0]
    assert len(fewest.units) == 1 and fewest.diff == pytest.approx(10)
    assert len(closest.units) == 2 and closest.diff == pytest.approx(0)


def test_payment_outside_window_is_not_matched() -> None:
    lines = frame([
        {"text": "Payroll202601", "amount_dc": -1000.0, "posting_date": date(2026, 1, 31)},
        {"amount_dc": 1000.0, "posting_date": date(2026, 4, 30), "document_no": "2000000001"},
    ])  # fmt: skip
    result = analyse_profile(lines, _profile(window_end_days=70), Rules())
    assert not result.matches[0].matched


def test_gap_timeline_balance_expected_gap() -> None:
    lines = _pulse_lines()
    profile = _profile()
    result = analyse_profile(lines, profile, Rules())
    points = {p.month: p for p in gap_timeline(result.acct, result.matches)}
    assert points["2026-01"].balance == -1000 and points["2026-01"].expected == -1000
    assert points["2026-01"].gap == 0
    assert points["2026-03"].balance == pytest.approx(-5.0)
    assert points["2026-03"].expected == 0  # no batch in March
    assert points["2026-05"].gap == pytest.approx(points["2026-05"].balance + 5000)


def test_pulse_alerts_on_small_frame() -> None:
    rules = Rules(materiality_eur=100, tolerance_eur=0, payment_profiles=[_profile()])
    result = run_pulse(_pulse_lines(), rules, AS_OF)
    types = sorted(r.type for r in result.records)
    assert "pulse_gap" in types
    assert types.count("pulse_missing_payment") == 2  # April and May
    assert "pulse_missing_batch" in types  # March 2026
    assert "label_mismatch" in types  # Feb payment labelled January
    assert "pulse_spike" in types  # May = 5x the median of Jan/Feb/Apr
    missing_batch = next(r for r in result.records if r.type == "pulse_missing_batch")
    assert missing_batch.facts["missing_period"] == "2026-03"


def test_missing_payment_lookback() -> None:
    """A15 (#20): only batches due within the look-back before the run date are raised."""
    # April is expected by 14 Jun 2026 and May by 14 Jul 2026 (period end + 30 + 15 grace).
    base = {"materiality_eur": 100, "tolerance_eur": 0, "payment_profiles": [_profile()]}

    def unpaid(months: int) -> list[str]:
        rules = Rules(**base, missing_payment_lookback_months=months)
        records = run_pulse(_pulse_lines(), rules, AS_OF).records
        missing = [r for r in records if r.type == "pulse_missing_payment"]
        assert all(r.facts["lookback_months"] == months for r in missing)
        return sorted(str(r.facts["batch_period"]) for r in missing)

    assert unpaid(6) == ["2026-04", "2026-05"]  # due on or after 18 May 2026
    assert unpaid(5) == ["2026-05"]  # due on or after 18 Jun 2026: April drops out
    assert unpaid(4) == []
    gap = next(
        r for r in run_pulse(_pulse_lines(), Rules(**base, missing_payment_lookback_months=1),
                             AS_OF).records
        if r.type == "pulse_gap"
    )  # fmt: skip
    assert gap.facts["unmatched_batches"] == 2, "older batches stay on the gap alert"
    with pytest.raises(ValueError):
        Rules(missing_payment_lookback_months=0)


def _june_lines(june_paid: float | None) -> pd.DataFrame:
    """Six 600,000 batches in 2026, each paid 30 days after month end, except June: paid
    ``june_paid`` (outside the tolerance, so it never matches) or not at all."""
    rows: list[dict[str, object]] = []
    for month in range(1, 7):
        end = date(2026, month, 28 if month == 2 else 30 if month in (4, 6) else 31)
        rows.append({"text": f"Payroll2026{month:02d}", "amount_dc": -600_000.0,
                     "posting_date": end, "document_no": f"10000000{month:02d}"})  # fmt: skip
        paid = 600_000.0 if month < 6 else june_paid
        if paid:
            rows.append({"text": "URSSAF", "amount_dc": paid,
                         "posting_date": end + pd.Timedelta(days=30),
                         "document_no": f"20000000{month:02d}"})  # fmt: skip
    for row in rows:
        row["posting_date"] = pd.Timestamp(row["posting_date"]).date()  # type: ignore[arg-type]
    return frame(rows)


@pytest.mark.parametrize(
    ("june_paid", "check", "expected"),
    [
        (None, True, ("No payment found for the 2026-06 batch", -600_000.0)),
        (660_000.0, True, None),  # paid 10% more than booked: the balance is in debit
        (300_000.0, True, ("Payment short by 300K on the 2026-06 batch", -300_000.0)),
        (660_000.0, False, ("No payment found for the 2026-06 batch", -600_000.0)),
    ],
)  # fmt: skip
def test_missing_payment_balance_check(
    june_paid: float | None, check: bool, expected: tuple[str, float] | None
) -> None:
    """A44: a batch the account's balance shows as paid is not raised; a part paid batch is
    raised for what the balance still holds."""
    rules = Rules(
        materiality_eur=100, payment_profiles=[_profile()], missing_payment_balance_check=check
    )
    records = run_pulse(_june_lines(june_paid), rules, date(2026, 10, 23)).records
    missing = [(r.title, r.exposure_eur) for r in records if r.type == "pulse_missing_payment"]
    assert missing == ([expected] if expected else [])


def test_months_before_clamps_to_month_end() -> None:
    assert months_before(date(2026, 11, 18), 12) == date(2025, 11, 18)
    assert months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert months_before(date(2026, 1, 15), 1) == date(2025, 12, 15)


def test_match_batches_does_not_reuse_payments() -> None:
    lines = frame([
        {"text": "Payroll202601", "amount_dc": -1000.0, "posting_date": date(2026, 1, 31)},
        {"text": "Payroll202602", "amount_dc": -1000.0, "posting_date": date(2026, 2, 28)},
        {"amount_dc": 1000.0, "posting_date": date(2026, 3, 2), "document_no": "2000000001"},
    ])  # fmt: skip
    result = analyse_profile(lines, _profile(), Rules())
    assert [m.matched for m in result.matches] == [True, False]
    assert match_batches([], [], _profile(), Rules()) == []


# ----- sentinel -----------------------------------------------------------------------------
def _sentinel_lines() -> pd.DataFrame:
    rows = [{"amount_dc": -10.0, "account": "X"} for _ in range(9)]
    rows.append({"amount_dc": -50_000.0, "account": "X", "user_name": "USER_901",
                 "document_no": "0000000099"})  # fmt: skip
    rows.append({"amount_dc": -60_000.0, "account": "X", "user_name": "BOT_UPLOAD_001",
                 "document_no": "0000000098"})  # fmt: skip
    rows.append({"amount_dc": -70_000.0, "account": "X", "user_name": "BOT_RPA_001",
                 "document_no": "0000000097"})  # fmt: skip
    rows.append({"amount_dc": 0.0, "amount_lc": 99_999.0, "account": "X"})  # FX valuation
    return frame(rows)


def test_s1_scope_options() -> None:
    lines = _sentinel_lines()
    rules = Rules(outlier_multiple=1000)
    assert len(outlier_hits(lines, rules, "all")) == 3
    assert len(outlier_hits(lines, rules, "people_only")) == 1
    assert len(outlier_hits(lines, rules, "exempt_bot_upload")) == 2


def test_s1_records_carry_evidence_and_rule() -> None:
    records = [r for r in run_sentinel(_sentinel_lines(), Rules()) if r.type == "sentinel_outlier"]
    assert len(records) == 1
    record = records[0]
    assert record.evidence == ["0000000099/2026"]
    assert record.facts["posted_by"] == "person"
    assert "S1" in str(record.facts["rule"])


def test_s2_same_amount_in_two_currencies() -> None:
    day, next_day = date(2026, 3, 9), date(2026, 3, 10)
    lines = frame([
        # Hit: 4,200.40 EUR and 4,200 RWF on one day are the same amount in whole units.
        {"document_no": "1", "posting_date": day, "amount_dc": -4_200.4},
        {"document_no": "2", "posting_date": day, "currency_dc": "RWF", "amount_dc": -4_200.0,
         "amount_lc": -2.8, "amount_eur": -2.8},
        # No hit: different days.
        {"document_no": "3", "posting_date": day, "amount_dc": 7_000.0},
        {"document_no": "4", "posting_date": next_day, "currency_dc": "GHS", "amount_dc": 7_000.0,
         "amount_lc": 600.0, "amount_eur": 600.0},
        # No hit: the same currency.
        {"document_no": "5", "posting_date": day, "amount_dc": 8_000.0},
        {"document_no": "6", "posting_date": day, "amount_dc": -8_000.0},
        # No hit: one document in two currencies, but different amounts.
        {"document_no": "7", "posting_date": day, "amount_dc": 5_000.0},
        {"document_no": "7", "item": 2, "posting_date": day, "currency_dc": "RWF",
         "amount_dc": -7_500_000.0, "amount_lc": -5_000.0, "amount_eur": -5_000.0},
        # Below the default minimum of 1,000.
        {"document_no": "8", "posting_date": day, "amount_dc": 600.0},
        {"document_no": "9", "posting_date": day, "currency_dc": "GHS", "amount_dc": 600.0,
         "amount_lc": 50.0, "amount_eur": 50.0},
    ])  # fmt: skip
    rules = Rules()
    assert rules.sentinel_s2_min_amount == 1_000
    records = [r for r in run_sentinel(lines, rules) if r.type == "sentinel_two_currencies"]
    assert len(records) == 1
    record = records[0]
    assert record.evidence == ["1/2026", "2/2026"]
    assert record.facts["currencies"] == "EUR, RWF"
    assert record.facts["amount_dc"] == 4_200
    assert record.facts["lines"] == 2
    assert record.exposure_eur == 4_200.4
    assert "1,000" in str(record.facts["rule"])
    assert record.suggested_class == "Required Adjustment Item"
    assert len(two_currency_alerts(lines, Rules(sentinel_s2_min_amount=500))) == 2
    # A third line of the same amount joins the finding; the finding keeps its id.
    more = frame([{"document_no": "10", "posting_date": day, "amount_dc": 4_200.0}])
    grown = two_currency_alerts(pd.concat([lines, more], ignore_index=True), rules)
    assert [(r.id, len(r.evidence)) for r in grown] == [(record.id, 3)]


def test_s3_currency_codes() -> None:
    lines = frame([
        {"document_no": "1", "currency_dc": "XXQ", "amount_dc": -5.0, "amount_lc": -1.0},
        {"document_no": "2", "currency_dc": "DEM", "posting_date": date(2015, 6, 1),
         "amount_dc": 900.0, "amount_lc": 460.0},
        # Still valid: DEM before 2002, BGN before 2026.
        {"document_no": "3", "currency_dc": "DEM", "posting_date": date(2001, 6, 1),
         "amount_dc": 900.0, "amount_lc": 460.0},
        {"document_no": "4", "currency_dc": "BGN", "posting_date": date(2025, 12, 31),
         "amount_dc": 900.0, "amount_lc": 460.0},
        {"document_no": "5", "currency_dc": "BGN", "posting_date": date(2026, 1, 2),
         "amount_dc": 900.0, "amount_lc": 460.0},
        # An amount equal in two currencies is no longer an S3 finding (dropped in #10).
        {"document_no": "6", "currency_dc": "GHS", "amount_dc": -1_845.0},
    ])  # fmt: skip
    records = {r.evidence[0]: r for r in currency_code_alerts(lines)}
    assert sorted(records) == ["1/2026", "2/2015", "5/2026"]
    assert records["1/2026"].title == "'XXQ' is not a valid currency code"
    assert "euro_since" not in records["1/2026"].facts
    assert records["2/2015"].title == "DEM was replaced by the euro"
    assert records["2/2015"].facts["euro_since"] == "2002-01-01"
    assert records["5/2026"].facts["euro_since"] == "2026-01-01"
    # Both kinds keep the id key used before #10, so earlier decisions survive.
    assert records["2/2015"].id == stable_id(
        "sentinel_currency_code", "P20", "C192", "279006", ["2/2015", "invalid"]
    )
    assert not ISO_CURRENCIES & REPLACED_BY_EURO.keys()


# ----- typos --------------------------------------------------------------------------------
def spelling(rows: list[dict[str, object]], rules: Rules | None = None) -> list[ExceptionRecord]:
    return [r for r in run_typos(frame(rows), rules or Rules()) if "found" in r.facts]


def test_spelling_prompt_one_edit_from_a_word_used_20_times_as_often() -> None:
    """A6 (#12): rare word, one letter away, the usual spelling 20x as common; Text and header."""
    rows = [{"text": "URSSAF/ASSEDIC SITE03 - Jan'2026"} for _ in range(20)]
    rows.append({"text": "URSAAF/ASSEDIC SITE03 - Feb'2026", "document_no": "0000000077"})
    rows += [{"text": "Retirement fund"} for _ in range(20)]
    rows.append({"text": "", "header_text": "Retirment fund", "document_no": "0000000078"})
    rows += [{"text": "deductions"} for _ in range(30)] + [{"text": "deduction"}]  # plural
    rows += [{"text": "Langfr. Rueckst."} for _ in range(30)] + [{"text": "Langrf. Rueckst."}]
    records = spelling(rows)
    assert sorted((r.facts["found"], r.facts["suggestion"]) for r in records) == [
        ("Retirment", "Retirement"), ("URSAAF", "URSSAF")
    ]  # fmt: skip
    ursaaf = next(r for r in records if r.facts["found"] == "URSAAF")
    assert ursaaf.evidence == ["0000000077/2026"]
    assert ursaaf.facts["edits"] == 1 and ursaaf.facts["dictionary_count"] == 20
    assert str(ursaaf.facts["prompt"]).startswith("You may have made a mistake")


def test_spelling_prompt_thresholds_and_allow_list_come_from_rules() -> None:
    rows = [{"text": "Allow payroll"} for _ in range(19)] + [{"text": "Alloc payroll"}]
    assert spelling(rows) == [], "19 is not 20 times as common, and 'alloc' is allowed"
    rows.append({"text": "Allow payroll"})
    assert spelling(rows) == [], "on the allow-list"
    records = spelling(rows, Rules(typo_allow_list=[]))
    assert [(r.facts["found"], r.facts["suggestion"]) for r in records] == [("Alloc", "Allow")]
    assert spelling(rows, Rules(typo_allow_list=[], typo_common_ratio=25)) == []


def test_spelling_word_length_and_rare_count_come_from_rules() -> None:
    """#13: the shortest word checked and "rare" are Rules parameters, shown in the facts."""
    rows = [{"text": "Paid"} for _ in range(100)] + [{"text": "Pais"}]
    assert spelling(rows) == [], "four letters is below the default minimum of five"
    shorter = spelling(rows, Rules(typo_min_word_length=4))
    assert [(r.facts["found"], r.facts["suggestion"]) for r in shorter] == [("Pais", "Paid")]
    assert shorter[0].facts["min_word_length"] == 4

    rows = [{"text": "Salary"} for _ in range(100)] + [{"text": "Salery"} for _ in range(4)]
    assert spelling(rows) == [], "seen 4 times is not rare at the default of 3"
    records = spelling(rows, Rules(typo_max_rare_count=4))
    assert [(r.facts["found"], r.facts["suggestion"]) for r in records] == [("Salery", "Salary")]
    assert records[0].facts["max_rare_count"] == 4
    assert records[0].facts["common_ratio"] == 20.0


def test_typo_thresholds_are_bounded() -> None:
    from pydantic import ValidationError

    for bad in (
        {"typo_max_edits": 0},
        {"typo_max_edits": 4},
        {"typo_max_rare_count": 0},
        {"typo_common_ratio": 0},
        {"typo_min_word_length": 1},
        {"period_label_min_lines": 1},
    ):
        with pytest.raises(ValidationError):
            Rules(**bad)  # type: ignore[arg-type]


def test_period_label_minimum_lines_comes_from_rules() -> None:
    rows = [{"text": "Payroll202609", "document_no": "6", "item": 1}]
    rows.append({"text": "Payroll202608", "document_no": "6", "item": 2})
    rows.append({"text": "Payroll202609", "document_no": "6", "item": 3})
    found = [r for r in run_typos(frame(rows), Rules()) if "found_period" in r.facts]
    assert len(found) == 1, "three lines reach the default minimum"
    assert found[0].facts["min_lines"] == 3
    strict = Rules(period_label_min_lines=4)
    assert [r for r in run_typos(frame(rows), strict) if "found_period" in r.facts] == []


def test_period_label_prompt() -> None:
    rows = [{"text": "Payroll202609", "document_no": "5", "item": i} for i in range(4)]
    rows.append({"text": "Payroll202608", "document_no": "5", "item": 9})
    records = [r for r in run_typos(frame(rows), Rules()) if "found_period" in r.facts]
    assert len(records) == 1
    assert records[0].facts["found_period"] == "2026-08"
    assert records[0].facts["expected_period"] == "2026-09"


# ----- miner --------------------------------------------------------------------------------
def test_fingerprint_masks_names_spells_out_corr_and_masks_digits() -> None:
    assert fingerprint_text("Corr. NAME205 reclass to 279006") == ("correction <name> reclass to #")
    assert fingerprint_text("CORR NAME1 05/2026") == "correction <name> #/#"
    assert fingerprint_text("Correction run 7") == "correction run #", "only the word corr"
    assert fingerprint_text("Accorr 1") == "accorr #"
    assert fingerprint_text(None) == fingerprint_text("  ") == ""


def _manual(months: list[int], entity: str = "C192", user: str = "USER_045",
            header: str | None = "Corr. NAME{m} reclass {m}", day: int = 20,
            first_doc: int = 0) -> list[dict[str, object]]:  # fmt: skip
    """One person-posted line per month with a header text (A7)."""
    return [
        {"user_name": user, "doc_type": "SA", "entity": entity, "posting_date": date(2026, m, day),
         "header_text": None if header is None else header.format(m=m), "text": "Reclass",
         "document_no": f"{first_doc + i:010d}", "amount_dc": 100.0 + m}
        for i, m in enumerate(months)
    ]  # fmt: skip


def test_miner_score_is_entities_times_months() -> None:
    """A7: score = distinct entities x distinct months; Inbox at miner_min_score (12)."""
    one_entity = _manual(list(range(1, 7)))  # 6 months x 1 entity = 6
    assert run_miner(frame(one_entity), Rules()) == []
    assert len(run_miner(frame(one_entity), Rules(miner_min_score=6))) == 1
    second = _manual([5, 6], entity="C132", day=25, first_doc=100)  # 6 months x 2 = 12
    records = run_miner(frame(one_entity + second), Rules())
    assert len(records) == 1
    record = records[0]
    assert record.type == "miner_cluster"
    assert (record.facts["months"], record.facts["entities"]) == (6, 2)
    assert record.facts["miner_score"] == 12
    assert record.facts["entity_list"] == "C132, C192"
    assert record.entity == "C132", "the record sits on the lowest company code"
    assert record.title == "Repeated manual posting: 6 months"
    # 25 May adds the second entity (5 x 2 = 10); 20 Jun adds the sixth month (6 x 2 = 12).
    assert record.first_signal == date(2026, 6, 20), "the line that lifted the score to 12"
    assert record.facts["pattern"] == "correction <name> reclass #"
    assert "NAME" not in str(record.facts["fingerprint"])
    assert "USER" not in str(record.facts), "user ids never reach the facts (the AI layer)"
    assert str(record.facts["hint"]).startswith("This may be a correction")
    assert len(record.evidence) == 8


def test_miner_needs_min_repeats_in_distinct_months() -> None:
    rows = _manual([5, 6, 7])
    assert len(run_miner(frame(rows), Rules(miner_min_score=0, miner_min_repeats=3))) == 1
    assert run_miner(frame(rows), Rules(miner_min_score=0, miner_min_repeats=4)) == []
    record = run_miner(frame(rows), Rules(miner_min_score=0))[0]
    assert record.facts["months"] == 3
    assert record.first_signal == date(2026, 7, 20)


def test_miner_ignores_bots_and_lines_without_header_text() -> None:
    rules = Rules(miner_min_score=0)
    assert run_miner(frame(_manual([1, 2, 3, 4], user="BOT_RPA_001")), rules) == []
    assert run_miner(frame(_manual([1, 2, 3, 4], header=None)), rules) == []
    assert run_miner(frame(_manual([1, 2, 3, 4], header="   ")), rules) == []


def test_miner_by_user_switch() -> None:
    """The original rule keeps people apart; miner_by_user=False joins them."""
    rows = _manual([1, 2]) + _manual([3, 4], user="USER_046", first_doc=50)
    rules = Rules(miner_min_score=0)
    assert run_miner(frame(rows), rules) == [], "two people, two months each"
    joined = run_miner(frame(rows), rules.model_copy(update={"miner_by_user": False}))
    assert len(joined) == 1
    assert (joined[0].facts["months"], joined[0].facts["people"]) == (4, 2)


def test_miner_ids_are_stable_and_ranked_by_score() -> None:
    rules = Rules(miner_min_score=0)
    strong = _manual(list(range(1, 9)))
    weak = _manual([1, 2, 3], user="USER_046", header="True-up {m}", first_doc=50)
    records = run_miner(frame(weak + strong), rules)
    assert [r.facts["months"] for r in records] == [8, 3], "highest score first"
    later = run_miner(frame(strong[1:] + weak), rules)
    assert {r.id for r in later} == {r.id for r in records}, "a cleared line keeps the id"


def test_miner_id_survives_line_counts_shifting_between_entities() -> None:
    """CLAUDE.md rule 10: a pattern spanning company codes keeps its id when a later extract
    changes which code has the most lines. The record sits on the lowest code (A7)."""
    rules = Rules(miner_min_score=0)
    low = _manual([1, 2, 3], entity="C132", first_doc=0)

    def run(c192_months: list[int]):  # type: ignore[no-untyped-def]
        rows = low + _manual(c192_months, entity="C192", day=25, first_doc=100)
        [record] = run_miner(frame(rows), rules)
        return record

    first = run([4, 5])  # C132 has more lines (3 against 2)
    overtaken = run([4, 5, 6, 7])  # the higher code overtakes (4 against 3)
    tied = run([4, 5, 6])  # a tie (3 and 3)
    assert first.id == overtaken.id == tied.id
    assert {first.entity, overtaken.entity, tied.entity} == {"C132"}
    assert overtaken.facts["entity_list"] == "C132, C192"


def test_miner_id_survives_a_tie_after_the_higher_code_led() -> None:
    rules = Rules(miner_min_score=0)
    low = _manual([1, 2], entity="C132", first_doc=0)
    led = low + _manual([3, 4, 5], entity="C192", day=25, first_doc=100)  # C192 leads
    tied = low + _manual([3, 4], entity="C192", day=25, first_doc=100)  # one C192 line cleared
    [a], [b] = run_miner(frame(led), rules), run_miner(frame(tied), rules)
    assert a.id == b.id and a.entity == b.entity == "C132"


# ----- lead time and score ------------------------------------------------------------------
def test_nth_working_day_after_month_end() -> None:
    """A8: the close review is the 5th Monday-to-Friday day after month end, minus holidays."""
    from app.engines.leadtime import nth_working_day_after

    # 31 Jan 2026 is a Saturday: Mon 2 Feb is day 1, Fri 6 Feb day 5.
    assert nth_working_day_after(date(2026, 1, 31), 5) == date(2026, 2, 6)
    # 30 Sep 2026 is a Wednesday: Thu 1, Fri 2, Mon 5, Tue 6, Wed 7 Oct.
    assert nth_working_day_after(date(2026, 9, 30), 5) == date(2026, 10, 7)
    assert nth_working_day_after(date(2026, 9, 30), 1) == date(2026, 10, 1)
    # A holiday on Mon 2 Feb pushes the 5th working day to Mon 9 Feb.
    assert nth_working_day_after(date(2026, 1, 31), 5, {date(2026, 2, 2)}) == date(2026, 2, 9)


def test_next_run_on_or_after() -> None:
    from app.engines.leadtime import next_run_on_or_after

    assert next_run_on_or_after(date(2026, 10, 5), 0) == date(2026, 10, 5), "a Monday is the run"
    assert next_run_on_or_after(date(2026, 9, 18), 0) == date(2026, 9, 21), "Friday -> Monday"
    assert next_run_on_or_after(date(2026, 11, 22), 0) == date(2026, 11, 23), "Sunday -> Monday"
    assert next_run_on_or_after(date(2026, 9, 18), 2) == date(2026, 9, 23), "Wednesday runs"


def test_badge_text() -> None:
    from app.engines.leadtime import badge_text

    assert badge_text(7, "close_review", 365) == "Caught 7 days before the close review"
    assert badge_text(1, "close_review", 365) == "Caught 1 day before the close review"
    assert badge_text(310, "ageing", 365) == "Caught 310 days before the 365-day ageing rule"
    assert badge_text(-2, "close_review", 365) == "Seen 2 days after the close review"
    assert badge_text(None, "never", None) == "Today's process would miss this"


def test_lead_time_by_basis() -> None:
    lines = _sentinel_lines()
    rules = Rules()
    record = run_sentinel(lines, rules)[0]
    assert record.first_signal == date(2026, 1, 31)  # posted on Saturday 31 Jan
    timed = apply_lead_time([record], lines, rules)[0]
    assert timed.today_detection == date(2026, 2, 6)  # 5th working day after 31 Jan
    assert timed.facts["okane_run_date"] == "2026-02-02"  # the Monday run
    assert timed.lead_days == 4, "weekly view: Monday 2 Feb to Friday 6 Feb"
    assert timed.facts["lead_days_daily"] == 6
    assert timed.facts["lead_days_weekly"] == 4
    assert timed.facts["lead_badge"] == "Caught 4 days before the close review"
    assert timed.facts["today_detection_basis"] == "month-end close review"
    daily = apply_lead_time([record], lines, rules.model_copy(update={"lead_time_view": "daily"}))
    assert daily[0].lead_days == 6
    holiday = rules.model_copy(update={"close_review_holidays": [date(2026, 2, 6)]})
    assert apply_lead_time([record], lines, holiday)[0].today_detection == date(2026, 2, 9)

    rules_small = Rules(materiality_eur=100, payment_profiles=[_profile()])
    pulse = run_pulse(_pulse_lines(), rules_small, AS_OF).records
    timed_pulse = {r.type: r for r in apply_lead_time(pulse, _pulse_lines(), rules_small)}
    assert timed_pulse["pulse_gap"].today_detection is None
    assert timed_pulse["pulse_gap"].lead_days is None
    missing = timed_pulse["pulse_missing_payment"]
    accrual = date.fromisoformat(str(missing.facts["accrual_date"]))
    assert missing.today_detection == date.fromordinal(accrual.toordinal() + 365)


def test_score_uses_rules_weights() -> None:
    rules = Rules(materiality_eur=100, payment_profiles=[_profile()])
    records = run_pulse(_pulse_lines(), rules, AS_OF).records
    scored = score_records(records, rules, AS_OF)
    assert scored == sorted(scored, key=lambda r: (-r.score, r.id))
    for record in scored:
        assert set(record.score_breakdown) == set(rules.weights)
        assert record.score == pytest.approx(sum(record.score_breakdown.values()), abs=0.11)
        assert 0 <= record.score <= 100
    zero = Rules(materiality_eur=100, payment_profiles=[_profile()],
                 weights=dict.fromkeys(rules.weights, 0))  # fmt: skip
    assert all(r.score == 0 for r in score_records(records, zero, AS_OF))


def _finding(type_: str = "sentinel_outlier", entity: str = "C192", account: str = "279006",
             exposure: float = 0.0, expected_by: date | None = None,
             facts: dict[str, float | str] | None = None) -> ExceptionRecord:  # fmt: skip
    return ExceptionRecord(
        id=stable_id(type_, "P20", entity, account, [str(exposure)]), run_id="r", type=type_,
        workgroup="Payroll", erp="P20", entity=entity, account=account, account_name="",
        title="t", exposure_eur=exposure, facts=facts or {}, evidence=[],
        first_signal=date(2026, 6, 30), today_detection=None, lead_days=None,
        expected_by=expected_by, suggested_class=None, score=0, score_breakdown={},
        ai_comment=None, verifier="not_run", status="new", decision_reason=None,
    )  # fmt: skip


def test_score_exposure_scales_to_five_times_materiality() -> None:
    """A9 (#18): exposure / (exposure_cap_multiple x materiality), capped at 1."""
    from app.engines.exposure import score_components

    rules = Rules(materiality_eur=500_000)
    parts = {e: score_components(_finding(exposure=e), rules, AS_OF, 0)["exposure"]
             for e in (-1_250_000, 2_500_000, 10_000_000)}  # fmt: skip
    assert parts == {-1_250_000: 0.5, 2_500_000: 1.0, 10_000_000: 1.0}, "sign ignored, capped"
    original = rules.model_copy(update={"exposure_cap_multiple": 1.0})
    assert score_components(_finding(exposure=500_000), original, AS_OF, 0)["exposure"] == 1.0


def test_score_days_past_expected_caps_at_90() -> None:
    from app.engines.exposure import score_components

    rules = Rules()

    def days(record: ExceptionRecord) -> float:
        return score_components(record, rules, AS_OF, 0)["days_past_expected"]

    assert days(_finding(expected_by=date.fromordinal(AS_OF.toordinal() - 45))) == 0.5
    assert days(_finding(expected_by=date.fromordinal(AS_OF.toordinal() - 400))) == 1.0
    assert days(_finding(expected_by=date.fromordinal(AS_OF.toordinal() + 3))) == 0.0
    assert days(_finding(expected_by=None)) == 0.0
    gap = _finding("pulse_gap")  # counts from its first month-end above materiality
    assert days(gap) == min((AS_OF - gap.first_signal).days / 90, 1.0)


def test_score_penalty_account_and_error_type_come_from_rules() -> None:
    from app.engines.exposure import score_components

    rules = Rules()
    c192, other = _finding(), _finding(entity="C132")
    assert score_components(c192, rules, AS_OF, 0)["penalty_account"] == 1.0
    assert score_components(other, rules, AS_OF, 0)["penalty_account"] == 0.0
    wider = rules.model_copy(update={"penalty_accounts": ["P20/C132/279006"]})
    assert score_components(other, wider, AS_OF, 0)["penalty_account"] == 1.0
    assert score_components(c192, rules, AS_OF, 0)["error_type"] == 0.7
    severe = rules.model_copy(update={"error_type_severity": {"sentinel_outlier": 0.9}})
    assert score_components(c192, severe, AS_OF, 0)["error_type"] == 0.9
    assert score_components(_finding("typo"), severe, AS_OF, 0)["error_type"] == 0.0


def test_score_repeats_read_the_miner_months() -> None:
    """A9 (#18): repeats = 1 when a Miner pattern on the same ERP, account and company code
    spans at least repeats_min_months months; the months come from the Miner's facts."""
    from app.engines.exposure import miner_months

    long = _finding(
        "miner_cluster", account="279030", facts={"months": 4, "entity_list": "C132, C192"}
    )
    short = _finding("miner_cluster", account="279031", facts={"months": 2, "entity_list": "C192"})
    same, cousin = _finding(account="279030"), _finding(entity="C132", account="279030")
    elsewhere = _finding(entity="C141", account="279030")
    records = [long, short, same, cousin, elsewhere]
    assert miner_months(records) == {long.id: 4, short.id: 2, same.id: 4, cousin.id: 4,
                                     elsewhere.id: 0}  # fmt: skip
    points = {r.id: r.score_breakdown["repeats"] for r in score_records(records, Rules(), AS_OF)}
    assert points == {long.id: 10, short.id: 0, same.id: 10, cousin.id: 10, elsewhere.id: 0}
    stricter = Rules(repeats_min_months=5)
    assert all(r.score_breakdown["repeats"] == 0 for r in score_records(records, stricter, AS_OF))


def test_score_breakdown_adds_up_and_ids_ignore_the_score() -> None:
    """The breakdown sums exactly to the score; a score never moves an id (CLAUDE.md rule 10)."""
    records = [
        _finding(exposure=1_234_567.89, expected_by=date(2026, 9, 1)),
        _finding("pulse_gap", exposure=-777_777.77),
        _finding("miner_cluster", entity="C132", exposure=33_333.33, facts={"months": 7}),
        _finding("typo", entity="C141", exposure=12.34),
    ]
    for rules in (Rules(), Rules(materiality_eur=100_000), Rules(repeats_min_months=9)):
        scored = score_records(records, rules, AS_OF)
        assert {r.id for r in scored} == {r.id for r in records}
        for r in scored:
            assert set(r.score_breakdown) == set(rules.weights)
            assert r.score == round(sum(r.score_breakdown.values()), 1)
            for name, points in r.score_breakdown.items():
                assert 0 <= points <= rules.weights[name]


def test_inbox_view_by_type_and_materiality() -> None:
    """A25 (#21): prompts and Miner cards have their own tabs; the default view holds findings at
    or above materiality and the types in Rules.inbox_always_types."""
    from app.engines.exposure import inbox_view

    rules = Rules(materiality_eur=500_000)
    assert inbox_view(_finding("typo", exposure=9e6), rules) == "prompts"
    assert inbox_view(_finding("label_mismatch", exposure=9e6), rules) == "prompts"
    assert inbox_view(_finding("miner_cluster", exposure=9e6), rules) == "repeats"
    assert inbox_view(_finding(exposure=-500_000), rules) == "attention", "at the limit, any sign"
    assert inbox_view(_finding(exposure=499_999.99), rules) == "other"
    assert inbox_view(_finding("pulse_missing_batch"), rules) == "attention"
    assert inbox_view(_finding("pulse_missing_batch"), Rules(inbox_always_types=[])) == "other"
    assert inbox_view(_finding(exposure=150_000), Rules(materiality_eur=100_000)) == "attention"


def test_exception_ids_are_stable_across_runs(synthetic_lines: pd.DataFrame) -> None:
    rules = Rules()
    first = {r.id for r in run_pulse(synthetic_lines, rules, AS_OF).records}
    second = {r.id for r in run_pulse(synthetic_lines.copy(), rules, AS_OF).records}
    assert first == second and len(first) > 0


# ----- AI layer: verifier, prompts, client ---------------------------------------------------
GAP_FACTS: dict[str, float | str] = {
    "gap_eur": 1_838_461.53,
    "balance_eur": 1_324_638.17,
    "expected_eur": -513_823.36,
    "diff_pct": -0.29,
    "multiple": 4.1,
    "expected_by": "2026-11-21",
    "since_month": "2025-05",
    "rule": "Batch above 3x the trailing 12-month median",
}


@pytest.mark.parametrize(
    ("comment", "passes"),
    [
        ("The gap is 1,838,462 EUR.", True),
        ("The gap is 1,838,461.53 EUR.", True),
        ("The gap is 1,838,461.5 EUR.", True),
        ("The gap is 1.84M.", True),
        ("The gap is 1.8M.", True),
        ("The gap is 1.838M.", True),
        ("The gap is 1.84 million.", True),
        ("The gap is 1,838 thousand.", True),
        ("The gap is 1.85M.", False),  # near miss
        ("The gap is 1.839M.", False),  # wrong at the shown precision
        ("The gap is 1,838,460 EUR.", False),  # near miss
        ("The gap is 1,838 EUR.", False),  # unit dropped
        ("The gap is EUR 1,838,462 against a balance of 1,324,638.", True),
        ("The expected balance is -513,823.36.", True),  # sign ignored
        ("The payment is 0.29% short.", True),
        ("The payment is 0.3% short.", True),
        ("The payment is 0.30% short.", False),
        ("The batch is 4.1x the median.", True),
        ("The batch is 4.2x the median.", False),
        ("It is above 3x the 12-month median.", True),  # numbers from the rule text
        ("Expected by 21 Nov 2026.", True),
        ("Expected by November 21, 2026.", True),
        ("Expected by 2026-11-21.", True),
        ("Expected by 22 Nov 2026.", False),
        ("Above materiality since May 2025.", True),
        ("Above materiality since 2025-05.", True),
        ("Above materiality since June 2025.", False),
        ("Two payments of 7 days.", False),  # invented figure
        ("Check the batch for C192 and the Payroll202609 lines.", True),  # identifiers
        ("Clear it within 21 days.", False),  # the day of a fact date is not a figure
        ("The 2026 accruals are open.", False),  # nor is its year
        ("No numbers here at all.", True),
    ],
)
def test_verifier(comment: str, passes: bool) -> None:
    from app.ai.verifier import verify

    outcome = verify(comment, GAP_FACTS)
    assert (outcome.result == "passed") is passes, (outcome.checked, outcome.failed)
    if not passes:
        assert outcome.failed


def test_verifier_reports_each_figure_and_allows_identifiers() -> None:
    from app.ai.verifier import verify

    outcome = verify("Account 279006 shows 1.84M, not 2.5M, since 2025-05.", GAP_FACTS)
    assert outcome.result == "failed"
    assert outcome.failed == ["279006", "2.5M"]
    with_ids = verify("Account 279006 shows 1.84M since 2025-05.", GAP_FACTS, ["C192", "279006"])
    assert with_ids.result == "passed"
    assert set(with_ids.checked) == {"2025-05", "279006", "1.84M"}


def test_every_template_comment_passes_the_verifier(synthetic_lines: pd.DataFrame) -> None:
    from app.ai.prompts import TEMPLATE_LABEL, template_comment
    from app.ai.verifier import verify
    from app.services.pipeline import run_engines

    records = run_engines(synthetic_lines, Rules(), AS_OF).records
    assert len({r.type for r in records}) >= 9
    for record in records:
        text = template_comment(record)
        assert text.startswith(TEMPLATE_LABEL)
        body = text.removeprefix(TEMPLATE_LABEL)
        outcome = verify(body, record.facts, [record.entity, record.account])
        assert outcome.result == "passed", (record.type, outcome.failed)


def test_prompt_masks_names_hides_documents_and_titles(synthetic_lines: pd.DataFrame) -> None:
    from app.ai.prompts import user_prompt
    from app.services.pipeline import run_engines

    records = run_engines(synthetic_lines, Rules(), AS_OF).records
    for record in records:
        prompt = user_prompt(record)
        assert not re.search(r"NAME\d+", prompt, re.IGNORECASE)
        if "prompt" not in record.facts:  # a mistake prompt repeats its own wording
            assert record.title not in prompt  # titles carry rounded amounts (#45)
        assert '"miner_score"' not in prompt  # the comment may not give a score (A10)
        for document in record.evidence:
            assert document.split("/")[0] not in prompt


@pytest.mark.parametrize(
    ("key", "value", "shown"),
    [
        ("gap_eur", 1_838_461.53, "1,838,462 EUR"),
        ("expected_eur", -513_823.36, "-513,823 EUR"),
        ("amount_lc", 12_500_000.0, "12,500,000 JPY"),
        ("amount_dc", 1_000.0, "1,000"),  # no document currency in these facts
        ("diff_pct", -0.29, "-0.29%"),
        ("multiple", 4.1, "4.1x"),
        ("lines", 3.0, "3"),
        ("lag_p90_days", 12.5, "12.5"),
        ("expected_by", "2026-11-21", "21 Nov 2026"),
        ("since_month", "2025-05", "May 2025"),
    ],
)
def test_display_formats_each_kind(key: str, value: float | str, shown: str) -> None:
    from app.ai.prompts import display

    assert display(key, value, {"currency_lc": "JPY"}) == shown


def test_every_displayed_figure_passes_the_verifier(synthetic_lines: pd.DataFrame) -> None:
    from app.ai.prompts import figures
    from app.ai.verifier import verify
    from app.services.pipeline import run_engines

    for record in run_engines(synthetic_lines, Rules(), AS_OF).records:
        for name, figure in figures(record).items():
            outcome = verify(figure["value"], record.facts, [record.entity, record.account])
            assert outcome.result == "passed", (record.type, name, outcome.failed)


def test_render_fills_slots_and_reports_unknown_names() -> None:
    from app.ai.prompts import render

    figs = {"gap_eur": {"value": "1,838,462 EUR", "means": "the gap"}}
    text, unknown = render("A gap of {gap_eur}, not { gap_eur }; see {balance}.", figs)
    assert text == "A gap of 1,838,462 EUR, not 1,838,462 EUR; see {balance}."
    assert unknown == ["balance"]


@pytest.mark.parametrize(
    ("draft", "shown"),
    [
        ("It is {multiple}x the median.", "It is 4.1x the median."),
        ("It is {multiple} × the median.", "It is 4.1x the median."),
        ("A gap of {gap_eur} EUR.", "A gap of 1,838,462 EUR."),
        ("Posted as {amount_dc} in DEM.", "Posted as 12,000 DEM."),
        ("Off by {diff_pct} percent.", "Off by -0.29%."),
        ("A gap of {gap_eur} away from plan.", "A gap of 1,838,462 EUR away from plan."),
        ("Seen {lines} lines in {entity}.", "Seen 3 lines in C192."),
        ("It is {multiple} the median.", "It is 4.1x the median."),
        ("It is {multiple} times the median.", "It is 4.1x the median."),
        ("A gap of {gap_eur} euros.", "A gap of 1,838,462 EUR."),
        ("A gap of EUR {gap_eur}.", "A gap of 1,838,462 EUR."),
        ("A gap of € {gap_eur}.", "A gap of 1,838,462 EUR."),
        ("Posted as DEM {amount_dc}.", "Posted as 12,000 DEM."),
        ("Paid in HUF {gap_eur}.", "Paid in HUF 1,838,462 EUR."),  # a different code stays
        ("A gap of {{gap_eur}}.", "A gap of 1,838,462 EUR."),
    ],
)
def test_render_drops_a_repeated_unit(draft: str, shown: str) -> None:
    from app.ai.prompts import render

    figs = {
        key: {"value": value, "means": ""}
        for key, value in {
            "multiple": "4.1x", "gap_eur": "1,838,462 EUR", "amount_dc": "12,000 DEM",
            "diff_pct": "-0.29%", "lines": "3", "entity": "C192",
        }.items()
    }  # fmt: skip
    assert render(draft, figs) == (shown, [])


@pytest.mark.parametrize(
    ("comment", "issue"),
    [
        (" ".join(["word"] * 60), None),
        (" ".join(["word"] * 61), "Longer than 60 words (61)"),
        ("The gap is open because the payment was late.", "States a cause"),
        ("The gap is due to a late payment.", "States a cause"),
        ("A possible cause is a late payment.", None),
        ("The gap may be because the payment was late.", None),
        ("The amount due to employees is open.", None),  # "due to" as a payable, not a cause
        ("This is a Timing item.", "Names a classification"),
        ("This is a high-risk item.", "Gives a risk level"),
        ("The risk level is high.", "Gives a risk level"),
        ("Clear it before the deadline.", "Sets a deadline"),
        ("Check the unmatched batches listed as evidence.", None),
        ("Check the cause of the gap.", None),  # names a cause, does not state one
        ("Find the reason for the difference.", None),
        ("The cause is a late payment.", "States a cause"),
        ("The likely reason was a late payment.", "States a cause"),
        ("Clear it within 21 days.", "Sets a deadline"),
        ("Clear it by the end of {latest_month}.", "Sets a deadline"),
        ("It is usually paid within {lag_p90_days} days.", None),  # a figure, not a deadline
    ],
)
def test_wording_issues(comment: str, issue: str | None) -> None:
    from app.ai.verifier import wording_issues

    issues = wording_issues(comment)
    if issue is None:
        assert issues == []
    else:
        assert len(issues) == 1 and issues[0].startswith(issue), issues


def _record(synthetic_lines: pd.DataFrame):  # type: ignore[no-untyped-def]
    return next(r for r in run_pulse(synthetic_lines, Rules(), AS_OF).records
                if r.type == "pulse_gap")  # fmt: skip


def _mock_ollama(replies: list[str], calls: list[dict]):  # type: ignore[no-untyped-def,type-arg]
    """Ollama stand-in: answers ``replies`` in order and records each request body."""
    import json as jsonlib

    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(jsonlib.loads(request.content))
        content = replies[min(len(calls), len(replies)) - 1]
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("enabled", "tags", "state", "reason"),
    [
        (True, {"models": [{"name": "qwen2.5:7b-instruct"}]}, "on", None),
        (True, {"models": [{"name": "llama3:8b"}]}, "offline", "the model is not installed"),
        (True, None, "offline", "the local model server does not answer"),
        (False, None, "off", "turned off in settings"),
    ],
)  # fmt: skip
def test_assistant_status(enabled: bool, tags: dict | None, state: str, reason: str | None) -> None:  # type: ignore[type-arg]
    """A45: the run dock says whether the assistant drafts notes."""
    import httpx

    from app.ai.client import assistant_status
    from app.config import Settings

    def handler(request: httpx.Request) -> httpx.Response:
        if tags is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=tags)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    status = assistant_status(Settings(ai_enabled=enabled), http)
    assert (status.assistant, status.model, status.reason) == (state, "qwen2.5:7b-instruct", reason)


def _reply(text: str) -> str:
    import json as jsonlib

    return jsonlib.dumps({"comment": text})


GOOD_SLOTS = (
    "The month-end balance of {entity} for {latest_month} is {balance_eur}, a gap of {gap_eur} "
    "from the expected {expected_eur}. Check the unmatched accrual batches listed as evidence."
)
BAD_FIGURE = "The gap is 9,999,999 EUR above the expected balance."


def test_client_renders_slots_verifies_and_caches(tmp_path, synthetic_lines) -> None:  # type: ignore[no-untyped-def]
    from app.ai.client import cache_key, draft_comment
    from app.ai.prompts import display
    from app.config import Settings
    from app.database import Database

    db = Database(tmp_path / "ai.duckdb")
    settings = Settings(ai_enabled=True)
    record = _record(synthetic_lines)
    gap = display("gap_eur", record.facts["gap_eur"], record.facts)  # "1,234,568 EUR"

    calls: list[dict] = []  # type: ignore[type-arg]
    first = draft_comment(record, db, settings, http=_mock_ollama([_reply(GOOD_SLOTS)], calls))
    assert (first.source, first.verifier, len(calls)) == ("model", "passed", 1)
    assert gap in first.comment and gap.removesuffix(" EUR") in first.checked_figures
    assert "{" not in first.comment
    assert calls[0]["options"]["temperature"] == 0
    assert calls[0]["format"]["required"] == ["comment"]  # JSON schema, not just "json"

    again = draft_comment(record, db, settings, http=_mock_ollama([BAD_FIGURE], calls))
    assert again.cached and again.comment == first.comment and len(calls) == 1

    other_model = Settings(ai_enabled=True, ollama_model="llama3.1:8b")
    assert cache_key(record, other_model) != cache_key(record, settings)
    db.close()


def test_client_retries_with_feedback(tmp_path, synthetic_lines) -> None:  # type: ignore[no-untyped-def]
    from app.ai.client import draft_comment
    from app.config import Settings
    from app.database import Database

    db = Database(tmp_path / "ai.duckdb")
    record = _record(synthetic_lines)
    calls: list[dict] = []  # type: ignore[type-arg]
    http = _mock_ollama([_reply(BAD_FIGURE), _reply(GOOD_SLOTS)], calls)
    result = draft_comment(record, db, Settings(ai_enabled=True), http=http)

    assert (result.source, result.verifier, len(calls)) == ("model", "passed", 2)
    retry = calls[1]["messages"]
    assert [m["role"] for m in retry] == ["system", "user", "assistant", "user"]
    assert "9,999,999" in retry[2]["content"]  # the failed draft is shown back
    assert "'9,999,999' doesn't match" in retry[3]["content"]
    assert "{gap_eur}" in retry[3]["content"]  # with the names it may use
    db.close()


def test_client_rejects_wording_and_unknown_names(tmp_path, synthetic_lines) -> None:  # type: ignore[no-untyped-def]
    from app.ai.client import check, draft_comment
    from app.ai.prompts import figures
    from app.config import Settings
    from app.database import Database

    db = Database(tmp_path / "ai.duckdb")
    record = _record(synthetic_lines)
    calls: list[dict] = []  # type: ignore[type-arg]
    cause = _reply("The gap of {gap_eur} is open because a payment was missed.")
    unknown = _reply("The liability of {liability_eur} is above the expected balance.")
    result = draft_comment(record, db, Settings(ai_enabled=True),
                           http=_mock_ollama([cause, unknown], calls))  # fmt: skip
    assert "States a cause" in calls[1]["messages"][3]["content"]
    assert result.source == "template" and result.rejected_draft is not None
    assert result.rejected_reasons == ["Refers to a figure Okane doesn't have"]  # no slot names
    # the model, on the other hand, is told the exact name it got wrong
    attempt = check("The liability of {liability_eur} is open.", record, figures(record))
    assert attempt.reasons == ["Uses a figure name we don't have: {liability_eur}"]
    db.close()


def test_client_twice_rejected_returns_template_with_draft(tmp_path, synthetic_lines) -> None:  # type: ignore[no-untyped-def]
    from app.ai.client import draft_comment
    from app.ai.prompts import TEMPLATE_LABEL
    from app.config import Settings
    from app.database import Database

    db = Database(tmp_path / "ai.duckdb")
    settings = Settings(ai_enabled=True)
    record = _record(synthetic_lines)
    calls: list[dict] = []  # type: ignore[type-arg]
    result = draft_comment(record, db, settings, http=_mock_ollama([_reply(BAD_FIGURE)], calls))

    assert len(calls) == 2
    assert (result.source, result.verifier) == ("template", "not_run")
    assert result.comment.startswith(TEMPLATE_LABEL) and "9,999,999" not in result.comment
    assert result.rejected_draft == BAD_FIGURE
    assert result.rejected_reasons == ["'9,999,999' doesn't match any of our figures"]

    cached = draft_comment(record, db, settings, http=_mock_ollama([_reply(GOOD_SLOTS)], calls))
    assert cached.cached and cached.rejected_draft == BAD_FIGURE and len(calls) == 2
    db.close()


def test_client_falls_back_to_labelled_template(tmp_path, synthetic_lines) -> None:  # type: ignore[no-untyped-def]
    import httpx

    from app.ai.client import cached_comment, draft_comment, ollama_available
    from app.config import Settings
    from app.database import Database

    db = Database(tmp_path / "ai.duckdb")
    record = _record(synthetic_lines)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    down = httpx.Client(transport=httpx.MockTransport(refuse))
    settings = Settings(ai_enabled=True)
    result = draft_comment(record, db, settings, http=down)
    assert (result.source, result.verifier) == ("template", "not_run")
    assert result.comment.startswith("Standard note") and result.rejected_draft is None
    assert not ollama_available(settings, http=down)
    assert cached_comment(record, db, settings) is None  # an outage is not cached

    calls: list[dict] = []  # type: ignore[type-arg]
    junk = _mock_ollama(["not json", '{"text": "wrong field"}'], calls)
    assert draft_comment(record, db, settings, http=junk).source == "template"
    disabled = draft_comment(record, db, Settings(ai_enabled=False))
    assert disabled.source == "template"
    db.close()


# ----- AI typo check (#30) -------------------------------------------------------------------
def _spelling(synthetic_lines: pd.DataFrame) -> list[ExceptionRecord]:
    from app.ai.typo_check import spelling_prompts

    return spelling_prompts(run_typos(synthetic_lines, Rules()))


def test_typo_samples_are_scoped_and_masked(synthetic_lines: pd.DataFrame) -> None:
    from app.engines.typos import typo_samples

    records = _spelling(synthetic_lines)
    assert records
    for record in records:
        samples = typo_samples(synthetic_lines, record)
        assert 1 <= len(samples) <= 3 and len(set(samples)) == len(samples)
        found = str(record.facts["found"]).lower()
        assert all(found in s.lower() for s in samples)
        assert not any(re.search(r"NAME\d+", s, re.IGNORECASE) for s in samples)


@pytest.mark.parametrize(
    ("is_typo", "suggestion", "kept"),
    [
        (False, "URSSAF", None),
        (True, "URSSAF", "URSSAF"),
        (True, "urssaf", "URSSAF"),  # the rule's casing
        (True, None, "URSSAF"),
        (True, "URSAAF", "URSSAF"),  # the flagged word itself
        (True, "ursaff", "ursaff"),  # common in the run and one letter away
        (True, "urssat", "URSSAF"),  # in the run but rare
        (True, "payroll", "URSSAF"),  # common but not close
        (True, "Unedic", "URSSAF"),  # not a word of the run
    ],
)
def test_typo_suggestion_must_be_a_common_run_word(
    synthetic_lines: pd.DataFrame, is_typo: bool, suggestion: str | None, kept: str | None
) -> None:
    from collections import Counter

    from app.ai.typo_check import TypoVerdict, accepted_suggestion

    record = _spelling(synthetic_lines)[0]
    record = record.model_copy(update={"facts": {**record.facts, "found": "URSAAF",
                                                 "suggestion": "URSSAF"}})  # fmt: skip
    vocabulary = Counter({"urssaf": 62, "ursaaf": 1, "ursaff": 40, "urssat": 1, "payroll": 90})
    verdict = TypoVerdict(is_typo=is_typo, suggestion=suggestion)
    assert accepted_suggestion(verdict, record, vocabulary, Rules()) == kept


def test_typo_check_is_advisory_and_cached(tmp_path, synthetic_lines) -> None:  # type: ignore[no-untyped-def]
    from app.ai.typo_check import annotate_typos
    from app.config import Settings
    from app.database import Database

    db = Database(tmp_path / "ai.duckdb")
    settings = Settings(ai_enabled=True)
    records = run_typos(synthetic_lines, Rules())
    spelling = _spelling(synthetic_lines)
    calls: list[dict] = []  # type: ignore[type-arg]
    reply = '{"is_typo": false, "suggestion": null}'
    http = _mock_ollama([reply], calls)

    checked = annotate_typos(records, synthetic_lines, Rules(), db, settings, True, http)
    assert len(calls) == len(spelling)
    # both keys required: Ollama may skip an optional key (#62 review)
    assert calls[0]["format"]["required"] == ["is_typo", "suggestion"]
    assert not any(re.search(r"NAME\d+", str(c["messages"]), re.IGNORECASE) for c in calls)
    for before, after in zip(records, checked, strict=True):
        # the verdict never hides a prompt or changes what code decided
        assert before.model_dump(exclude={"ai_check"}) == after.model_dump(exclude={"ai_check"})
        if before in spelling:
            assert after.ai_check is not None and after.ai_check.verdict == "not_a_typo"
            assert after.ai_check.suggestion is None
        else:
            assert after.ai_check is None  # period-label prompts are not checked

    again = annotate_typos(records, synthetic_lines, Rules(), db, settings, False)
    assert [r.ai_check for r in again] == [r.ai_check for r in checked]
    assert len(calls) == len(spelling)  # served from the cache
    db.close()


def test_typo_check_without_a_model_changes_nothing(tmp_path, synthetic_lines) -> None:  # type: ignore[no-untyped-def]
    import httpx

    from app.ai.typo_check import annotate_typos
    from app.config import Settings
    from app.database import Database

    db = Database(tmp_path / "ai.duckdb")
    settings = Settings(ai_enabled=True)
    records = run_typos(synthetic_lines, Rules())
    assert annotate_typos(records, synthetic_lines, Rules(), db, settings, False) == records

    attempts: list[int] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("connection refused")

    down = httpx.Client(transport=httpx.MockTransport(refuse))
    assert annotate_typos(records, synthetic_lines, Rules(), db, settings, True, down) == records
    assert len(attempts) == 1  # stops asking after the first failure
    db.close()


def test_cached_typo_verdict_follows_todays_rules(tmp_path, synthetic_lines) -> None:  # type: ignore[no-untyped-def]
    from collections import Counter

    from app.ai.typo_check import check_typo
    from app.config import Settings
    from app.database import Database

    db = Database(tmp_path / "ai.duckdb")
    settings = Settings(ai_enabled=True)
    record = _spelling(synthetic_lines)[0]
    record = record.model_copy(update={"facts": {**record.facts, "found": "URSAAF",
                                                 "suggestion": "URSSAF"}})  # fmt: skip
    vocabulary = Counter({"urssaf": 62, "ursaaf": 1, "ursaff": 40})
    calls: list[dict] = []  # type: ignore[type-arg]
    http = _mock_ollama(['{"is_typo": true, "suggestion": "ursaff"}'], calls)

    first = check_typo(record, ["URSAAF contribution"], vocabulary, Rules(), db, settings, http)
    assert first is not None and first.suggestion == "ursaff"  # 40 >= 20 x 1
    # the controller raises the ratio: the cached answer is checked again, without the model
    stricter = Rules(typo_common_ratio=50)
    again = check_typo(record, ["URSAAF contribution"], vocabulary, stricter, db, settings, None)
    assert again is not None and again.suggestion == "URSSAF" and len(calls) == 1
    db.close()


def test_typo_prompt_masks_names_and_long_numbers(synthetic_lines: pd.DataFrame) -> None:
    from app.ai.typo_check import typo_prompt

    record = _spelling(synthetic_lines)[0]
    prompt = typo_prompt(record, ["Retirment top-up NAME12 ref 1900012345, 2 lines"])
    assert "NAME12" not in prompt and "1900012345" not in prompt
    assert "[name]" in prompt and "[number]" in prompt and "2 lines" in prompt


def test_model_errors_do_not_carry_the_models_text() -> None:
    from app.ai.client import ModelUnavailableError, chat
    from app.ai.typo_check import TypoVerdict
    from app.config import Settings

    calls: list[dict] = []  # type: ignore[type-arg]
    reply = '{"is_typo": "maybe", "suggestion": "Retirement top-up 4,812.50"}'
    with pytest.raises(ModelUnavailableError) as failure:
        chat([], TypoVerdict, Settings(ai_enabled=True), _mock_ollama([reply], calls))
    assert "4,812.50" not in str(failure.value) and "Retirement" not in str(failure.value)
    assert "ValidationError" in str(failure.value)
