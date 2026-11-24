"""Golden values.

Two halves:

- ``test_real_*``: the brief's "Expected" values on the real workbooks (section 8). They skip
  automatically when ``data/inbox/`` lacks the workbook they need (always the case in CI).
- ``test_synthetic_*``: the same rules on the synthetic workbooks, whose planted cases are
  documented in ``scripts/generate_sample_data.py``. They always run, so CI is meaningful.

Real tests assert aggregates plus the row-level values the brief itself quotes (allowed by
docs/ASSUMPTIONS.md A35); nothing row-level is printed and no real row is stored.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.engines import is_person
from app.engines.exposure import payroll_netting
from app.engines.miner import run_miner
from app.engines.pairs import paired_count
from app.engines.pulse import PulseResult, expected_by, run_pulse
from app.engines.sentinel import outlier_alerts, outlier_hits, run_sentinel
from app.engines.typos import run_typos
from app.schemas import Rules

AS_OF = date(2026, 11, 18)
PAYROLL_RATES = {
    "HUF": 366.2, "XOF": 655.957, "AUD": 1.6297, "CZK": 24.44, "GBP": 0.85463,
    "IDR": 20_315.3, "KRW": 1_539.1,
}  # fmt: skip


# ----- EUR conversion (brief section 8) -----------------------------------------------------
def test_real_payroll_rates_match_brief(real_lines: pd.DataFrame) -> None:
    rates = real_lines.groupby("currency_lc")["eur_rate"].agg(["min", "max"])
    for currency, rate in PAYROLL_RATES.items():
        assert rates.loc[currency, "min"] == pytest.approx(rate)
        assert rates.loc[currency, "max"] == pytest.approx(rate)


def test_real_p20_allowed_age_365(real_lines: pd.DataFrame) -> None:
    p20 = real_lines[real_lines["erp"] == "P20"]
    assert len(p20) == 8_298
    assert int((p20["allowed_age"] == 365).sum()) == 8_193


def test_synthetic_payroll_rates(synthetic_lines: pd.DataFrame) -> None:
    huf = synthetic_lines[synthetic_lines["currency_lc"] == "HUF"]
    assert set(huf["eur_rate"]) == {366.2}


def test_synthetic_pension_account_is_exempt(synthetic_lines: pd.DataFrame) -> None:
    pension = synthetic_lines[synthetic_lines["account"] == "279020"]
    assert len(pension) == 3
    assert pension["allowed_age"].isna().all()
    assert (pension["overdue_abs"] == 0).all()


# ----- engines on real data (brief section 8 "Expected") ------------------------------------
@pytest.fixture(scope="module")
def real_pulse(real_lines: pd.DataFrame) -> PulseResult:
    return run_pulse(real_lines, Rules(), AS_OF)


def test_real_exact_pairs(real_lines: pd.DataFrame) -> None:
    assert paired_count(real_lines[real_lines["workbook"] == "Payroll"]) == 476


def test_real_payroll_netting(real_lines: pd.DataFrame) -> None:
    result = payroll_netting(real_lines, 500_000)
    assert result.old_rule_lines == 5_475
    assert result.old_rule_overdue_abs == pytest.approx(145_668_628, abs=1)
    assert result.net_eur == pytest.approx(-5_693_332, abs=1)
    assert result.groups_above() == 4
    assert payroll_netting(real_lines, 100_000).groups_above() == 7
    top = [(g.entity, g.account, round(g.net_eur)) for g in result.groups[:4]]
    assert top == [
        ("C242", "34900001", -6_497_211), ("C192", "279006", 1_087_864),
        ("C192", "179003", 679_839), ("C192", "279014", -649_069),
    ]  # fmt: skip
    c242 = next(g for g in result.groups if (g.entity, g.account) == ("C242", "34900015"))
    assert c242.lines == 15
    assert c242.overdue_abs == pytest.approx(24_935_919, abs=1)
    assert round(c242.net_eur) == -2_493


def test_real_c192_pulse(real_pulse: PulseResult) -> None:
    c192 = real_pulse.profiles["P20/C192/279006"]
    assert sum(m.matched for m in c192.matches) == 21
    assert c192.lag_median == 30
    assert c192.lag_p90 == 37
    latest = c192.timeline[-1]
    assert latest.month == "2026-09"
    assert latest.balance == pytest.approx(1_324_638, abs=1)
    assert latest.gap == pytest.approx(1_838_462, abs=1)
    sep = next(m for m in c192.matches if m.batch.period == (2026, 9))
    assert sep.batch.amount == pytest.approx(-513_823.36)
    assert len(sep.batch.lines) == 68
    assert sep.batch.accrual_date == date(2026, 9, 29)
    assert expected_by(sep.batch, c192.profile, c192.lag_p90, Rules()) == date(2026, 11, 21)
    since_may = [p for p in c192.timeline if p.month >= "2025-05"]
    assert all(p.gap >= 500_000 for p in since_may)
    lowest = min(since_may, key=lambda p: p.gap)
    assert (lowest.month, round(lowest.gap)) == ("2025-07", 1_058_373)


def test_real_c192_alerts(real_pulse: PulseResult) -> None:
    c192 = [r for r in real_pulse.records if (r.entity, r.account) == ("C192", "279006")]
    gap = next(r for r in c192 if r.type == "pulse_gap")
    # A43 (review of 22 Nov 2026): the brief's "Liability 1.84M above expected" read as "more
    # is owed". The gap points toward debit on a credit-normal account with a debit balance, so
    # it now reads as below expected, more paid than accrued.
    assert gap.title == "Liability 1.84M below expected: more paid than accrued"
    assert (gap.facts["normal_side"], gap.facts["gap_direction"]) == ("credit", "toward debit")
    assert (gap.facts["balance_side"], gap.facts["wrong_side_balance"]) == ("debit", "yes")
    assert gap.facts["balance_abs_eur"] == pytest.approx(1_324_638.17)
    assert gap.first_signal == date(2025, 5, 31)
    spikes = [r for r in c192 if r.type == "pulse_spike"]
    assert [(r.facts["batch_period"], r.facts["multiple"]) for r in spikes] == [("2026-08", 4.1)]
    assert spikes[0].facts["batch_eur"] == pytest.approx(-2_531_445.87)
    assert round(float(spikes[0].facts["median_eur"])) == 620_878
    missing = [r.facts["missing_period"] for r in c192 if r.type == "pulse_missing_batch"]
    assert missing == ["2025-08"]
    labels = {
        (r.first_signal, r.facts["label_period"]): r for r in c192 if r.type == "label_mismatch"
    }
    jan = labels[(date(2024, 3, 28), "2024-01")]
    assert jan.facts["settles_period"] == "2024-02"
    assert jan.facts["diff_pct"] == pytest.approx(-0.29)
    assert jan.facts["payment_eur"] == pytest.approx(653_106.90)
    # ASSUMPTION (docs/ASSUMPTIONS.md): the brief says this payment settles August (-0.30%);
    # greedy date-order matching assigns it to July. The mismatch fires either way. The -0.30%
    # is the payment against the August batch, which stays unmatched. Confirmed in #4 (A13).
    assert (date(2024, 9, 27), "2024-09") in labels
    sep = [
        r
        for r in c192
        if r.type == "pulse_missing_payment" and r.facts["batch_period"] == "2026-09"
    ]
    assert sep == [], "the September 2026 batch is not due before 21 Nov 2026"


def test_real_missing_payments_capped(real_lines: pd.DataFrame) -> None:
    """A15 (#20): 21 missing payments without the cap, 7 with it (C192 4, C242 3).

    Measured with the balance check off (A44), so the cap's own effect stays visible. Older
    unmatched C192 batches stay listed on the gap alert. Widening the C192 profile was tried and
    matched no further payments, so the profile is unchanged.
    """
    unchecked = Rules(missing_payment_balance_check=False)
    pulse = run_pulse(real_lines, unchecked, AS_OF)
    missing = [r for r in pulse.records if r.type == "pulse_missing_payment"]
    c192 = sorted(r.facts["batch_period"] for r in missing if r.entity == "C192")
    assert c192 == ["2026-04", "2026-05", "2026-06", "2026-07"]
    assert sum(r.entity == "C242" for r in missing) == 3
    assert len(missing) == 7
    gap = next(r for r in pulse.records if r.type == "pulse_gap" and r.entity == "C192")
    assert gap.facts["unmatched_batches"] == 19, "the 18 overdue plus Sep 2026, not yet due"
    wide = unchecked.model_copy(update={"missing_payment_lookback_months": 120})
    uncapped = run_pulse(real_lines, wide, AS_OF).records
    assert sum(r.type == "pulse_missing_payment" for r in uncapped) == 21


def test_real_missing_payments_balance_check(real_pulse: PulseResult) -> None:
    """A44 (review of 22 Nov 2026): the account's balance shows 6 of the 7 batches were paid.

    C192 is in debit (more paid than accrued), so none of April to July 2026 is still owed.
    C242's February and June 2026 batches were settled with the next month's payments (the
    month-end balance came back to a few thousand). Only C242's October 2026 batch, still held
    in the open credit balance on 18 Nov, remains. The matching statistics do not change.
    """
    missing = [r for r in real_pulse.records if r.type == "pulse_missing_payment"]
    assert [(r.entity, r.facts["batch_period"]) for r in missing] == [("C242", "2026-10")]
    assert float(missing[0].facts["unpaid_by_balance_eur"]) > 0
    c192 = real_pulse.profiles["P20/C192/279006"]
    matched = sum(m.matched for m in c192.matches)
    assert (matched, c192.lag_median, c192.lag_p90) == (21, 30, 37)


def test_real_c242_matches(real_pulse: PulseResult) -> None:
    c242 = {m.batch.period: m for m in real_pulse.profiles["BPP/C242/34900015"].matches}
    july, august, september = c242[(2025, 7)], c242[(2025, 8)], c242[(2025, 9)]
    assert july.batch.amount == pytest.approx(-4_091_302.21)
    assert sum(u.amount for u in july.units) == pytest.approx(4_090_894.37)
    assert (len(july.units), july.lag) == (3, 12)
    assert (len(august.units), august.lag) == (4, 9)
    assert (len(september.units), september.lag, september.diff) == (3, 12, 0)
    gaps = [r for r in real_pulse.records if r.type == "pulse_gap" and r.entity == "C242"]
    assert gaps == []


def test_real_sentinel_s1(real_lines: pd.DataFrame) -> None:
    rules = Rules()
    every = outlier_hits(real_lines, rules, "all")
    p20 = every[every["erp"] == "P20"]
    assert len(p20) == 174
    assert int((~p20["user_name"].map(is_person)).sum()) == 165
    people = outlier_hits(real_lines, rules, "people_only")
    # Brief section 8 (S1 expected top hit) and open item 1; ASSUMPTIONS A2, A35.
    top = people.sort_values("multiple", ascending=False).iloc[0]
    assert (top["erp"], top["entity"], top["account"], top["document_no"], top["year"]) == (
        "BPP",
        "C242",
        "48900002",
        "7910008634",
        2019,
    )
    assert top["user_name"] == "USER_120"
    assert round(top["multiple"]) == 57_769


def test_real_sentinel_s1_with_fixed_assets(real_all_lines: pd.DataFrame) -> None:
    """Brief section 8: on Payroll plus Fixed assets, S1 returns 185 hits: 173 bots, 12 people."""
    every = outlier_hits(real_all_lines, Rules(), "all")
    assert len(every) == 185
    assert int((~every["user_name"].map(is_person)).sum()) == 173
    assert int(every["user_name"].map(is_person).sum()) == 12
    fixed = every[every["workbook"] == "Fixed assets"]
    assert len(fixed) == 2
    assert int(fixed["user_name"].map(is_person).sum()) == 1


def test_real_sentinel_s1_default_scope(
    real_all_lines: pd.DataFrame, real_lines: pd.DataFrame
) -> None:
    """A1 (decided, #9): S1 flags person-posted lines only, the brief's 12 hits (11 + 1)."""
    rules = Rules()
    assert rules.sentinel_s1_scope == "people_only"
    both = outlier_hits(real_all_lines, rules)
    assert len(both) == 12
    assert both["user_name"].map(is_person).all()
    assert (both["workbook"] == "Payroll").sum() == 11
    assert (both["workbook"] == "Fixed assets").sum() == 1
    assert len(outlier_hits(real_lines, rules)) == 11
    assert len(outlier_alerts(real_all_lines, rules)) == 12, "one Inbox record per hit"


def test_real_fixed_assets_scope(real_all_lines: pd.DataFrame, real_lines: pd.DataFrame) -> None:
    """A3: Fixed assets feed Sentinel, typo prompts and the Miner, never netting or Pulse."""
    from app.services.pipeline import run_engines

    both, payroll = payroll_netting(real_all_lines, 500_000), payroll_netting(real_lines, 500_000)
    assert both.old_rule_lines == payroll.old_rule_lines == 5_475
    assert both.old_rule_overdue_abs == pytest.approx(payroll.old_rule_overdue_abs)
    assert both.net_eur == pytest.approx(payroll.net_eur)
    assert both.groups_above() == 4

    output = run_engines(real_all_lines, Rules(), AS_OF)
    top = output.records[0]
    assert (top.type, top.entity, top.account) == ("pulse_gap", "C192", "279006")
    fixed_types = {r.type for r in output.records if r.workgroup == "Fixed assets"}
    assert fixed_types, "Fixed assets lines reach at least one engine"
    allowed = {"typo", "miner_cluster"}
    assert all(t.startswith("sentinel_") or t in allowed for t in fixed_types), fixed_types


def test_real_sentinel_s2(real_all_lines: pd.DataFrame, real_lines: pd.DataFrame) -> None:
    """A4 (decided, #10): one S2 hit, on Fixed assets P20 C218 119001, in EUR and JPY."""
    from app.engines.sentinel import two_currency_alerts

    rules = Rules()
    hits = two_currency_alerts(real_all_lines, rules)
    assert len(hits) == 1
    hit = hits[0]
    assert (hit.workgroup, hit.erp, hit.entity, hit.account) == (
        "Fixed assets", "P20", "C218", "119001"
    )  # fmt: skip
    assert hit.facts["currencies"] == "EUR, JPY"
    assert hit.facts["lines"] == 3 and len(hit.evidence) == 3
    assert two_currency_alerts(real_lines, rules) == [], "Payroll has none"
    lowest = rules.model_copy(update={"sentinel_s2_min_amount": 0.01})
    assert len(two_currency_alerts(real_all_lines, lowest)) == 1, "the minimum does not matter"


def test_real_sentinel_s3(real_all_lines: pd.DataFrame, real_lines: pd.DataFrame) -> None:
    """A5 (decided, #10): one S3 hit, a DEM line on Fixed assets P20 C238."""
    from app.engines.sentinel import currency_code_alerts

    hits = currency_code_alerts(real_all_lines)
    assert len(hits) == 1
    hit = hits[0]
    assert (hit.workgroup, hit.erp, hit.entity) == ("Fixed assets", "P20", "C238")
    assert hit.facts["currency_dc"] == "DEM"
    assert hit.title == "DEM was replaced by the euro"
    assert hit.facts["lines"] == 1
    assert currency_code_alerts(real_lines) == [], "Payroll has none"


def test_real_typo_prompts(real_all_lines: pd.DataFrame) -> None:
    """A6 (decided, #12): 4 spelling prompts and 7 period labels, all on Payroll."""
    records = run_typos(real_all_lines, Rules())
    spelling = [r for r in records if "found" in r.facts]
    assert {str(r.facts["found"]).lower() for r in spelling} == {
        "adjustmnt", "retirment", "swissllife", "ursaaf"
    }  # fmt: skip
    assert all(r.workgroup == "Payroll" for r in records), "Fixed assets has none"
    periods = [r for r in records if "found_period" in r.facts]
    assert len(periods) == 7
    no_allow_list = run_typos(real_all_lines, Rules(typo_allow_list=[]))
    found = {str(r.facts.get("found")).lower() for r in no_allow_list if "found" in r.facts}
    assert found - {str(r.facts["found"]).lower() for r in spelling} == {"alloc", "recov"}


def test_real_miner_payroll(real_lines: pd.DataFrame) -> None:
    """A7 (decided, #14), aggregates only: 6 patterns reach the Inbox at score 12 (16 at 6, 4 at
    20); the demo card's top pattern scores 42 (42 months x 1 company code) on BPP C242.

    Review of 22 Nov 2026: 2 of the 6 patterns at score 12 are mostly exact pairs (18 of 28 and
    99 of 125 lines), an accrual and its reversal. ``Rules.miner_max_paired_share`` at 0.5 drops
    them (4 at 12, 13 at 6); the switch is off by default (review of PR #73).
    """
    rules = Rules()
    records = run_miner(real_lines, rules)
    assert len(records) == 6
    switched = rules.model_copy(update={"miner_max_paired_share": 0.5})
    kept = run_miner(real_lines, switched)
    assert len(kept) == 4
    assert all(float(r.facts["paired_lines"]) / float(r.facts["lines"]) < 0.5 for r in kept)
    assert len(run_miner(real_lines, switched.model_copy(update={"miner_min_score": 6}))) == 13
    assert all(r.workgroup == "Payroll" for r in records)
    assert all(float(r.facts["miner_score"]) >= 12 for r in records)
    lower = rules.model_copy(update={"miner_min_score": 6})
    assert len(run_miner(real_lines, lower)) == 16
    assert len(run_miner(real_lines, rules.model_copy(update={"miner_min_score": 20}))) == 4
    top = records[0]
    assert (top.erp, top.entity, top.account) == ("BPP", "C242", "48900002")
    assert (top.facts["miner_score"], top.facts["months"], top.facts["entities"]) == (42, 42, 1)
    assert top.facts["lines"] == 111
    shown = ("pattern", "months", "entities", "lines", "total_abs_eur", "documents",
             "first_month", "last_month", "entity_list", "people", "hint")  # fmt: skip
    assert all(r.facts.get(k) not in (None, "") for r in records for k in shown), "#31 card"
    # No top pattern names a correction, so the card stays a hypothesis.
    assert not any("correction" in str(r.facts["pattern"]) for r in records)


def test_real_fixed_assets_exposure(real_fixed_assets: object) -> None:
    """A47 (review of 22 Nov 2026), aggregates only: pairing removes 98% of Fixed assets lines.

    10,198 lines: 101 with a zero document amount (FX valuations), 9,980 in exact pairs, 117
    unpaired, all posted by people. The 98 posted within 60 days of the extract make up the
    balance; the 19 older ones (C242 13, C238 6) net to zero within their entity. Only C102 has
    exchange differences (FX valuations and what exact pairs leave in local currency), so every
    entity's net = recent + older + exchange differences (review of PR #73).
    """
    from app.engines.exposure import fixed_asset_exposure
    from app.ingest import extract_dates

    lines = real_fixed_assets.lines  # type: ignore[attr-defined]
    taken = extract_dates(lines)["Fixed assets"][0]
    result = fixed_asset_exposure(lines, Rules(), taken)
    assert (result.lines, result.zero_amount_lines, result.paired_lines) == (10_198, 101, 9_980)
    assert (result.recent_lines, result.older_lines) == (98, 19)
    by_entity: dict[str, dict[str, float]] = {}
    for g in result.groups:
        entry = by_entity.setdefault(
            g.entity, {"recent": 0.0, "older": 0.0, "fx": 0.0, "net": 0.0, "old": 0}
        )
        entry["recent"] += g.recent_net_lc
        entry["older"] += g.older_net_lc
        entry["fx"] += g.fx_net_lc
        entry["net"] += g.net_lc
        entry["old"] += g.older_lines
    recent = {e: round(v["recent"]) for e, v in by_entity.items() if v["recent"]}
    assert recent == {"C102": 180_393, "C230": 118_375, "C242": 561_509, "C218": 62_456_836,
                      "C238": 4_864_669}  # fmt: skip
    assert {e: v["old"] for e, v in by_entity.items() if v["old"]} == {"C242": 13, "C238": 6}
    assert all(abs(v["older"]) < 1 for v in by_entity.values())
    assert {e for e, v in by_entity.items() if round(v["fx"])} == {"C102"}
    for v in by_entity.values():
        assert round(v["net"], 2) == round(v["recent"] + v["older"] + v["fx"], 2)
    assert {g.currency_lc for g in result.groups if g.estimated_rate} == {"JPY", "PLN"}


def test_synthetic_fixed_assets_exposure(synthetic_lines: pd.DataFrame) -> None:
    """A47 on the synthetic sample: C250's pairs fold away; C218 (JPY) and C219 (PLN) carry
    September 2026 lines inside the 60 days before the 2 Oct 2026 extract."""
    from app.engines.exposure import fixed_asset_exposure

    result = fixed_asset_exposure(synthetic_lines, Rules(), date(2026, 10, 2))
    groups = {g.entity: g for g in result.groups}
    assert sorted(groups) == ["C218", "C219", "C250"]
    assert (groups["C250"].paired_lines, groups["C250"].recent_lines) == (16, 0)
    assert groups["C250"].older_lines == 1 and not groups["C250"].estimated_rate
    assert (groups["C218"].recent_lines, groups["C218"].currency_lc) == (2, "JPY")
    assert groups["C218"].estimated_rate and groups["C219"].estimated_rate
    assert groups["C219"].recent_lines == 2
    assert result.paired_lines == 16 and result.zero_amount_lines == 0
    for g in result.groups:
        assert g.lines == g.zero_amount_lines + g.paired_lines + g.recent_lines + g.older_lines
        parts = g.recent_net_lc + g.older_net_lc + g.fx_net_lc
        assert round(g.net_lc, 2) == round(parts, 2)
        assert round(g.net_eur, 2) == round(g.recent_net_eur + g.older_net_eur + g.fx_net_eur, 2)
    shorter = fixed_asset_exposure(synthetic_lines, Rules(fa_recent_days=5), date(2026, 10, 2))
    assert shorter.recent_lines == 0, "the September lines are older than 5 days"


def test_real_miner_fixed_assets(real_fixed_assets: object) -> None:
    """A3, A7: Fixed assets feed the Miner; aggregates only.

    8 patterns reach score 12+ (measured in the review of PR #50), but every line of each one
    cancels in an exact pair (the "IC Winshuttle" accruals and their reversals on C102, and the
    C218 routines), so each nets to exactly zero. Review of 22 Nov 2026, fix 6 (second pass):
    the default ``miner_max_paired_share`` of 1.0 drops a pattern whose lines all cancel, so no
    Fixed assets card reaches the Inbox.
    """
    lines = real_fixed_assets.lines  # type: ignore[attr-defined]
    assert run_miner(lines, Rules()) == []


def test_real_miner_keeps_payroll_and_drops_fully_paired(real_all_lines: pd.DataFrame) -> None:
    """Fix 6: on both workbooks only the 6 Payroll patterns remain (at most 79% paired), and
    none of them nets to zero."""
    records = run_miner(real_all_lines, Rules())
    assert len(records) == 6
    assert all(r.workgroup == "Payroll" for r in records)
    assert all(float(r.facts["paired_lines"]) < float(r.facts["lines"]) for r in records)
    assert all(abs(float(r.facts["unpaired_net_eur"])) > 0 for r in records)


def test_real_label_mismatch_needs_a_real_share_of_the_batch(real_lines: pd.DataFrame) -> None:
    """Fix 9 (A13): the C242 prompt "Payment labelled 2025-10 settles 2026-04" compared one bank
    line worth 0.02% of the batch with the whole batch. Only a payment carrying at least
    ``label_mismatch_min_share`` (10%) of its batch is judged by its label: C242 has none; the
    five C192 prompts (each 99.7% to 100.1% of its batch) stay."""
    records = run_pulse(real_lines, Rules(), AS_OF).records
    labels = [r for r in records if r.type == "label_mismatch"]
    assert [r for r in labels if r.entity == "C242"] == []
    c192 = sorted((r.facts["label_period"], r.facts["settles_period"]) for r in labels)
    assert len(c192) == 5 and all(r.entity == "C192" for r in labels)
    assert ("2024-01", "2024-02") in c192
    assert all(abs(float(r.facts["diff_pct"])) < 1 for r in labels)
    # With the threshold at 0 the old false prompt comes back, so the rule is what removes it.
    loose = run_pulse(real_lines, Rules(label_mismatch_min_share=0), AS_OF).records
    c242 = [r for r in loose if r.type == "label_mismatch" and r.entity == "C242"]
    assert [(r.facts["label_period"], r.facts["settles_period"]) for r in c242] == [
        ("2025-10", "2026-04")
    ]


# ----- engines on synthetic data (always run) -----------------------------------------------
@pytest.fixture(scope="module")
def synthetic_pulse(synthetic_lines: pd.DataFrame) -> PulseResult:
    return run_pulse(synthetic_lines, Rules(), AS_OF)


def test_synthetic_pairs_and_netting(synthetic_lines: pd.DataFrame) -> None:
    payroll = synthetic_lines[synthetic_lines["workbook"] == "Payroll"]
    assert paired_count(payroll) == 26
    assert paired_count(synthetic_lines[synthetic_lines["workbook"] == "Fixed assets"]) == 16
    result = payroll_netting(synthetic_lines, 500_000)
    assert result.groups_above() == 3
    assert payroll_netting(synthetic_lines, 100_000).groups_above() == 4
    assert [g for g in result.groups if g.account == "279020"] == [], "pension lines never age"
    pairs_group = next(g for g in result.groups if g.account == "279014")
    assert pairs_group.net_eur == 0 and pairs_group.paired_lines == pairs_group.lines


def test_synthetic_c192_pulse(synthetic_pulse: PulseResult) -> None:
    c192 = synthetic_pulse.profiles["P20/C192/279006"]
    assert len(c192.matches) == 20
    assert sum(m.matched for m in c192.matches) == 16
    records = [r for r in synthetic_pulse.records if r.entity == "C192"]
    assert sum(r.type == "pulse_gap" for r in records) == 1
    unpaid = sorted(r.facts["batch_period"] for r in records if r.type == "pulse_missing_payment")
    # May and Jun 2025 are unpaid too, but due more than 12 months ago (A15, #20).
    assert unpaid == ["2026-06"]
    missing = [r.facts["missing_period"] for r in records if r.type == "pulse_missing_batch"]
    assert missing == ["2025-08"]
    assert [r.facts["batch_period"] for r in records if r.type == "pulse_spike"] == ["2026-08"]
    mismatch = [
        (r.facts["label_period"], r.facts["settles_period"])
        for r in records
        if r.type == "label_mismatch"
    ]
    assert mismatch == [("2026-01", "2026-02")]


def test_synthetic_c242_pulse(synthetic_pulse: PulseResult) -> None:
    c242 = synthetic_pulse.profiles["BPP/C242/34900015"]
    assert [len(m.units) for m in c242.matches] == [3, 3, 4, 3]
    assert all(m.lag <= 14 for m in c242.matches)
    assert c242.matches[-1].diff == 0


def test_synthetic_sentinel_typos_miner(synthetic_lines: pd.DataFrame) -> None:
    rules = Rules()
    assert rules.sentinel_s1_scope == "people_only", "A1, decided in #9"
    sentinel = run_sentinel(synthetic_lines, rules)
    outliers = {(r.entity, r.facts["posted_by"]) for r in sentinel if r.type == "sentinel_outlier"}
    assert outliers == {("C192", "person"), ("C218", "person")}
    every = run_sentinel(synthetic_lines, rules.model_copy(update={"sentinel_s1_scope": "all"}))
    assert sum(r.type == "sentinel_outlier" for r in every) == 3
    codes = {r.entity: r.title for r in sentinel if r.type == "sentinel_currency_code"}
    assert codes == {
        "C141": "'GHC' is not a valid currency code",
        "C218": "FRF was replaced by the euro",
    }
    two = [r for r in sentinel if r.type == "sentinel_two_currencies"]
    # #11: one Payroll and one Fixed assets plant.
    assert {(r.workgroup, r.entity, r.facts["currencies"], r.facts["lines"]) for r in two} == {
        ("Payroll", "C132", "EUR, RWF", 2),
        ("Fixed assets", "C219", "EUR, PLN", 2),
    }
    typos = {
        (r.facts.get("found"), r.facts.get("suggestion")) for r in run_typos(synthetic_lines, rules)
    }
    assert typos == {("URSAAF", "URSSAF"), ("Pauroll", "Payroll")}, "A6: swaps are two edits"


def test_synthetic_miner_planted_pattern_and_near_miss(synthetic_lines: pd.DataFrame) -> None:
    """A7 (decided, #14): the planted pattern (6 months x 2 company codes = 12) is found; the
    near-miss (5 x 2 = 10) and the older lines without a header text are not."""
    rules = Rules()
    records = run_miner(synthetic_lines, rules)
    assert len(records) == 1
    top = records[0]
    # The record sits on the lowest company code in the pattern, not the one with most lines.
    assert (top.erp, top.entity, top.account) == ("P20", "C132", "279030")
    assert (top.facts["months"], top.facts["entities"], top.facts["miner_score"]) == (6, 2, 12)
    assert top.facts["entity_list"] == "C132, C192"
    assert top.facts["pattern"] == "correction <name> reclass to # #/#"
    assert top.title == "Repeated manual posting: 6 months"
    assert top.first_signal == date(2026, 10, 21)
    assert len(top.evidence) == 8
    lower = run_miner(synthetic_lines, rules.model_copy(update={"miner_min_score": 10}))
    assert {(r.account, r.facts["miner_score"]) for r in lower} == {("279030", 12), ("279030", 10)}
    assert [r for r in lower if r.account == "279002"] == [], "no header text, no pattern"


def test_synthetic_miner_card_has_every_fact_it_shows(synthetic_lines: pd.DataFrame) -> None:
    """#31: the static Miner card (SentinelPage ``MinerCard`` and ``MinerStory``) reads only the
    record's facts; the planted pattern carries each of them, so the card renders in full."""
    top = run_miner(synthetic_lines, Rules())[0]
    shown = ("pattern", "months", "entities", "lines", "total_abs_eur", "doc_type", "documents",
             "first_month", "last_month", "entity_list", "people", "hint")  # fmt: skip
    assert all(top.facts.get(k) not in (None, "") for k in shown), shown
    assert (top.facts["lines"], top.facts["documents"], top.facts["people"]) == (8, 8, 1)
    assert (top.facts["first_month"], top.facts["last_month"]) == ("2026-05", "2026-10")
    assert top.account_name


# ----- lead time (A8, decided in #16) -------------------------------------------------------
def test_synthetic_c192_gap_ranks_first(synthetic_lines: pd.DataFrame) -> None:
    """A9 (#18): the planted C192 gap ranks first at 500K and 100K; the planted Miner pattern on
    C132/C192 279030 (6 months) earns the full repeats points; every breakdown adds up."""
    from app.services.pipeline import run_engines

    for materiality in (500_000, 100_000):
        records = run_engines(synthetic_lines, Rules(materiality_eur=materiality), AS_OF).records
        top = records[0]
        assert (top.type, top.entity, top.account) == ("pulse_gap", "C192", "279006")
        assert top.score > records[1].score
        for r in records:
            assert r.score == round(sum(r.score_breakdown.values()), 1)
    records = run_engines(synthetic_lines, Rules(), AS_OF).records
    assert (records[0].score, records[1].score) == (90.0, 65.0)
    miner = next(r for r in records if r.type == "miner_cluster")
    assert miner.score_breakdown["repeats"] == 10


def test_synthetic_lead_time(synthetic_lines: pd.DataFrame) -> None:
    """Weekly view: from the Monday run on or after the first signal to today's detection."""
    import statistics

    from app.services.pipeline import run_engines

    records = run_engines(synthetic_lines, Rules(), AS_OF).records
    # Sentinel: the C218 person-posted outlier, posted Friday 18 Sep 2026. Monday run 21 Sep;
    # close review on the 5th working day after Wednesday 30 Sep: Wednesday 7 Oct.
    outlier = next(r for r in records if r.type == "sentinel_outlier" and r.entity == "C218")
    assert outlier.first_signal == date(2026, 9, 18)
    assert outlier.facts["okane_run_date"] == "2026-09-21"
    assert outlier.today_detection == date(2026, 10, 7)
    assert (outlier.lead_days, outlier.facts["lead_days_daily"]) == (16, 19)
    # Fix 7 (review of 22 Nov 2026): the close review (7 Oct) is before the analysis date
    # (18 Nov), so this is a replay of the extract's history, not a catch.
    assert outlier.facts["lead_badge"] == "Would have been caught 16 days before the close review"
    # Pulse: the unpaid June 2026 batch (the May 2025 one is past the 12-month cap, A15).
    # First signal the day after expected-by (Fri 21 Aug 2026), Monday run 24 Aug; the 365-day
    # ageing rule shows it 29 Jun 2027.
    june = next(
        r for r in records
        if r.type == "pulse_missing_payment" and r.facts["batch_period"] == "2026-06"
    )  # fmt: skip
    assert june.first_signal == date(2026, 8, 21)
    assert june.facts["okane_run_date"] == "2026-08-24"
    assert june.today_detection == date(2027, 6, 29)
    assert (june.lead_days, june.facts["lead_days_daily"]) == (309, 312)
    assert june.facts["lead_badge"] == "Caught 309 days before the 365-day ageing rule"
    # Blind spots and the KPI median ("median days earlier", weekly).
    blind = [r for r in records if r.today_detection is None]
    assert {r.type for r in blind} == {"pulse_gap", "pulse_missing_batch", "miner_cluster"}
    assert all(r.facts["lead_badge"] == "Today's process would miss this" for r in blind)
    # The Fixed assets S2 plant (C219, posted Thursday 24 Sep 2026, Monday run 28 Sep, close
    # review 7 Oct): 9 days (#11).
    s2 = next(
        r for r in records if r.type == "sentinel_two_currencies" and r.entity == "C219"
    )  # fmt: skip
    assert (s2.facts["okane_run_date"], s2.today_detection, s2.lead_days) == (
        "2026-09-28", date(2026, 10, 7), 9
    )  # fmt: skip
    # The "Pauroll" typo (C172, posted Tuesday 28 May 2024, Monday run 3 Jun, close review
    # Friday 7 Jun): 4 days. Under A6 (#12) it replaces the "Auzahl" and "trnasit" prompts.
    # Under A15 (#20) only one missing payment remains, so 11 dated findings, median 16.
    pauroll = next(r for r in records if r.type == "typo" and r.entity == "C172")
    assert (pauroll.facts["okane_run_date"], pauroll.today_detection, pauroll.lead_days) == (
        "2024-06-03", date(2024, 6, 7), 4
    )  # fmt: skip
    leads = [r.lead_days for r in records if r.lead_days is not None]
    assert (len(leads), statistics.median(leads)) == (11, 16)


def test_real_lead_time_median(real_lines: pd.DataFrame) -> None:
    """A8, aggregates only: weekly median 11 days earlier over 36 dated findings, 9 blind.

    History: 62 / 17.5 before the typo rule (A6, #12) cut the typo prompts from 22 to 11;
    51 / 25 before the missing-payment cap (A15, #20) cut missing payments from 21 to 7;
    37 / 11 (daily 17) before the balance check (A44) cut them from 7 to 1 (31 / 10, daily 13);
    the 5 wrong-side balances (A46) are dated by the close review and add 5. Open balances are
    in today's ageing report, so they are neither dated nor blind. Blind spots stay at 9: the
    Miner's paired-share switch (A7) is off by default (7 with it on).
    """
    import statistics

    from app.services.pipeline import run_engines

    records = run_engines(real_lines, Rules(), AS_OF).records
    leads = [r.lead_days for r in records if r.lead_days is not None]
    # Fix 9 (A13): 36 before the false C242 label prompt was removed.
    assert (len(leads), statistics.median(leads)) == (35, 11)
    assert sum(r.today_detection is None for r in records) == 9
    assert min(leads) >= 0
    daily = [float(r.facts["lead_days_daily"]) for r in records if r.lead_days is not None]
    # Fix 9 (A13): 14.5 over 36 dated findings before the false C242 label prompt was removed.
    assert statistics.median(daily) == 15


def test_real_c192_september_batch_lead_time(real_lines: pd.DataFrame) -> None:
    """The original's example: the C192 September 2026 batch, still unpaid in the extract.

    Brief section 8 quotes its accrual date (29 Sep 2026) and expected-by date (21 Nov 2026);
    the analysis date is pinned to Monday 23 Nov 2026, after it falls due.

    A44: the account holds a debit balance (more paid than accrued), so with the balance check
    on (the default) the batch is not raised. The brief's lead-time values are checked with the
    check off, the rule the example was written for.
    """
    from app.services.pipeline import run_engines

    checked = run_engines(real_lines, Rules(), date(2026, 11, 23)).records
    assert not [
        r for r in checked
        if (r.entity, r.account, r.type) == ("C192", "279006", "pulse_missing_payment")
    ]  # fmt: skip
    unchecked = Rules(missing_payment_balance_check=False)
    records = run_engines(real_lines, unchecked, date(2026, 11, 23)).records
    sep = [
        r for r in records
        if (r.entity, r.account) == ("C192", "279006")
        and r.type == "pulse_missing_payment" and r.facts["batch_period"] == "2026-09"
    ]  # fmt: skip
    assert len(sep) == 1
    record = sep[0]
    assert record.expected_by == date(2026, 11, 21)
    assert record.first_signal == date(2026, 11, 22)
    assert record.facts["okane_run_date"] == "2026-11-23"
    assert record.today_detection == date(2027, 9, 29), "29 Sep 2026 + the account's 365 days"
    assert (record.lead_days, record.facts["lead_days_daily"]) == (310, 311)


def test_real_s2_fixed_assets_lead_time(real_all_lines: pd.DataFrame) -> None:
    """The original's example: the S2 same-figure-in-two-currencies case on Fixed assets.

    Not run when #17 was built (the Fixed assets workbook was not available), so it checks
    the rule rather than fixed dates. #11 (S2 as built) was still open; S2 itself is on main.
    Its close review falls before the 18 Nov analysis date, so the badge reads as a replay
    (A8, review of 22 Nov 2026, fix 7).
    """
    from app.engines.leadtime import close_review_date, next_run_on_or_after
    from app.services.pipeline import run_engines

    rules = Rules()
    records = run_engines(real_all_lines, rules, AS_OF).records
    hits = [r for r in records if r.type == "sentinel_two_currencies"]
    assert len(hits) == 1
    hit = hits[0]
    assert (hit.workgroup, hit.entity, hit.account) == ("Fixed assets", "C218", "119001")
    assert hit.today_detection == close_review_date(hit.first_signal, rules)
    run = next_run_on_or_after(hit.first_signal, rules.weekly_run_weekday)
    assert hit.lead_days == (hit.today_detection - run).days >= 0
    assert hit.today_detection < AS_OF and hit.facts["replay"] == "yes"
    assert hit.facts["lead_badge"] == (
        f"Would have been caught {hit.lead_days} days before the close review"
    )


def test_real_top_exception_is_c192_gap(real_lines: pd.DataFrame) -> None:
    """Demo step 4 opens the top exception: the C192 social security gap.

    A9 (#18), aggregates only: first at 79.4 ahead of 65.0 at 500K; still first at 100K (demo
    step 6), 90 ahead of 67. No Miner pattern sits on C192 279006, so its repeats points are 0.
    (Before the balance check, A44, the runner-up was a missing payment at 69.8, 89 at 100K.)
    """
    from app.services.pipeline import run_engines

    output = run_engines(real_lines, Rules(), AS_OF)
    top = output.records[0]
    assert (top.type, top.entity, top.account) == ("pulse_gap", "C192", "279006")
    assert output.counts["exposure_groups_above"] == 4
    assert (top.score, output.records[1].score) == (79.4, 65.0)
    assert top.score_breakdown["repeats"] == 0
    assert top.score == round(sum(top.score_breakdown.values()), 1)

    lower = run_engines(real_lines, Rules(materiality_eur=100_000), AS_OF).records
    assert (lower[0].type, lower[0].entity, lower[0].account) == ("pulse_gap", "C192", "279006")
    assert (lower[0].score, lower[1].score) == (90.0, 67.0)


def test_real_default_inbox_view(real_lines: pd.DataFrame) -> None:
    """A25 (#21), aggregates only: 48 findings; the default view holds 21 at 500K (31 at 100K),
    with the C192 gap first; 17 mistake prompts and 6 repeated postings sit on their own tabs.
    (46, 19 and 24 before the balance check, A44, removed 6 missing payments; A46 then added 3
    open balances and 5 wrong-side balances at 500K, 6 and 7 at 100K. The Miner's paired-share
    switch, A7, is off by default; on, it drops 2 repeated postings.)"""
    from collections import Counter

    from app.services.pipeline import run_engines

    for materiality, expected in ((500_000, 21), (100_000, 31)):
        rules = Rules(materiality_eur=materiality)
        records = run_engines(real_lines, rules, AS_OF).records
        views = Counter(r.inbox_view for r in records)
        assert views["attention"] == expected
        # Fix 9 (A13): 17 prompts before the false C242 label prompt was removed.
        assert (views["prompts"], views["repeats"]) == (16, 6)
        first = next(r for r in records if r.inbox_view == "attention")
        assert (first.type, first.entity, first.account) == ("pulse_gap", "C192", "279006")
    assert len(run_engines(real_lines, Rules(), AS_OF).records) == 47


# ----- account balances (A46, review of 22 Nov 2026) ----------------------------------------
def test_real_open_and_wrong_side_balances(real_lines: pd.DataFrame) -> None:
    """A46, account codes and account-level totals only, at the extract date (23 Oct 2026).

    Open balances: the "really open" accounts with no Pulse finding, 3 at 500K and 6 at 100K.
    Wrong-side balances: 6 accounts at 500K; C192 279006 has a gap, so its fact goes on the gap
    and 5 records are new. At 100K two more accounts. C192 179004 (an asset in credit) moved to
    the wrong side in mid-October 2026.
    """
    from app.services.pipeline import run_engines

    def accounts(records: list, type_: str) -> list[tuple[str, str, str]]:  # type: ignore
        return sorted((r.erp, r.entity, r.account) for r in records if r.type == type_)

    at_500k = run_engines(real_lines, Rules(), date(2026, 10, 23)).records
    assert accounts(at_500k, "open_balance") == [
        ("BPP", "C242", "34900001"), ("P20", "C192", "179003"), ("P20", "C192", "279014"),
    ]  # fmt: skip
    wrong = {r.account: r for r in at_500k if r.type == "wrong_side_balance"}
    assert accounts(at_500k, "wrong_side_balance") == [
        ("BPP", "C133", "34900011"), ("BPP", "C242", "34900009"), ("BPP", "C242", "48900004"),
        ("P20", "C192", "179004"), ("P20", "C192", "279002")]  # fmt: skip
    assert {a: round(r.exposure_eur / 1e6, 2) for a, r in wrong.items()} == {
        "48900004": 36.4,
        "279002": 2.96,
        "34900009": 2.8,
        "179004": -2.64,
        "34900011": 1.49,
    }
    assert all(r.suggested_class == "Required Adjustment Item" for r in wrong.values())
    crossed = wrong["179004"].first_signal
    assert (crossed.year, crossed.month) == (2026, 10) and 10 <= crossed.day <= 20
    gap = next(r for r in at_500k if r.type == "pulse_gap" and r.entity == "C192")
    assert gap.facts["wrong_side_balance"] == "yes" and "wrong_side_since" in gap.facts
    first = next(r for r in at_500k if r.inbox_view == "attention")
    assert (first.type, first.entity, first.account) == ("pulse_gap", "C192", "279006")
    opened = [r for r in at_500k if r.type == "open_balance"]
    assert all(r.today_detection and r.lead_days is None for r in opened), "listed, not blind"

    at_100k = run_engines(real_lines, Rules(materiality_eur=100_000), date(2026, 10, 23)).records
    more_open = [("BPP", "C133", "34900002"), ("P20", "C192", "279001"), ("P20", "C192", "279004")]
    assert accounts(at_100k, "open_balance") == sorted(
        [*accounts(at_500k, "open_balance"), *more_open]
    )
    more_wrong = [("BPP", "C242", "34900003"), ("P20", "C172", "279006")]
    assert accounts(at_100k, "wrong_side_balance") == sorted(
        [*accounts(at_500k, "wrong_side_balance"), *more_wrong]
    )


# ----- extract date (A38) -------------------------------------------------------------------
def test_real_extract_dates(real_payroll, real_fixed_assets) -> None:  # type: ignore[no-untyped-def]
    """Brief section 6 ageing dates: Payroll 23 Oct 2026, Fixed assets 2 Oct 2026."""
    from app.ingest import extract_dates

    payroll = extract_dates(real_payroll.lines)["Payroll"]
    fixed = extract_dates(real_fixed_assets.lines)["Fixed assets"]
    assert payroll == (date(2026, 10, 23), 0)  # 395 BPP lines one day off are tolerated
    assert fixed == (date(2026, 10, 2), 0)


def test_real_figures_at_the_extract_date(real_lines: pd.DataFrame) -> None:
    """A38: a live run uses the Payroll extract date (23 Oct 2026), not the run date.

    Aggregates only. With the balance check (A44), none of the 6 batches the 12-month limit
    (A15, #20) would raise at the extract date is still held in its account's balance, so no
    missing payment remains (C242's October 2026 batch is expected by 13 Nov, after the
    extract). 35 dated findings (5 of them wrong-side balances, A46), median 11 days; the C192
    gap still ranks first at 79.4 (A9, #18) and 4 groups stay above 500K. Before A44: 6 missing
    payments, 36 dated, median 11; between A44 and A46: 30 dated, median 8.5.
    """
    import statistics

    from app.services.pipeline import run_engines

    output = run_engines(real_lines, Rules(), date(2026, 10, 23))
    records = output.records
    assert not [r for r in records if r.type == "pulse_missing_payment"]
    assert (records[0].type, records[0].entity, round(records[0].score, 1)) == (
        "pulse_gap", "C192", 79.4)  # fmt: skip
    assert output.counts["exposure_groups_above"] == 4
    leads = [r.lead_days for r in records if r.lead_days is not None]
    # Fix 9 (A13): 35 before the false C242 label prompt was removed.
    assert (len(leads), statistics.median(leads)) == (34, 11)
