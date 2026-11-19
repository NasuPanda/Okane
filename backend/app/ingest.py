"""Excel ingestion and EUR conversion (brief sections 6 and 8, "EUR conversion").

Reads the Payroll and Fixed assets workbooks with pandas' calamine engine, skips the Summary
tab, drops rows with an empty CoCd, maps columns to the common model and converts to EUR:
``amount_eur = amount_lc / rate(currency_lc)`` with rates in units per EUR. Payroll sheets carry
their own EUR amount and rate; both are checked against rates.csv.

Errors are explicit: a missing column, an unknown currency or an unparseable date raises
``IngestError``. Nothing is ever guessed and nothing is written back to the workbook.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

WORKBOOK_SUFFIXES = (".xlsx", ".xlsm", ".xls")

# Common field -> source column, per workbook kind (brief section 6 mapping table).
PAYROLL_MAP: dict[str, str] = {
    "amount_dc": "Ammount in DC",  # (sic) the source header is misspelt
    "amount_lc": "Amount in LC",
    "currency_dc": "Curr.",
    "currency_lc": "LCurr",
    "source_amount_eur": "Amount in EUR",
    "source_eur_rate": "EURCurrencyExchangeRate",
    "doc_type": "DocumentType",
    "item": "ItemNo in Doc",
    "posting_date": "Pstng Date",
    "doc_date": "Doc Date",
    "age_days": "Current Ageing (Days)",
    "overdue_abs": "Overdue Amount ABS",
    "allowed_age": "Ageing Allowed (Days)",
}
FIXED_ASSETS_MAP: dict[str, str] = {
    "amount_dc": "Amount in DC",
    "amount_lc": "Amount in Local Currency",
    "currency_dc": "Curr.",
    "currency_lc": "Lcurr",
    "doc_type": "Type",
    "item": "Item",
    "posting_date": "Pstng Date",
    "doc_date": "Doc. Date",
    "age_days": "Ageing(No of days)",
}
# Columns that keep their names in every sheet.
SHARED_MAP: dict[str, str] = {
    "entity": "CoCd",
    "account": "Account",
    "account_name": "Description",
    "document_no": "DocumentNo",
    "year": "Year",
    "period": "Period",
    "user_name": "User Name",
    "text": "Text",
    "header_text": "Doc.Header Text",
    "reference": "Reference",
    "assignment": "Assignment",
}
OPTIONAL_MAP: dict[str, str] = {"partner": "Tr.Prt", "reversal": "Reversal"}
# Identifier columns are read as text so leading zeros survive.
STRING_COLUMNS = ("CoCd", "Account", "DocumentNo", "Reference", "Assignment", "Tr.Prt")
LINE_COLUMNS = [
    "workbook", "erp", "sheet", "source_row", "entity", "account", "account_name",
    "document_no", "item", "year", "period", "doc_type", "posting_date", "doc_date",
    "amount_dc", "currency_dc", "amount_lc", "currency_lc", "amount_eur", "eur_rate",
    "partner", "user_name", "text", "header_text", "reference", "assignment", "age_days",
    "allowed_age", "overdue_abs", "reversal",
]  # fmt: skip
NO_OVERDUE_MARKER = "no overdue"
RATE_CHECK_RELATIVE = 1e-6
AMOUNT_CHECK_EUR = 0.10  # source EUR amounts carry cent-level rounding
# ASSUMPTION (A38): some accounts count ageing days one day differently (on the real Payroll
# BPP sheet, 395 lines, nearly all pension-type, are exactly one day off), so only lines more
# than a day away from the extract date count as disagreeing.
EXTRACT_DATE_TOLERANCE_DAYS = 1


class IngestError(ValueError):
    """Raised when a workbook or the rate table cannot be read without guessing."""


@dataclass
class IngestResult:
    """All lines of one workbook set, plus provenance."""

    lines: pd.DataFrame
    files: list[str]
    hashes: list[str]
    row_counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)


def file_hash(path: Path) -> str:
    """SHA-256 of a file, used to identify a snapshot."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rates(path: Path) -> dict[str, float]:
    """Read ``currency,units_per_eur[,as_of]``; raise if missing or malformed."""
    if not path.exists():
        raise IngestError(
            f"Rate table not found at {path}. Run `make setup` to copy the sample rates, "
            "then confirm the values with the team."
        )
    table = pd.read_csv(path, dtype={"currency": str})
    if not {"currency", "units_per_eur"} <= set(table.columns):
        raise IngestError(f"{path} must have the columns currency,units_per_eur")
    if table["units_per_eur"].isna().any() or (table["units_per_eur"] <= 0).any():
        raise IngestError(f"{path} has an empty or non-positive rate")
    rates = dict(
        zip(table["currency"].str.strip().str.upper(), table["units_per_eur"], strict=True)
    )
    rates.setdefault("EUR", 1.0)
    return {k: float(v) for k, v in rates.items()}


def detect_kind(columns: list[str]) -> str:
    """Payroll sheets carry the misspelt 'Ammount in DC'; Fixed assets sheets 'Amount in DC'."""
    if "Ammount in DC" in columns:
        return "Payroll"
    if "Amount in DC" in columns:
        return "Fixed assets"
    raise IngestError(
        "Sheet has neither 'Ammount in DC' (Payroll) nor 'Amount in DC' (Fixed assets)"
    )


def sheet_erp(sheet_name: str) -> str | None:
    """Map a sheet name to its ERP; the Summary tab and anything else return None."""
    name = sheet_name.strip().upper()
    if name.startswith("P20"):
        return "P20"
    if name.startswith("BPP"):
        return "BPP"
    return None


def parse_allowed_age(values: pd.Series) -> pd.Series:
    """'365' -> 365; 'Actual ageing ( No Overdue )' -> None (pension-type, exempt)."""

    def one(value: object) -> int | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip()
        if NO_OVERDUE_MARKER in text.lower():
            return None
        if re.fullmatch(r"\d+(\.0+)?", text):
            return int(float(text))
        raise IngestError(f"Unrecognised 'Ageing Allowed (Days)' value: {text!r}")

    return values.map(one).astype("Int64")


def parse_dates(values: pd.Series, column: str) -> pd.Series:
    """Parse ISO strings or Excel datetimes; raise if any non-empty value fails."""
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    bad = values.notna() & (values.astype(str).str.strip() != "") & parsed.isna()
    if bad.any():
        raise IngestError(f"{int(bad.sum())} unparseable value(s) in column '{column}'")
    return parsed.dt.date


def _clean_str(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip()
    out = out.str.replace(r"\.0$", "", regex=True)
    return out.where(out.notna() & (out != ""), None).astype(object)


def map_sheet(raw: pd.DataFrame, kind: str, erp: str, sheet: str) -> pd.DataFrame:
    """Map one raw sheet to the common model. Raises on missing columns."""
    kind_map = PAYROLL_MAP if kind == "Payroll" else FIXED_ASSETS_MAP
    required = {**SHARED_MAP, **kind_map}
    missing = sorted(col for col in required.values() if col not in raw.columns)
    if missing:
        raise IngestError(f"{kind} sheet '{sheet}' is missing column(s): {', '.join(missing)}")

    raw = raw.reset_index(names="source_row")
    raw = raw[raw["CoCd"].notna() & (raw["CoCd"].astype(str).str.strip() != "")]
    out = pd.DataFrame(index=raw.index)
    out["workbook"], out["erp"], out["sheet"] = kind, erp, sheet
    out["source_row"] = raw["source_row"].astype(int) + 2  # 1-based, after the header row
    for common, source in {**SHARED_MAP, **kind_map}.items():
        out[common] = raw[source]
    for common, source in OPTIONAL_MAP.items():
        out[common] = raw[source] if source in raw.columns else None
    if kind == "Fixed assets":
        out["overdue_abs"], out["allowed_age"] = None, None
    return _normalise(out, kind)


def _normalise(out: pd.DataFrame, kind: str) -> pd.DataFrame:
    for col in ("entity", "account", "document_no", "reference", "assignment", "partner",
                "currency_dc", "currency_lc", "doc_type", "user_name", "text", "header_text",
                "account_name", "reversal"):  # fmt: skip
        out[col] = _clean_str(out[col])
    out["currency_lc"] = out["currency_lc"].str.upper()
    out["currency_dc"] = out["currency_dc"].map(lambda v: v.upper() if isinstance(v, str) else v)
    for col in ("amount_dc", "amount_lc"):
        out[col] = pd.to_numeric(out[col], errors="raise").astype(float)
    for col in ("item", "year", "period", "age_days"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    out["posting_date"] = parse_dates(out["posting_date"], "posting_date")
    out["doc_date"] = parse_dates(out["doc_date"], "doc_date")
    if kind == "Payroll":
        out["overdue_abs"] = pd.to_numeric(out["overdue_abs"], errors="raise").astype(float)
        out["allowed_age"] = parse_allowed_age(out["allowed_age"])
    if out["currency_lc"].isna().any():
        raise IngestError("Some lines have no local currency")
    return out


def convert_to_eur(lines: pd.DataFrame, rates: dict[str, float]) -> tuple[pd.DataFrame, list[str]]:
    """Add ``eur_rate`` and ``amount_eur``. Returns warnings.

    Payroll sheets keep their own EUR amount (brief section 6); their rate is checked against
    rates.csv and their amount against ``amount_lc / rate``. Other sheets are computed.
    """
    unknown = sorted(set(lines["currency_lc"]) - set(rates))
    if unknown:
        raise IngestError(
            f"No EUR rate for local currency {', '.join(unknown)}. Add it to rates.csv."
        )
    lines = lines.copy()
    lines["eur_rate"] = lines["currency_lc"].map(rates).astype(float)
    computed = (lines["amount_lc"] / lines["eur_rate"]).round(2)
    lines["amount_eur"] = computed
    warnings: list[str] = []
    if "source_amount_eur" in lines:
        source = pd.to_numeric(lines["source_amount_eur"], errors="coerce")
        has_source = source.notna()
        lines.loc[has_source, "amount_eur"] = source[has_source]
        src_rate = pd.to_numeric(lines["source_eur_rate"], errors="coerce")
        rate_off = has_source & (
            ((src_rate - lines["eur_rate"]).abs() / lines["eur_rate"]) > RATE_CHECK_RELATIVE
        )
        if rate_off.any():
            currencies = sorted(set(lines.loc[rate_off, "currency_lc"]))
            warnings.append(
                f"{int(rate_off.sum())} line(s) carry a source EUR rate different from rates.csv "
                f"({', '.join(currencies)})."
            )
        amount_off = has_source & ((source - computed).abs() > AMOUNT_CHECK_EUR)
        if amount_off.any():
            warnings.append(
                f"{int(amount_off.sum())} line(s) have a source EUR amount that differs from "
                f"amount_lc / rate by more than {AMOUNT_CHECK_EUR:.2f}."
            )
    lines = lines.drop(columns=["source_eur_rate", "source_amount_eur"], errors="ignore")
    return lines, warnings


def read_workbook(path: Path) -> tuple[str, list[pd.DataFrame], dict[str, int]]:
    """Read every P20/BPP sheet of one workbook. Returns kind, mapped sheets and row counts."""
    dtype = dict.fromkeys(STRING_COLUMNS, str)
    try:
        sheets = pd.read_excel(path, sheet_name=None, engine="calamine", dtype=dtype)
    except Exception as exc:  # calamine raises several types; report them uniformly
        raise IngestError(f"Cannot read workbook {path.name}: {exc}") from exc
    kinds: set[str] = set()
    mapped: list[pd.DataFrame] = []
    counts: dict[str, int] = {}
    for name, raw in sheets.items():
        erp = sheet_erp(name)
        if erp is None:
            continue  # Summary tab and any other non-data sheet
        kind = detect_kind([str(c) for c in raw.columns])
        kinds.add(kind)
        frame = map_sheet(raw, kind, erp, name)
        counts[f"{kind}/{erp}"] = len(frame)
        mapped.append(frame)
    if not mapped:
        raise IngestError(f"Workbook {path.name} has no P20 or BPP sheet")
    if len(kinds) > 1:
        raise IngestError(f"Workbook {path.name} mixes Payroll and Fixed assets sheets")
    return kinds.pop(), mapped, counts


def ingest(paths: list[Path], rates: dict[str, float]) -> IngestResult:
    """Read a set of workbooks into one common-model frame with EUR amounts."""
    if not paths:
        raise IngestError("No workbook to ingest")
    frames: list[pd.DataFrame] = []
    counts: dict[str, int] = {}
    for path in paths:
        _, mapped, sheet_counts = read_workbook(path)
        frames.extend(mapped)
        counts.update(sheet_counts)
    lines = pd.concat(frames, ignore_index=True)
    lines, warnings = convert_to_eur(lines, rates)
    lines.insert(0, "line_id", range(len(lines)))
    return IngestResult(
        lines=lines[["line_id", *LINE_COLUMNS]],
        files=[p.name for p in paths],
        hashes=[file_hash(p) for p in paths],
        row_counts=counts,
        warnings=warnings,
    )


def find_workbooks(folder: Path) -> list[Path]:
    """Every workbook in a folder, newest first; Excel lock files skipped.

    The kind is not guessed from the file name: the intake step reads the sheets (A38).
    """
    if not folder.exists():
        return []
    return sorted(
        (p for p in folder.iterdir()
         if p.is_file() and p.suffix.lower() in WORKBOOK_SUFFIXES and not p.name.startswith("~$")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )  # fmt: skip


def workbook_kind(path: Path) -> tuple[str, dict[str, int]]:
    """Check a workbook by its sheets and columns; return its kind and rows per sheet.

    Raises ``IngestError`` with a plain message when the file is not a Payroll or Fixed assets
    extract. ASSUMPTION (A38): an extract must carry both the P20 and the BPP sheet.
    """
    if path.suffix.lower() not in WORKBOOK_SUFFIXES:
        raise IngestError(f"{path.name} is not an Excel workbook (.xlsx, .xlsm or .xls)")
    kind, _, counts = read_workbook(path)
    erps = {key.split("/")[1] for key in counts}
    missing = sorted({"P20", "BPP"} - erps)
    if missing:
        raise IngestError(f"{kind} workbook {path.name} has no {' or '.join(missing)} sheet")
    return kind, counts


def extract_dates(lines: pd.DataFrame) -> dict[str, tuple[date | None, int]]:
    """The day each workbook was extracted: posting date + ageing days, per line.

    Returns ``{workbook: (date, lines that disagree)}``. ASSUMPTION (A38): the most common
    value wins; lines within ``EXTRACT_DATE_TOLERANCE_DAYS`` of it agree; a workbook without
    ageing days gives ``(None, 0)``.
    """
    out: dict[str, tuple[date | None, int]] = {}
    for workbook, group in lines.groupby("workbook", sort=True):
        ages = pd.to_numeric(group["age_days"], errors="coerce")
        posted = pd.to_datetime(group["posting_date"], errors="coerce")
        known = ages.notna() & posted.notna()
        if not known.any():
            out[str(workbook)] = (None, 0)
            continue
        taken = posted[known] + pd.to_timedelta(ages[known].astype(int), unit="D")
        mode = taken.value_counts().index[0]
        off = (taken - mode).dt.days.abs() > EXTRACT_DATE_TOLERANCE_DAYS
        out[str(workbook)] = (mode.date(), int(off.sum()))
    return out
