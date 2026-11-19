"""Generate small synthetic Payroll and Fixed assets workbooks for demos and tests.

The workbooks use the same sheet names and column layout as the real extracts (brief
section 6) but every value is invented. They are written to a folder that is git-ignored
(spreadsheets are never committed): ``data/sample/`` via ``make generate-sample-data``, or a
pytest temp folder via ``backend/tests/conftest.py``.

Planted cases (each one is asserted in backend/tests/test_golden.py):

- C192 P20 279006 (payment profile 1): monthly "PayrollYYYYMM" batches Jan 2025 - Sep 2026,
  paid ~30 days after period end; Aug 2025 has no batch (missing batch); May and Jun 2025 are
  never paid (missing payments, gap); Aug 2026 is a 4x spike; the Feb 2026 payment is labelled
  "Jan'2026" (label mismatch); one payment text says "URSAAF" (typo).
- C242 BPP 34900015 (payment profile 2): monthly GX batches "Auszahl. Rente_MM.YYYY" from
  BOT_UPLOAD_002, settled by 3-4 bank (TX) lines within 14 days; one text misspelt "Auzahl.".
- Exact offsetting pairs on C192 279014 and in Fixed assets.
- Sentinel: a person-posted outlier (USER_901) and a bot-posted outlier; the same amount
  posted in EUR and RWF on one day in Payroll (C132) and in EUR and PLN on one day in Fixed
  assets (C219); a withdrawn currency code in Payroll (C141) and a
  currency the euro replaced in Fixed assets (C218).
- Miner (A7): USER_045 posts the same header text ("Corr. ...") on 279030 in six months
  and two entities (score 6 x 2 = 12, found); USER_903 repeats another header text in five
  months and two entities (score 10, a near-miss). The older USER_045 lines on 279002 have
  no header text, so they are not a pattern.
- Pension-type account with "Actual ageing ( No Overdue )" (exempt from the 365-day rule).
"""

from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PAYROLL_AGEING_DATE = date(2026, 10, 23)
FIXED_ASSETS_AGEING_DATE = date(2026, 10, 2)
RATES = {"EUR": 1.0, "HUF": 366.2, "XOF": 655.957, "AUD": 1.6297, "JPY": 162.5, "PLN": 4.29}
NO_OVERDUE = "Actual ageing ( No Overdue )"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sep", "Oct", "Nov", "Dec"]

PAYROLL_COLUMNS = [
    "CoCd", "Account", "Description", "DocumentNo", "ItemNo in Doc", "DocumentType", "Year",
    "Period", "Ammount in DC", "Curr.", "Amount in LC", "LCurr", "Amount in EUR",
    "EURCurrencyExchangeRate", "EUR Absolute", "PK", "Debit Credit Indicator",
    "Internal/External", "Pstng Date", "Doc Date", "Entry Date", "User Name", "Text",
    "Doc.Header Text", "Profit Ctr", "Clearing", "Clrng Doc.", "Reference", "Tr.Prt",
    "WBS Elem.", "Assignment", "ItemNo in  Purch Doc.", "ERP System", "Work Group",
    "GL Account Categories", "OIM Category Number", "Ageing Allowed (Days)",
    "Due/Not Due Aged/Not Aged", "Overdue Amount ABS", "Current Ageing (Days)",
    "Current Ageing (Range)",
]  # fmt: skip
FIXED_ASSET_COLUMNS = [
    "CoCd", "Account", "Description", "DocumentNo", "Item", "Type", "Year", "Period",
    "Amount in DC", "Curr.", "Amount in Local Currency", "Lcurr", "Pstng Date", "Doc. Date",
    "User Name", "Text", "Doc.Header Text", "Reference", "Tr.Prt", "Assignment",
    "Ageing(No of days)", "Reversal",
]  # fmt: skip


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def months_between(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    out, current = [], start
    while current <= end:
        out.append(current)
        current = add_months(*current, 1)
    return out


@dataclass
class DocCounter:
    """Ten-digit document numbers; some start with zeros on purpose."""

    prefix: str
    counters: dict[int, int] = field(default_factory=dict)

    def next(self, year: int) -> str:
        self.counters[year] = self.counters.get(year, 0) + 1
        return f"{self.prefix}{self.counters[year]:0{10 - len(self.prefix)}d}"


class PayrollSheet:
    """Accumulates rows for one Payroll sheet (P20 or BPP)."""

    def __init__(self, erp: str) -> None:
        self.erp = erp
        self.rows: list[dict[str, object]] = []

    def add(
        self,
        cocd: str,
        account: str,
        description: str,
        doc: str,
        item: int,
        doc_type: str,
        posted: date,
        amount_lc: float,
        user: str,
        text: str,
        lcurr: str = "EUR",
        curr: str | None = None,
        amount_dc: float | None = None,
        allowed: str = "365",
        partner: str | None = None,
        reference: str = "",
        header: str = "",
    ) -> None:
        rate = RATES[lcurr]
        curr = curr or lcurr
        amount_dc = amount_lc if amount_dc is None else amount_dc
        eur = round(amount_lc / rate, 2)
        age = (PAYROLL_AGEING_DATE - posted).days
        aged = allowed != NO_OVERDUE and age > int(allowed)
        self.rows.append(
            {
                "CoCd": cocd, "Account": account, "Description": description,
                "DocumentNo": doc, "ItemNo in Doc": item, "DocumentType": doc_type,
                "Year": posted.year, "Period": posted.month, "Ammount in DC": amount_dc,
                "Curr.": curr, "Amount in LC": amount_lc, "LCurr": lcurr, "Amount in EUR": eur,
                "EURCurrencyExchangeRate": rate, "EUR Absolute": abs(eur),
                "PK": 50 if amount_lc < 0 else 40,
                "Debit Credit Indicator": "H" if amount_lc < 0 else "S",
                "Internal/External": "External", "Pstng Date": posted.isoformat(),
                "Doc Date": posted.isoformat(), "Entry Date": posted.isoformat(),
                "User Name": user, "Text": text, "Doc.Header Text": header, "Profit Ctr": "PC100",
                "Clearing": "", "Clrng Doc.": None, "Reference": reference,
                "Tr.Prt": partner if self.erp == "BPP" else None, "WBS Elem.": 0,
                "Assignment": "", "ItemNo in  Purch Doc.": 0, "ERP System": self.erp,
                "Work Group": "Payroll", "GL Account Categories": "Payroll liabilities",
                "OIM Category Number": 6, "Ageing Allowed (Days)": allowed,
                "Due/Not Due Aged/Not Aged": "Aged more than 365 days" if aged else "Not Aged",
                "Overdue Amount ABS": abs(eur) if aged else 0.0,
                "Current Ageing (Days)": age,
                "Current Ageing (Range)": ">365" if age > 365 else "0-365",
            }
        )  # fmt: skip

    def frame(self) -> pd.DataFrame:
        frame = pd.DataFrame(self.rows, columns=PAYROLL_COLUMNS)
        if self.erp == "P20":
            frame = frame.drop(columns=["Tr.Prt"])
        return frame


def _split(total: float, parts: int) -> list[float]:
    """Split an amount into uneven parts that add up exactly to the cent."""
    weights = [0.4, 0.3, 0.2, 0.1][:parts] if parts <= 4 else [1 / parts] * parts
    scale = sum(weights)
    amounts = [round(total * w / scale, 2) for w in weights]
    amounts[-1] = round(total - sum(amounts[:-1]), 2)
    return amounts


C192_BATCHES: dict[tuple[int, int], float] = {
    (2025, 1): 610_400.00, (2025, 2): 598_250.40, (2025, 3): 640_120.10, (2025, 4): 655_300.00,
    (2025, 5): 702_310.55, (2025, 6): 688_940.20, (2025, 7): 615_000.00,
    (2025, 9): 633_450.75, (2025, 10): 590_880.00, (2025, 11): 612_300.30,
    (2025, 12): 645_700.00, (2026, 1): 601_222.10, (2026, 2): 615_900.00,
    (2026, 3): 628_400.60, (2026, 4): 642_010.00, (2026, 5): 610_550.25,
    (2026, 6): 598_600.00, (2026, 7): 620_878.00, (2026, 8): 2_531_445.87,
    (2026, 9): 513_823.36,
}  # fmt: skip
C192_UNPAID = {(2025, 5), (2025, 6), (2026, 9)}
C192_LABEL_SHIFT = {(2026, 2): (2026, 1)}  # paid for Feb 2026 but labelled January 2026
C192_TYPO = {(2026, 3)}


def build_c192(p20: PayrollSheet, docs: DocCounter) -> None:
    """Profile 1: social security batches and their payments."""
    cocd, account, name = "C192", "279006", "Social security liabilities"
    for index, ((year, month), amount) in enumerate(C192_BATCHES.items()):
        end = month_end(year, month)
        posted = end - timedelta(days=1)
        doc = docs.next(year)
        for item, part in enumerate(_split(-amount, 4), start=1):
            p20.add(cocd, account, name, doc, item, "P0", posted, part, "BOT_UPLOAD_001",
                    f"Payroll{year}{month:02d}")  # fmt: skip
        if (year, month) in C192_UNPAID:
            continue
        paid_on = end + timedelta(days=28 + index % 10)  # lags of 28 to 37 days
        label_year, label_month = C192_LABEL_SHIFT.get((year, month), (year, month))
        agency = "URSAAF" if (year, month) in C192_TYPO else "URSSAF"
        label = f"{agency}/ASSEDIC SITE03 - {MONTHS[label_month - 1]}'{label_year}"
        pay_doc = docs.next(paid_on.year)
        payment = round(amount * 0.997, 2)
        for item, part in enumerate(_split(payment, 2), start=1):
            p20.add(cocd, account, name, pay_doc, item, "P1", paid_on, part, "BOT_RPA_003", label)
    # a few old unexplained debits on the same account (counted by the old ageing rule)
    for i, amount in enumerate([1_250.0, 880.5, 2_400.0]):
        p20.add(cocd, account, name, docs.next(2023), 1, "SA", date(2023, 3 + i, 10), amount,
                "USER_031", f"Manual adj NAME{100 + i} social charges")  # fmt: skip


def build_payroll_p20(docs: DocCounter) -> PayrollSheet:
    p20 = PayrollSheet("P20")
    build_c192(p20, docs)
    # Exact offsetting pairs on 279014, aged > 365 days: loud for the old rule, net zero.
    for i in range(6):
        posted = date(2024, 1 + i, 15)
        amount = 12_000.0 + 1_000 * i
        p20.add("C192", "279014", "Payroll clearing", docs.next(2024), 1, "P0", posted, -amount,
                "BOT_UPLOAD_001", f"Payroll2024{1 + i:02d}")  # fmt: skip
        p20.add("C192", "279014", "Payroll clearing", docs.next(2024), 1, "P1",
                posted + timedelta(days=20), amount, "BOT_RPA_003", "Net pay transfer")  # fmt: skip
    # Routine lines for the S1 median, recent so they are not overdue.
    for i in range(12):
        p20.add("C192", "279002", "Payroll deductions", docs.next(2026), 1, "P0",
                date(2026, 9, 1) + timedelta(days=i), -(1_500.0 + 50 * i), "BOT_UPLOAD_001",
                f"Deduction batch {i}")  # fmt: skip
    # S1: a person-posted outlier (>1000x the account median) and a bot-posted one.
    p20.add("C192", "279002", "Payroll deductions", docs.next(2026), 1, "SA", date(2026, 10, 5),
            -9_870_000.0, "USER_901", "Reclass deductions NAME122")  # fmt: skip
    p20.add("C192", "279002", "Payroll deductions", docs.next(2026), 1, "P0", date(2026, 10, 6),
            -2_150_000.0, "BOT_UPLOAD_001", "Deduction batch bulk")  # fmt: skip
    # Miner: the same manual correction in four consecutive months.
    for month in (5, 6, 7, 8):
        doc = docs.next(2026)
        posted = date(2026, month, 20)
        p20.add("C192", "279002", "Payroll deductions", doc, 1, "SA", posted, 3_100.0 + month,
                "USER_045", f"Manual correction NAME{200 + month} reclass to 279006")  # fmt: skip
        p20.add("C192", "279002", "Payroll deductions", doc, 2, "SA", posted, -(3_100.0 + month),
                "USER_045", f"Manual correction NAME{200 + month} reclass to 279006")  # fmt: skip
    # Miner (A7): the same header text by one person in six months and two entities (score
    # 12), and a near-miss in five months and two entities (score 10). Recent and one-sided, so
    # no pairs, no ageing and no outliers.
    for month in range(5, 11):
        for cocd in ("C192", "C132") if month >= 9 else ("C192",):
            p20.add(cocd, "279030", "Payroll corrections", docs.next(2026), 1, "SA",
                    date(2026, month, 21), 2_000.0 + 37 * month, "USER_045",
                    "Reclass to social security",
                    header=f"Corr. NAME{210 + month} reclass to 279006 {month:02d}/2026")  # fmt: skip
    for month in range(5, 10):
        for cocd in ("C192", "C132") if month == 9 else ("C192",):
            p20.add(cocd, "279030", "Payroll corrections", docs.next(2026), 1, "SA",
                    date(2026, month, 24), 900.0 + 11 * month, "USER_903", "Accrual true-up",
                    header=f"True-up accrual {month:02d}/2026")  # fmt: skip
    # Old aged debit balance on 179003 (an exposure group above 500K).
    for i, amount in enumerate([310_000.0, 245_500.0, 124_339.48]):
        p20.add("C192", "179003", "Employee receivables", docs.next(2023), 1, "SA",
                date(2023, 6 + i, 12), amount, "USER_031", "Advance NAME300")  # fmt: skip
    # Pension-type account: old, but exempt from the 365-day rule.
    for i in range(3):
        p20.add("C192", "279020", "Pension liabilities", docs.next(2022), 1, "P0",
                date(2022, 2 + i, 28), -(80_000.0 + i), "BOT_UPLOAD_001", "Pension accrual",
                allowed=NO_OVERDUE)  # fmt: skip
    # HUF entity with an aged balance between 100K and 500K EUR.
    for i in range(4):
        p20.add("C172", "279006", "Social security liabilities", docs.next(2024), 1, "P0",
                date(2024, 2 + i, 28), -(40_000.0 * 366.2 + i), "BOT_UPLOAD_001",
                f"Payroll2024{2 + i:02d}", lcurr="HUF")  # fmt: skip
    # S2: the same amount posted in EUR and in RWF on one day (equal in whole units only).
    p20.add("C132", "279006", "Social security liabilities", docs.next(2026), 1, "SA",
            date(2026, 9, 14), -4_200.40, "USER_077", "Social charges RW")  # fmt: skip
    p20.add("C132", "279006", "Social security liabilities", docs.next(2026), 1, "SA",
            date(2026, 9, 14), -2.80, "USER_077", "Social charges RW", curr="RWF",
            amount_dc=-4_200.0)  # fmt: skip
    # S3: a withdrawn currency code (GHC, not an ISO code any more).
    p20.add("C141", "279006", "Social security liabilities", docs.next(2026), 1, "SA",
            date(2026, 10, 2), -18_450.0, "USER_088", "SSNIT contribution Sep",
            curr="GHC", amount_dc=-1_845.0)  # fmt: skip
    return p20


def build_payroll_bpp(docs: DocCounter) -> PayrollSheet:
    bpp = PayrollSheet("BPP")
    cocd, account, name = "C242", "34900015", "Accrued payroll"
    batches = {(2026, 6): 4_088_120.40, (2026, 7): 4_091_302.21, (2026, 8): 4_102_550.00,
               (2026, 9): 4_095_000.00}  # fmt: skip
    for (year, month), amount in batches.items():
        accrual = date(year, month, 25)
        word = "Auzahl." if (year, month) == (2026, 7) else "Auszahl."
        text = f"{word} Rente_{month:02d}.{year}"
        doc = docs.next(year)
        for item, part in enumerate(_split(-amount, 3), start=1):
            bpp.add(cocd, account, name, doc, item, "GX", accrual, part, "BOT_UPLOAD_002", text,
                    partner="TP-001")  # fmt: skip
        paid = amount if month == 9 else round(amount * 0.9999, 2)
        parts = 4 if month == 8 else 3
        for i, part in enumerate(_split(paid, parts)):
            bpp.add(cocd, account, name, docs.next(year), 1, "TX",
                    accrual + timedelta(days=3 + 3 * i), part, "BOT_RPA_002",
                    "Bank statement pension payout", partner="TP-001")  # fmt: skip
    # An aged, large credit balance (top exposure group in the real data has the same shape).
    for i in range(5):
        bpp.add(cocd, "34900001", "Accrued salaries", docs.next(2024), 1, "GX",
                date(2024, 3 + i, 25), -(410_000.0 + 1_000 * i), "BOT_UPLOAD_002",
                f"Salary accrual 0{3 + i}.2024", partner="TP-002")  # fmt: skip
    # AUD entity, small.
    for i in range(3):
        bpp.add("C222", "34900002", "Accrued payroll", docs.next(2025), 1, "IR",
                date(2025, 1 + i, 20), -(9_000.0 * 1.6297), "USER_150", "Payroll accrual AU",
                lcurr="AUD", partner="TP-014")  # fmt: skip
    return bpp


def build_fixed_assets() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fixed assets BPP (EUR) and P20 (JPY and PLN), mostly exact cancelling pairs."""
    docs = DocCounter("49")
    bpp_rows: list[dict[str, object]] = []
    p20_rows: list[dict[str, object]] = []

    def row(cocd: str, account: str, posted: date, amount_lc: float, lcurr: str, user: str,
            text: str, curr: str | None = None, amount_dc: float | None = None,
            reversal: str = "", doc_type: str = "AA") -> dict[str, object]:  # fmt: skip
        return {
            "CoCd": cocd, "Account": account, "Description": "Assets under construction",
            "DocumentNo": docs.next(posted.year), "Item": 1, "Type": doc_type,
            "Year": posted.year, "Period": posted.month,
            "Amount in DC": amount_lc if amount_dc is None else amount_dc,
            "Curr.": curr or lcurr, "Amount in Local Currency": amount_lc, "Lcurr": lcurr,
            "Pstng Date": posted.isoformat(), "Doc. Date": posted.isoformat(),
            "User Name": user, "Text": text, "Doc.Header Text": "", "Reference": "",
            "Tr.Prt": "", "Assignment": "", "Reversal": reversal,
            "Ageing(No of days)": (FIXED_ASSETS_AGEING_DATE - posted).days,
        }  # fmt: skip

    for i in range(8):
        posted = date(2021 + i % 4, 1 + i, 10)
        amount = 25_000.0 + 2_500 * i
        bpp_rows.append(row("C250", "1190010", posted, amount, "EUR", "BOT_RPA_010",
                            "Asset in transit"))  # fmt: skip
        bpp_rows.append(row("C250", "1190010", posted + timedelta(days=40), -amount, "EUR",
                            "BOT_RPA_010", "Asset in transit", reversal="X"))  # fmt: skip
    bpp_rows.append(row("C250", "1190010", date(2019, 5, 2), 14_000.0, "EUR", "USER_902",
                        "Asset in trnasit"))  # fmt: skip
    for i in range(10):
        p20_rows.append(row("C218", "119001", date(2025, 1 + i, 5), 1_600_000.0 + 10_000 * i,
                            "JPY", "BOT_RPA_011", "Machine capitalisation"))  # fmt: skip
    p20_rows.append(row("C218", "119001", date(2026, 9, 18), 2_400_000_000.0, "JPY", "USER_902",
                        "Capitalisation correction"))  # fmt: skip
    p20_rows.append(row("C218", "119001", date(2026, 9, 21), 88_000.0, "JPY", "USER_902",
                        "Import duty", curr="FRF", amount_dc=3_600.0))  # fmt: skip
    for i in range(4):
        p20_rows.append(row("C219", "119001", date(2025, 3 + i, 9), 42_000.0 + i, "PLN",
                            "BOT_RPA_011", "Machine capitalisation"))  # fmt: skip
    # S2 (A4): the same amount posted in EUR and in PLN on one day (equal in whole units only).
    # Appended last so every earlier document number stays the same.
    p20_rows.append(row("C219", "119001", date(2026, 9, 24), round(12_500.40 * 4.29, 2), "PLN",
                        "USER_902", "Asset transfer", curr="EUR", amount_dc=12_500.40))  # fmt: skip
    p20_rows.append(row("C219", "119001", date(2026, 9, 24), 12_500.0, "PLN", "USER_902",
                        "Asset transfer"))  # fmt: skip
    bpp = pd.DataFrame(bpp_rows, columns=FIXED_ASSET_COLUMNS)
    p20 = pd.DataFrame(p20_rows, columns=FIXED_ASSET_COLUMNS).drop(columns=["Reversal"])
    return bpp, p20


def _write(path: Path, title: str, sheets: dict[str, pd.DataFrame]) -> Path:
    summary = pd.DataFrame({f"{title} (SYNTHETIC SAMPLE, invented values)": ["Summary"]})
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path


def generate(out: Path) -> list[Path]:
    """Write ``Payroll_sample.xlsx`` and ``Fixed_assets_sample.xlsx`` into ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    docs = DocCounter("00")
    p20 = build_payroll_p20(docs).frame()
    bpp = build_payroll_bpp(DocCounter("79")).frame()
    blank = pd.DataFrame([{c: None for c in p20.columns}])  # a row with an empty CoCd
    p20 = pd.concat([p20, blank], ignore_index=True)
    fa_bpp, fa_p20 = build_fixed_assets()
    return [
        _write(out / "Payroll_sample.xlsx", "Payroll", {"P20": p20, "BPP": bpp}),
        _write(out / "Fixed_assets_sample.xlsx", "Fixed assets", {"BPP": fa_bpp, "P20": fa_p20}),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/sample"))
    args = parser.parse_args()
    for path in generate(args.out):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
