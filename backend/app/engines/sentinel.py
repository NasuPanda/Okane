"""Posting-Day Error Sentinel (brief section 8, "Sentinel"; section 9 for S2 and S3).

- S1 outlier (specified): |amount_lc| at or above ``outlier_multiple`` x the median |amount_lc|
  of the same ERP, entity and account, skipping lines with amount_dc = 0 (FX valuations).
  As written it fires on routine bot payroll batches, so ``Rules.sentinel_s1_scope`` restricts
  it (open item 2): ``people_only`` (default, decided in #9), ``exempt_bot_upload`` or ``all``.
- S2 two currencies (decided in #10, docs/ASSUMPTIONS.md A4): the same amount posted in
  different document currencies on the same ERP, entity, account and posting date, with
  |amount_dc| at or above ``Rules.sentinel_s2_min_amount``. One record per such group.
- S3 currency code (decided in #10, A5): a document currency that is not an ISO 4217 code, or
  one the euro had already replaced on the posting date.

Every check runs on the posting date of the line, so the finding exists on posting day.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.engines import doc_ref, doc_refs, is_person, make_record
from app.schemas import ExceptionRecord, Rules

# ISO 4217 active codes (data, not a threshold). BGN is in REPLACED_BY_EURO instead.
ISO_CURRENCIES = frozenset(
    """AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BRL BSD BTN
    BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD
    FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY
    KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP
    MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR
    RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT
    TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW
    ZWL""".split()  # noqa: SIM905
)
# National currencies the euro replaced, with the first day they could no longer be used
# (data, not a threshold). The 1999 and 2001 joiners kept their old units until the end of
# 2001; later joiners switched on their changeover day.
_FIRST_WAVE = "ATS BEF DEM ESP FIM FRF GRD IEP ITL LUF NLG PTE".split()  # noqa: SIM905
REPLACED_BY_EURO: dict[str, date] = {
    **dict.fromkeys(_FIRST_WAVE, date(2002, 1, 1)),
    "SIT": date(2007, 1, 1),
    "CYP": date(2008, 1, 1),
    "MTL": date(2008, 1, 1),
    "SKK": date(2009, 1, 1),
    "EEK": date(2011, 1, 1),
    "LVL": date(2014, 1, 1),
    "LTL": date(2015, 1, 1),
    "HRK": date(2023, 1, 1),
    "BGN": date(2026, 1, 1),
}


def _in_scope(user: object, scope: str) -> bool:
    if scope == "people_only":
        return is_person(user)
    if scope == "exempt_bot_upload":
        return not (isinstance(user, str) and user.upper().startswith("BOT_UPLOAD"))
    return True


def outlier_hits(lines: pd.DataFrame, rules: Rules, scope: str | None = None) -> pd.DataFrame:
    """S1 hits (one row per line) with the account median and the multiple."""
    scope = scope or rules.sentinel_s1_scope
    work = lines[lines["amount_dc"] != 0].copy()
    work["abs_lc"] = work["amount_lc"].abs()
    work["median_abs_lc"] = work.groupby(["erp", "entity", "account"])["abs_lc"].transform("median")
    work = work[work["median_abs_lc"] > 0]
    work["multiple"] = work["abs_lc"] / work["median_abs_lc"]
    hits = work[work["abs_lc"] >= rules.outlier_multiple * work["median_abs_lc"]]
    in_scope = hits["user_name"].map(lambda u: _in_scope(u, scope)).astype(bool)
    return hits.loc[in_scope]


def outlier_alerts(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """S1: one record per document and account."""
    hits = outlier_hits(lines, rules)
    records = []
    for (_, _, _, year, number), group in hits.groupby(
        ["erp", "entity", "account", "year", "document_no"], sort=False
    ):
        top = group.loc[group["abs_lc"].idxmax()]
        ref = doc_ref(year, number)
        who = "a person" if is_person(top["user_name"]) else "an automated posting"
        records.append(
            make_record(
                type_="sentinel_outlier",
                lines=group,
                title=f"Amount {top['multiple']:,.0f}x the account's usual size, posted by {who}",
                exposure_eur=float(group["amount_eur"].sum()),
                facts={
                    "rule": f"S1: amount at or above {rules.outlier_multiple:g}x the median",
                    "amount_lc": float(top["amount_lc"]),
                    "currency_lc": str(top["currency_lc"]),
                    "median_abs_lc": float(top["median_abs_lc"]),
                    "multiple": round(float(top["multiple"]), 1),
                    "outlier_multiple": rules.outlier_multiple,
                    "posted_by": "person" if is_person(top["user_name"]) else "automated",
                    "posting_date": top["posting_date"],
                    "scope": rules.sentinel_s1_scope,
                },
                evidence=[ref],
                first_signal=top["posting_date"],
                id_keys=[ref],
                suggested_class="Required Adjustment Item",
            )
        )
    return records


def two_currency_alerts(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """S2: the same amount posted in different currencies on one day (one record per group)."""
    minimum = rules.sentinel_s2_min_amount
    work = lines[lines["currency_dc"].notna() & (lines["amount_dc"].abs() >= minimum)].copy()
    # ASSUMPTION (A4): "the same amount" is compared in whole units. A currency without
    # decimals cannot repeat the cents of one with them, so a cent-level match misses the slip.
    work["figure"] = work["amount_dc"].abs().round(0)
    records = []
    for (_, _, _, posted, figure), group in work.groupby(
        ["erp", "entity", "account", "posting_date", "figure"], sort=False
    ):
        currencies = sorted(set(group["currency_dc"]))
        if len(currencies) < 2:
            continue
        records.append(
            make_record(
                type_="sentinel_two_currencies",
                lines=group,
                title=f"Same amount posted in {' and '.join(currencies)} on the same day",
                exposure_eur=float(group["amount_eur"].abs().max()),
                facts={
                    "rule": (
                        f"S2: the same amount of at least {minimum:,.0f} posted in different "
                        "currencies on one day"
                    ),
                    "currencies": ", ".join(currencies),
                    "amount_dc": float(figure),
                    "min_amount": minimum,
                    "lines": len(group),
                    "posting_date": posted,
                },
                evidence=doc_refs(group),
                first_signal=posted,
                # The group's own key, so a decision survives when one of its lines is cleared.
                id_keys=[posted.isoformat(), f"{figure:.0f}"],
                suggested_class="Required Adjustment Item",
            )
        )
    return records


def _replaced_by_euro(code: object, posted: object) -> bool:
    since = REPLACED_BY_EURO.get(str(code))
    return since is not None and isinstance(posted, date) and posted >= since


def currency_code_alerts(lines: pd.DataFrame) -> list[ExceptionRecord]:
    """S3: a document currency that is not an ISO code, or that the euro had replaced."""
    dc = lines["currency_dc"].fillna("")
    replaced = pd.Series(
        [_replaced_by_euro(c, d) for c, d in zip(dc, lines["posting_date"], strict=True)],
        index=lines.index,
        dtype=bool,
    )
    unknown = (dc != "") & ~dc.isin(ISO_CURRENCIES) & ~dc.isin(REPLACED_BY_EURO.keys())
    records = []
    for kind, frame in (("replaced", lines[replaced]), ("unknown", lines[unknown])):
        for (_, _, _, year, number), group in frame.groupby(
            ["erp", "entity", "account", "year", "document_no"], sort=False
        ):
            top = group.iloc[0]
            code = str(top["currency_dc"])
            ref = doc_ref(year, number)
            facts: dict[str, object] = {}
            if kind == "replaced":
                title = f"{code} was replaced by the euro"
                facts["rule"] = (
                    "S3: the document currency had been replaced by the euro by the posting date"
                )
                facts["euro_since"] = REPLACED_BY_EURO[code]
            else:
                title = f"'{code}' is not a valid currency code"
                facts["rule"] = "S3: the document currency is not an ISO currency code"
            facts |= {
                "currency_dc": code,
                "currency_lc": str(top["currency_lc"]),
                "amount_dc": float(top["amount_dc"]),
                "amount_lc": float(top["amount_lc"]),
                "lines": len(group),
                "posting_date": top["posting_date"],
            }
            records.append(
                make_record(
                    type_="sentinel_currency_code",
                    lines=group,
                    title=title,
                    exposure_eur=float(group["amount_eur"].sum()),
                    facts=facts,
                    evidence=[ref],
                    first_signal=top["posting_date"],
                    # Both kinds keep the key "invalid" so earlier decisions keep their id.
                    id_keys=[ref, "invalid"],
                    suggested_class="Required Adjustment Item",
                )
            )
    return records


def run_sentinel(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """S1 to S3 over every in-scope line. (S5, reversal mismatch, is P1 and not built.)"""
    return (
        outlier_alerts(lines, rules)
        + two_currency_alerts(lines, rules)
        + currency_code_alerts(lines)
    )
