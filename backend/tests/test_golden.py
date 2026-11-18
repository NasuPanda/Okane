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
    assert gap.title == "Liability 1.84M above expected"
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


def test_real_typos_find_known_misspellings(real_lines: pd.DataFrame) -> None:
    found = {str(r.facts.get("found")).lower() for r in run_typos(real_lines, Rules())}
    assert {"auzahl", "ursaaf"} <= found


def test_real_miner_payroll(real_lines: pd.DataFrame) -> None:
    """A7 (decided, #14), aggregates only: 6 patterns reach the Inbox at score 12 (16 at 6, 4 at
    20); the demo card's top pattern scores 42 (42 months x 1 company code) on BPP C242."""
    rules = Rules()
    records = run_miner(real_lines, rules)
    assert len(records) == 6
    assert all(r.workgroup == "Payroll" for r in records)
    assert all(float(r.facts["miner_score"]) >= 12 for r in records)
    lower = rules.model_copy(update={"miner_min_score": 6})
    assert len(run_miner(real_lines, lower)) == 16
    assert len(run_miner(real_lines, rules.model_copy(update={"miner_min_score": 20}))) == 4
    top = records[0]
    assert (top.erp, top.entity, top.account) == ("BPP", "C242", "48900002")
    assert (top.facts["miner_score"], top.facts["months"], top.facts["entities"]) == (42, 42, 1)
    assert top.facts["lines"] == 111
    # No top pattern names a correction, so the card stays a hypothesis.
    assert not any("correction" in str(r.facts["pattern"]) for r in records)


def test_real_miner_fixed_assets(real_fixed_assets: object) -> None:
    """A3, A7: Fixed assets feed the Miner. Invariants only: the counts were not measured,
    because the workbook was not available when #15 was built (see the PR)."""
    lines = real_fixed_assets.lines  # type: ignore[attr-defined]
    rules = Rules()
    records = run_miner(lines, rules)
    for record in records:
        assert record.workgroup == "Fixed assets"
        assert float(record.facts["miner_score"]) >= rules.miner_min_score
        assert float(record.facts["months"]) >= rules.miner_min_repeats
        assert record.evidence
    scores = [float(r.facts["miner_score"]) for r in records]
    assert scores == sorted(scores, reverse=True)


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
    assert sum(m.matched for m in c192.matches) == 17
    records = [r for r in synthetic_pulse.records if r.entity == "C192"]
    assert sum(r.type == "pulse_gap" for r in records) == 1
    unpaid = sorted(r.facts["batch_period"] for r in records if r.type == "pulse_missing_payment")
    assert unpaid == ["2025-05", "2025-06"]
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
    assert [(r.entity, r.facts["currencies"], r.facts["lines"]) for r in two] == [
        ("C132", "EUR, RWF", 2)
    ]
    typos = {
        (r.facts.get("found"), r.facts.get("suggestion")) for r in run_typos(synthetic_lines, rules)
    }
    assert {("Auzahl", "Auszahl"), ("URSAAF", "URSSAF"), ("trnasit", "transit")} <= typos


def test_synthetic_miner_planted_pattern_and_near_miss(synthetic_lines: pd.DataFrame) -> None:
    """A7 (decided, #14): the planted pattern (6 months x 2 company codes = 12) is found; the
    near-miss (5 x 2 = 10) and the older lines without a header text are not."""
    rules = Rules()
    records = run_miner(synthetic_lines, rules)
    assert len(records) == 1
    top = records[0]
    assert (top.erp, top.entity, top.account) == ("P20", "C192", "279030")
    assert (top.facts["months"], top.facts["entities"], top.facts["miner_score"]) == (6, 2, 12)
    assert top.facts["entity_list"] == "C132, C192"
    assert top.facts["pattern"] == "correction <name> reclass to # #/#"
    assert top.title == "Repeated manual posting: 6 months"
    assert top.first_signal == date(2026, 10, 21)
    assert len(top.evidence) == 8
    lower = run_miner(synthetic_lines, rules.model_copy(update={"miner_min_score": 10}))
    assert {(r.account, r.facts["miner_score"]) for r in lower} == {("279030", 12), ("279030", 10)}
    assert [r for r in lower if r.account == "279002"] == [], "no header text, no pattern"


# ----- lead time (A8, decided in #16) -------------------------------------------------------
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
    assert outlier.facts["lead_badge"] == "Caught 16 days before the close review"
    # Pulse: the unpaid May 2025 batch. First signal the day after expected-by (Wed 22 Jul
    # 2025), Monday run 28 Jul; the 365-day ageing rule shows it 30 May 2026.
    may = next(
        r for r in records
        if r.type == "pulse_missing_payment" and r.facts["batch_period"] == "2025-05"
    )  # fmt: skip
    assert may.first_signal == date(2025, 7, 22)
    assert may.facts["okane_run_date"] == "2025-07-28"
    assert may.today_detection == date(2026, 5, 30)
    assert (may.lead_days, may.facts["lead_days_daily"]) == (306, 312)
    assert may.facts["lead_badge"] == "Caught 306 days before the 365-day ageing rule"
    # Blind spots and the KPI median ("median days earlier", weekly).
    blind = [r for r in records if r.today_detection is None]
    assert {r.type for r in blind} == {"pulse_gap", "pulse_missing_batch", "miner_cluster"}
    assert all(r.facts["lead_badge"] == "Today's process would miss this" for r in blind)
    leads = [r.lead_days for r in records if r.lead_days is not None]
    assert (len(leads), statistics.median(leads)) == (12, 27.5)


def test_real_lead_time_median(real_lines: pd.DataFrame) -> None:
    """A8, aggregates only: weekly median 17.5 days earlier over 62 dated findings, 9 blind."""
    import statistics

    from app.services.pipeline import run_engines

    records = run_engines(real_lines, Rules(), AS_OF).records
    leads = [r.lead_days for r in records if r.lead_days is not None]
    assert (len(leads), statistics.median(leads)) == (62, 17.5)
    assert sum(r.today_detection is None for r in records) == 9
    assert min(leads) >= 0
    daily = [float(r.facts["lead_days_daily"]) for r in records if r.lead_days is not None]
    assert statistics.median(daily) == 21


def test_real_c192_september_batch_lead_time(real_lines: pd.DataFrame) -> None:
    """The original's example: the C192 September 2026 batch, still unpaid in the extract.

    Brief section 8 quotes its accrual date (29 Sep 2026) and expected-by date (21 Nov 2026);
    the analysis date is pinned to Monday 23 Nov 2026, after it falls due.
    """
    from app.services.pipeline import run_engines

    records = run_engines(real_lines, Rules(), date(2026, 11, 23)).records
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
    assert hit.facts["lead_badge"] == f"Caught {hit.lead_days} days before the close review"


def test_real_top_exception_is_c192_gap(real_lines: pd.DataFrame) -> None:
    """Demo step 4 opens the top exception: the C192 social security gap."""
    from app.services.pipeline import run_engines

    output = run_engines(real_lines, Rules(), AS_OF)
    top = output.records[0]
    assert (top.type, top.entity, top.account) == ("pulse_gap", "C192", "279006")
    assert output.counts["exposure_groups_above"] == 4
