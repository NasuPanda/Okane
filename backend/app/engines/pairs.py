"""Exact offsetting pairs (brief section 8, "Exact pairs").

Rule: key = ERP, CoCd, Account, document currency and |amount_dc| rounded to cents. Within a
key, rank the positive lines and the negative lines by posting date, then pair equal ranks.
Lines with amount_dc = 0 are never paired. Paired lines cancel each other and fold away in the
exposure view; they produce no exception on their own.

Expected (real data): 476 paired Payroll lines.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PAIR_KEY = ["erp", "entity", "account", "currency_dc", "abs_dc"]


def find_pairs(lines: pd.DataFrame) -> pd.Series:
    """Return a ``pair_id`` per line (``<NA>`` for unpaired lines), indexed like ``lines``."""
    work = lines[["line_id", "erp", "entity", "account", "currency_dc", "amount_dc",
                  "posting_date"]].copy()  # fmt: skip
    work["abs_dc"] = work["amount_dc"].abs().round(2)
    work["sign"] = np.sign(work["amount_dc"])
    work = work[work["sign"] != 0].sort_values(["posting_date", "line_id"])
    work["currency_dc"] = work["currency_dc"].fillna("")
    work["rank"] = work.groupby([*PAIR_KEY, "sign"]).cumcount()
    debit = work[work["sign"] > 0][[*PAIR_KEY, "rank", "line_id"]]
    credit = work[work["sign"] < 0][[*PAIR_KEY, "rank", "line_id"]]
    matched = debit.merge(credit, on=[*PAIR_KEY, "rank"], suffixes=("_d", "_c"))
    matched["pair_id"] = np.arange(len(matched))
    pair_of = pd.concat(
        [
            matched.set_index("line_id_d")["pair_id"],
            matched.set_index("line_id_c")["pair_id"],
        ]
    )
    return lines["line_id"].map(pair_of).astype("Int64")


def paired_count(lines: pd.DataFrame) -> int:
    """Number of lines that belong to an exact pair."""
    return int(find_pairs(lines).notna().sum())
