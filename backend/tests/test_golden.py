"""Golden values.

Two halves:

- ``test_real_*``: the brief's "Expected" values on the real workbooks (section 8). They skip
  automatically when ``data/inbox/`` has no Payroll workbook (always the case in CI).
- ``test_synthetic_*``: the same rules on the synthetic workbooks, whose planted cases are
  documented in ``scripts/generate_sample_data.py``. They always run, so CI is meaningful.

Only aggregates are asserted; no row-level real data is printed or stored.
"""

from __future__ import annotations

import pandas as pd
import pytest

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
