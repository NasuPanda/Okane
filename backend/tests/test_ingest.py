"""Ingestion: column mapping, validation, EUR conversion, snapshots (brief sections 6 and 8)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.database import Database
from app.ingest import (
    IngestError,
    convert_to_eur,
    find_workbooks,
    ingest,
    load_rates,
    parse_allowed_age,
)

PAYROLL_HEADERS = [
    "CoCd", "Account", "Description", "DocumentNo", "ItemNo in Doc", "DocumentType", "Year",
    "Period", "Ammount in DC", "Curr.", "Amount in LC", "LCurr", "Amount in EUR",
    "EURCurrencyExchangeRate", "Pstng Date", "Doc Date", "User Name", "Text", "Doc.Header Text",
    "Reference", "Assignment", "Ageing Allowed (Days)", "Overdue Amount ABS",
    "Current Ageing (Days)",
]  # fmt: skip


def _payroll_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "CoCd": "C172", "Account": "279006", "Description": "Social security",
        "DocumentNo": "0012345678", "ItemNo in Doc": 1, "DocumentType": "P0", "Year": 2026,
        "Period": 9, "Ammount in DC": -36620.0, "Curr.": "HUF", "Amount in LC": -36620.0,
        "LCurr": "HUF", "Amount in EUR": -100.0, "EURCurrencyExchangeRate": 366.2,
        "Pstng Date": "2026-09-30", "Doc Date": "2026-09-30", "User Name": "BOT_UPLOAD_001",
        "Text": "Payroll202609", "Doc.Header Text": "", "Reference": "007", "Assignment": "",
        "Ageing Allowed (Days)": "365", "Overdue Amount ABS": 0.0, "Current Ageing (Days)": 23,
    }  # fmt: skip
    row.update(overrides)
    return row


def _write(path: Path, sheets: dict[str, pd.DataFrame]) -> Path:
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame({"Balance Sheet Reconciliation": ["summary"]}).to_excel(
            writer, sheet_name="Summary", index=False
        )
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path


def test_payroll_mapping_keeps_document_number_as_string(
    tmp_path: Path, rates: dict[str, float]
) -> None:
    rows = [_payroll_row(), _payroll_row(CoCd=None), _payroll_row(DocumentNo="0000000042")]
    path = _write(tmp_path / "Payroll.xlsx", {"P20": pd.DataFrame(rows)})
    result = ingest([path], rates)
    lines = result.lines
    assert len(lines) == 2, "the row with an empty CoCd is dropped and Summary is skipped"
    assert list(lines["document_no"]) == ["0012345678", "0000000042"]
    assert lines["reference"].iloc[0] == "007"
    assert lines["amount_eur"].iloc[0] == pytest.approx(-100.0)
    assert lines["workbook"].iloc[0] == "Payroll" and lines["erp"].iloc[0] == "P20"
    assert result.row_counts == {"Payroll/P20": 2}
    assert len(result.hashes[0]) == 64


def test_missing_column_raises_clear_error(tmp_path: Path, rates: dict[str, float]) -> None:
    frame = pd.DataFrame([_payroll_row()]).drop(columns=["Overdue Amount ABS"])
    path = _write(tmp_path / "Payroll.xlsx", {"BPP": frame})
    with pytest.raises(IngestError, match="Overdue Amount ABS"):
        ingest([path], rates)


def test_unknown_currency_raises(tmp_path: Path, rates: dict[str, float]) -> None:
    path = _write(tmp_path / "Payroll.xlsx", {"P20": pd.DataFrame([_payroll_row(LCurr="XYZ")])})
    with pytest.raises(IngestError, match="XYZ"):
        ingest([path], rates)


def test_rate_mismatch_is_reported_not_guessed(rates: dict[str, float]) -> None:
    lines = pd.DataFrame(
        {"currency_lc": ["HUF"], "amount_lc": [-36620.0],
         "source_eur_rate": [360.0], "source_amount_eur": [-101.72]}
    )  # fmt: skip
    converted, warnings = convert_to_eur(lines, rates)
    assert converted["amount_eur"].iloc[0] == pytest.approx(-101.72), "payroll keeps its own EUR"
    assert any("source EUR rate" in w for w in warnings)


def test_allowed_age_parsing() -> None:
    parsed = parse_allowed_age(pd.Series(["365", "Actual ageing ( No Overdue )", "180"]))
    assert parsed.tolist() == [365, pd.NA, 180]
    with pytest.raises(IngestError):
        parse_allowed_age(pd.Series(["sometimes"]))


def test_rates_file_missing(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="make setup"):
        load_rates(tmp_path / "nope.csv")


def test_find_workbooks_lists_newest_first_without_lock_files(tmp_path: Path) -> None:
    import os

    for i, name in enumerate(["Payroll_old.xlsx", "Payroll_new.xlsx", "Fixed_assets.xlsx"]):
        p = tmp_path / name
        p.write_bytes(b"x")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))
    (tmp_path / "~$Payroll_new.xlsx").write_bytes(b"lock")
    (tmp_path / "notes.txt").write_bytes(b"x")
    names = [p.name for p in find_workbooks(tmp_path)]
    # The kind is read from the sheets by the intake step (A38), never guessed from the name.
    assert names == ["Fixed_assets.xlsx", "Payroll_new.xlsx", "Payroll_old.xlsx"]


def test_snapshot_round_trip(tmp_path: Path, rates: dict[str, float]) -> None:
    path = _write(tmp_path / "Payroll.xlsx", {"P20": pd.DataFrame([_payroll_row()])})
    result = ingest([path], rates)
    db = Database(tmp_path / "t.duckdb")
    db.write_snapshot("s1", result.lines, result.files, result.hashes, True, result.row_counts, [])
    back = db.read_lines("s1")
    assert back["document_no"].tolist() == ["0012345678"]
    assert db.snapshot_info("s1")["synthetic"] is True
    db.close()


# ----- synthetic workbooks (always run) -----------------------------------------------------
def test_synthetic_workbooks_ingest(synthetic) -> None:  # type: ignore[no-untyped-def]
    counts = synthetic.row_counts
    assert set(counts) == {"Payroll/P20", "Payroll/BPP", "Fixed assets/P20", "Fixed assets/BPP"}
    lines = synthetic.lines
    fa = lines[lines["workbook"] == "Fixed assets"]
    assert set(fa["currency_lc"]) >= {"JPY", "PLN", "EUR"}
    jpy = fa[fa["currency_lc"] == "JPY"].iloc[0]
    assert jpy["amount_eur"] == pytest.approx(round(jpy["amount_lc"] / 162.5, 2))
    assert fa["reversal"].notna().any()
    assert lines["document_no"].str.len().eq(10).all()


# ----- real workbooks (skipped when data/inbox is empty) ------------------------------------
def test_real_payroll_row_counts(real_payroll) -> None:  # type: ignore[no-untyped-def]
    assert real_payroll.row_counts == {"Payroll/P20": 8298, "Payroll/BPP": 5669}
    assert real_payroll.warnings == []


def test_real_find_workbooks_sees_payroll(real_payroll_path: Path) -> None:
    assert real_payroll_path in find_workbooks(real_payroll_path.parent)


def test_real_find_workbooks_sees_both(
    real_payroll_path: Path, real_fixed_assets_path: Path
) -> None:
    found = find_workbooks(real_payroll_path.parent)
    assert {real_payroll_path, real_fixed_assets_path} <= set(found)


def test_real_fixed_assets_row_counts(real_fixed_assets, real_payroll) -> None:  # type: ignore[no-untyped-def]
    """Brief section 6: four data sheets, 24,165 rows in total."""
    assert real_fixed_assets.row_counts == {"Fixed assets/BPP": 5976, "Fixed assets/P20": 4222}
    assert real_fixed_assets.warnings == []
    total = sum(real_fixed_assets.row_counts.values()) + sum(real_payroll.row_counts.values())
    assert total == 24_165


def test_real_fixed_assets_column_mapping(real_fixed_assets) -> None:  # type: ignore[no-untyped-def]
    """Brief section 6 mapping table, Fixed-asset column."""
    lines = real_fixed_assets.lines
    assert set(lines["workbook"]) == {"Fixed assets"}
    bpp, p20 = lines[lines["erp"] == "BPP"], lines[lines["erp"] == "P20"]
    assert set(bpp["currency_lc"]) == {"EUR"}
    assert set(p20["currency_lc"]) == {"JPY", "PLN"}
    assert bpp["account"].nunique() == 1 and p20["account"].nunique() == 1
    assert lines["allowed_age"].isna().all() and lines["overdue_abs"].isna().all()
    assert bpp["reversal"].notna().any(), "Reversal is mapped on Fixed assets BPP"
    assert p20["reversal"].isna().all(), "Fixed assets P20 has no Reversal column"
    for col in ("age_days", "posting_date", "doc_date", "item", "doc_type", "document_no"):
        assert lines[col].notna().all(), col
    assert lines["document_no"].map(type).eq(str).all()


def test_real_fixed_assets_eur_conversion(  # type: ignore[no-untyped-def]
    real_fixed_assets, rates: dict[str, float]
) -> None:
    """Fixed-asset sheets carry no EUR amount: amount_eur = amount_lc / rate(currency_lc)."""
    lines = real_fixed_assets.lines
    assert (lines["eur_rate"] == lines["currency_lc"].map(rates)).all()
    computed = (lines["amount_lc"] / lines["eur_rate"]).round(2)
    assert (lines["amount_eur"] - computed).abs().max() == pytest.approx(0)
    bpp = lines[lines["erp"] == "BPP"]
    assert (bpp["amount_eur"] == bpp["amount_lc"].round(2)).all()
