"""Posting-Day Error Sentinel (brief section 8, "Sentinel"; section 9 for S2 and S3).

- S1 outlier (specified): |amount_lc| at or above ``outlier_multiple`` x the median |amount_lc|
  of the same ERP, entity and account, skipping lines with amount_dc = 0 (FX valuations).
  As written it fires on routine bot payroll batches, so ``Rules.sentinel_s1_scope`` restricts
  it (open item 2): ``people_only`` (default, decided in #9), ``exempt_bot_upload`` or ``all``.
- S2 two currencies (ASSUMPTION): one document whose lines carry more than one document
  currency, or one company code whose lines carry more than one local currency.
- S3 currency code (ASSUMPTION): a document currency that is not an ISO 4217 code, or an amount
  copied unconverted (document currency differs from local currency but the amounts are equal).

Every check runs on the posting date of the line, so the finding exists on posting day.
"""

from __future__ import annotations

import pandas as pd

from app.engines import doc_ref, is_person, make_record
from app.schemas import ExceptionRecord, Rules

# ISO 4217 active codes (data, not a threshold).
ISO_CURRENCIES = frozenset(
    """AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN
    BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD
    FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY
    KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP
    MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR
    RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT
    TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW
    ZWL""".split()  # noqa: SIM905
)
UNCONVERTED_MIN_AMOUNT = 1.0  # ignore rounding residues below one unit


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


def two_currency_alerts(lines: pd.DataFrame) -> list[ExceptionRecord]:
    """S2 (ASSUMPTION): a document in two document currencies; an entity in two local ones."""
    records = []
    with_dc = lines[lines["currency_dc"].notna()]
    per_doc = with_dc.groupby(["erp", "entity", "account", "year", "document_no"], sort=False)
    for (_, _, _, year, number), group in per_doc:
        currencies = sorted(set(group["currency_dc"]))
        if len(currencies) < 2:
            continue
        ref = doc_ref(year, number)
        first = min(group["posting_date"])
        records.append(
            make_record(
                type_="sentinel_two_currencies",
                lines=group,
                title=f"One document posted in {' and '.join(currencies)}",
                exposure_eur=float(group["amount_eur"].abs().max()),
                facts={
                    "rule": "S2: one document carries more than one document currency",
                    "currencies": ", ".join(currencies),
                    "lines": len(group),
                    "posting_date": first,
                },
                evidence=[ref],
                first_signal=first,
                id_keys=[ref],
                suggested_class="Required Adjustment Item",
            )
        )
    for (_, _), group in lines.groupby(["erp", "entity"], sort=False):
        currencies = sorted(set(group["currency_lc"]))
        if len(currencies) < 2:
            continue
        minority = group[group["currency_lc"] != group["currency_lc"].mode().iloc[0]]
        refs = sorted({doc_ref(y, n) for y, n in zip(minority["year"], minority["document_no"],
                                                       strict=True)})  # fmt: skip
        first = min(minority["posting_date"])
        records.append(
            make_record(
                type_="sentinel_two_currencies",
                lines=minority,
                title=f"Company code books in two local currencies ({', '.join(currencies)})",
                exposure_eur=float(minority["amount_eur"].sum()),
                facts={
                    "rule": "S2: one company code carries more than one local currency",
                    "currencies": ", ".join(currencies),
                    "lines": len(minority),
                    "posting_date": first,
                },
                evidence=refs,
                first_signal=first,
                id_keys=["local-currency"],
                suggested_class="Required Adjustment Item",
            )
        )
    return records


def currency_code_alerts(lines: pd.DataFrame) -> list[ExceptionRecord]:
    """S3 (ASSUMPTION): invalid currency code, or an amount copied without conversion."""
    dc = lines["currency_dc"].fillna("")
    invalid = lines[(dc != "") & ~dc.isin(ISO_CURRENCIES)]
    unconverted = lines[
        (dc != "")
        & (dc != lines["currency_lc"])
        & (lines["amount_dc"].abs() >= UNCONVERTED_MIN_AMOUNT)
        & ((lines["amount_dc"] - lines["amount_lc"]).abs() < 0.005)
    ]
    records = []
    for kind, frame in (("invalid", invalid), ("unconverted", unconverted)):
        for (_, _, _, year, number), group in frame.groupby(
            ["erp", "entity", "account", "year", "document_no"], sort=False
        ):
            top = group.iloc[0]
            ref = doc_ref(year, number)
            if kind == "invalid":
                title = f"Unknown currency code '{top['currency_dc']}'"
                rule = "S3: document currency is not an ISO 4217 code"
            else:
                title = (
                    f"{top['currency_dc']} amount equals the {top['currency_lc']} amount: "
                    "not converted?"
                )
                rule = "S3: document and local currency differ but the amounts are equal"
            records.append(
                make_record(
                    type_="sentinel_currency_code",
                    lines=group,
                    title=title,
                    exposure_eur=float(group["amount_eur"].sum()),
                    facts={
                        "rule": rule,
                        "currency_dc": str(top["currency_dc"]),
                        "currency_lc": str(top["currency_lc"]),
                        "amount_dc": float(top["amount_dc"]),
                        "amount_lc": float(top["amount_lc"]),
                        "posting_date": top["posting_date"],
                    },
                    evidence=[ref],
                    first_signal=top["posting_date"],
                    id_keys=[ref, kind],
                    suggested_class="Required Adjustment Item",
                )
            )
    return records


def run_sentinel(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """S1 to S3 over every in-scope line. (S5, reversal mismatch, is P1 and not built.)"""
    return outlier_alerts(lines, rules) + two_currency_alerts(lines) + currency_code_alerts(lines)
