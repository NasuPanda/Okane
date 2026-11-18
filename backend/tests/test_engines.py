"""Engine unit tests on small hand-built frames, plus synthetic end-to-end checks."""

from __future__ import annotations

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
    parse_period,
    run_pulse,
)
from app.engines.sentinel import outlier_hits, run_sentinel
from app.engines.typos import run_typos
from app.schemas import PaymentProfile, Rules

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
    rows.append({"amount_dc": -50_000.0, "account": "X", "user_name": "USER_120",
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


def test_s2_and_s3() -> None:
    lines = frame([
        {"document_no": "1", "currency_dc": "RWF", "amount_dc": -6_000.0, "amount_lc": -4.0,
         "amount_eur": -4.0},
        {"document_no": "1", "currency_dc": "EUR", "amount_dc": 4.0},
        {"document_no": "2", "currency_dc": "GHS", "amount_dc": -1_845.0},  # unconverted
        {"document_no": "3", "currency_dc": "XXQ", "amount_dc": -5.0, "amount_lc": -1.0},
        {"document_no": "4", "currency_dc": "GHS", "amount_dc": -0.4},  # below 1 unit
    ])  # fmt: skip
    records = run_sentinel(lines, Rules())
    by_type = sorted((r.type, r.evidence[0]) for r in records)
    assert by_type == [
        ("sentinel_currency_code", "2/2026"),
        ("sentinel_currency_code", "3/2026"),
        ("sentinel_two_currencies", "1/2026"),
    ]


# ----- typos --------------------------------------------------------------------------------
def test_spelling_prompt_uses_account_dictionary() -> None:
    rows = [{"text": "URSSAF/ASSEDIC SITE03 - Jan'2026"} for _ in range(6)]
    rows.append({"text": "URSAAF/ASSEDIC SITE03 - Feb'2026", "document_no": "0000000077"})
    rows += [{"text": "deductions"} for _ in range(6)] + [{"text": "deduction"}]
    records = [r for r in run_typos(frame(rows), Rules()) if "found" in r.facts]
    assert [(r.facts["found"], r.facts["suggestion"]) for r in records] == [("URSAAF", "URSSAF")]
    assert records[0].evidence == ["0000000077/2026"]
    assert str(records[0].facts["prompt"]).startswith("You may have made a mistake")


def test_period_label_prompt() -> None:
    rows = [{"text": "Payroll202609", "document_no": "5", "item": i} for i in range(4)]
    rows.append({"text": "Payroll202608", "document_no": "5", "item": 9})
    records = [r for r in run_typos(frame(rows), Rules()) if "found_period" in r.facts]
    assert len(records) == 1
    assert records[0].facts["found_period"] == "2026-08"
    assert records[0].facts["expected_period"] == "2026-09"


# ----- miner --------------------------------------------------------------------------------
def test_fingerprint_masks_names_and_digits() -> None:
    assert fingerprint_text("Manual correction NAME205 reclass to 279006") == (
        "manual correction <name> reclass to #"
    )


def test_miner_needs_min_repeats_in_distinct_months() -> None:
    rows = [
        {"user_name": "USER_045", "doc_type": "SA", "posting_date": date(2026, m, 20),
         "text": f"Manual correction NAME{200 + m} reclass", "document_no": f"00000000{m}"}
        for m in (5, 6, 7)
    ]  # fmt: skip
    rows.append({"user_name": "BOT_RPA_001", "doc_type": "SA", "posting_date": date(2026, 8, 1),
                 "text": "Manual correction NAME999 reclass"})  # fmt: skip
    assert len(run_miner(frame(rows), Rules(miner_min_repeats=3))) == 1
    assert run_miner(frame(rows), Rules(miner_min_repeats=4)) == []
    record = run_miner(frame(rows), Rules())[0]
    assert record.facts["months"] == 3
    assert record.first_signal == date(2026, 7, 20)
    assert "NAME" not in str(record.facts["pattern"])


# ----- lead time and score ------------------------------------------------------------------
def test_lead_time_by_basis() -> None:
    lines = _sentinel_lines()
    rules = Rules(close_review_days=5)
    record = run_sentinel(lines, rules)[0]
    timed = apply_lead_time([record], lines, rules)[0]
    assert timed.today_detection == date(2026, 2, 5)  # 31 Jan month end + 5 days
    assert timed.lead_days == 5
    assert timed.facts["today_detection_basis"] == "month-end close review"

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


def test_exception_ids_are_stable_across_runs(synthetic_lines: pd.DataFrame) -> None:
    rules = Rules()
    first = {r.id for r in run_pulse(synthetic_lines, rules, AS_OF).records}
    second = {r.id for r in run_pulse(synthetic_lines.copy(), rules, AS_OF).records}
    assert first == second and len(first) > 0
