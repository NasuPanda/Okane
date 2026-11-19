"""The intake step, extract dates and the late rule (docs/ASSUMPTIONS.md A38). Synthetic only."""

from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.config import Settings
from app.database import Database
from app.ingest import extract_dates
from app.intake import Intake
from app.services.schedule import extract_status, last_scheduled_run, weekday_index
from tests.conftest import rewrite_workbook

PAYROLL = "Payroll_sample.xlsx"
FIXED = "Fixed_assets_sample.xlsx"


@pytest.fixture
def intake(tmp_path: Path) -> Intake:
    settings = Settings(data_dir=tmp_path / "data", inbox_dir=tmp_path / "watched")
    return Intake(settings, Database(tmp_path / "data" / "okane.duckdb"))


def _snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    return {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in folder.iterdir()}


def test_accepts_a_valid_extract_and_stores_a_copy(intake: Intake, synthetic_dir: Path) -> None:
    src = synthetic_dir / PAYROLL
    result = intake.accept(src, "upload", received_by="preparer")
    assert (result.status, result.kind) == ("accepted", "Payroll")
    [stored] = intake.current_paths()
    assert stored.parent == intake.settings.store_dir / "payroll"
    assert stored.read_bytes() == src.read_bytes() and src.exists()
    [entry] = intake.db.current_extracts()
    assert (entry["route"], entry["received_by"]) == ("upload", "preparer")
    assert entry["rows"] > 0


def test_refuses_an_extract_already_loaded(intake: Intake, synthetic_dir: Path) -> None:
    intake.accept(synthetic_dir / PAYROLL, "upload")
    again = intake.accept(synthetic_dir / PAYROLL, "upload", original_name="renamed.xlsx")
    assert again.status == "duplicate" and "already loaded" in again.message


@pytest.mark.parametrize("case", ["csv_renamed", "missing_column", "one_sheet"])
def test_refuses_a_wrong_file(
    intake: Intake, synthetic_dir: Path, tmp_path: Path, case: str
) -> None:
    bad = tmp_path / "bad.xlsx"
    if case == "csv_renamed":
        bad.write_text("CoCd,Account\nC1,1\n")
    elif case == "missing_column":
        rewrite_workbook(synthetic_dir / PAYROLL, bad, drop_column="Pstng Date")
    else:
        rewrite_workbook(synthetic_dir / PAYROLL, bad, drop_sheets=("BPP",))
    result = intake.accept(bad, "upload", original_name="Payroll week 47.xlsx")
    assert result.status == "rejected"
    assert "Payroll week 47.xlsx" in result.message or "Pstng Date" in result.message
    assert "bad.xlsx" not in result.message
    if case == "csv_renamed":
        assert result.message.startswith("Payroll week 47.xlsx could not be read as a Payroll")
    assert intake.current_paths() == []


def test_a_new_extract_replaces_the_current_one_and_archives_it(
    intake: Intake, synthetic_dir: Path, tmp_path: Path
) -> None:
    intake.accept(synthetic_dir / PAYROLL, "upload")
    newer = rewrite_workbook(synthetic_dir / PAYROLL, tmp_path / "Payroll_w47.xlsx",
                             drop_last_rows=1)  # fmt: skip
    assert intake.accept(newer, "upload").status == "accepted"
    [current] = intake.current_paths()
    assert current.name == "Payroll_w47.xlsx"
    archived = list(intake.settings.archive_path.iterdir())
    assert len(archived) == 1 and archived[0].name.endswith(PAYROLL)
    assert archived[0].read_bytes() == (synthetic_dir / PAYROLL).read_bytes()


def test_scan_leaves_the_watched_folder_untouched(
    intake: Intake, synthetic_dir: Path, tmp_path: Path
) -> None:
    watched = tmp_path / "watched"
    shutil.copytree(synthetic_dir, watched)
    (watched / "notes.txt").write_text("not a workbook")
    before = _snapshot(watched)
    results = intake.scan_folder(watched, "watcher")
    assert sorted((r.status, r.kind) for r in results) == [
        ("accepted", "Fixed assets"), ("accepted", "Payroll")]  # fmt: skip
    assert _snapshot(watched) == before
    assert intake.scan_folder(watched, "schedule") == []  # nothing new the second time


def test_scan_never_loads_an_older_file_over_a_newer_one(
    intake: Intake, synthetic_dir: Path, tmp_path: Path
) -> None:
    import os

    watched = tmp_path / "watched"
    watched.mkdir()
    old = rewrite_workbook(synthetic_dir / PAYROLL, watched / "Payroll_w46.xlsx",
                           drop_last_rows=1)  # fmt: skip
    new = shutil.copy(synthetic_dir / PAYROLL, watched / "Payroll_w47.xlsx")
    os.utime(old, (1_000_000, 1_000_000))
    intake.accept(Path(new), "upload")
    assert intake.scan_folder(watched, "watcher") == []
    assert [p.name for p in intake.current_paths()] == ["Payroll_w47.xlsx"]


def test_a_refused_file_in_the_watched_folder_is_reported_once(
    intake: Intake, tmp_path: Path
) -> None:
    watched = tmp_path / "watched"
    watched.mkdir()
    (watched / "Payroll.xlsx").write_text("not really a workbook")
    [first] = intake.scan_folder(watched, "watcher")
    assert first.status == "rejected"
    assert intake.scan_folder(watched, "watcher") == []


# ----- extract date -------------------------------------------------------------------------
def test_extract_dates_of_the_synthetic_workbooks(synthetic_lines: pd.DataFrame) -> None:
    dates = extract_dates(synthetic_lines)
    assert dates == {"Fixed assets": (date(2026, 10, 2), 0), "Payroll": (date(2026, 10, 23), 0)}


def test_extract_date_takes_the_most_common_value_and_counts_the_rest() -> None:
    oct1 = date(2026, 10, 1)
    lines = pd.DataFrame({
        "workbook": ["Payroll"] * 4 + ["Fixed assets"],
        "posting_date": [oct1, oct1, oct1, oct1, date(2026, 9, 1)],
        # 23 Oct twice (the extract date), 24 Oct (one day off: agrees), 26 Oct (disagrees)
        "age_days": [22, 22, 23, 25, None],
    })  # fmt: skip
    assert extract_dates(lines) == {
        "Payroll": (date(2026, 10, 23), 1), "Fixed assets": (None, 0)}  # fmt: skip


# ----- late rule ----------------------------------------------------------------------------
MON = 0


@pytest.mark.parametrize(
    ("now", "boundary"),
    [
        (datetime(2026, 11, 23, 6, 0), datetime(2026, 11, 23, 6, 0)),  # Monday, at the run
        (datetime(2026, 11, 23, 5, 59), datetime(2026, 11, 16, 6, 0)),  # Monday, just before
        (datetime(2026, 11, 19, 14, 0), datetime(2026, 11, 16, 6, 0)),  # Thursday
    ],
)
def test_last_scheduled_run(now: datetime, boundary: datetime) -> None:
    assert last_scheduled_run(now, MON, 6, 0) == boundary


def test_late_when_nothing_new_since_the_previous_monday_run() -> None:
    monday_run = datetime(2026, 11, 23, 6, 0)
    on_time = extract_status(datetime(2026, 11, 17, 9, 0), monday_run, MON, 6, 0)
    exactly = extract_status(datetime(2026, 11, 16, 6, 0), monday_run, MON, 6, 0)
    late = extract_status(datetime(2026, 11, 16, 5, 59), monday_run, MON, 6, 0)
    assert on_time == (False, datetime(2026, 11, 30, 6, 0))
    assert exactly[0] is False and late[0] is True
    # mid-week, last week's extract is still current
    assert extract_status(datetime(2026, 11, 10, 9, 0), datetime(2026, 11, 19), MON, 6, 0) == (
        False, datetime(2026, 11, 23, 6, 0))  # fmt: skip


def test_weekday_index() -> None:
    assert (weekday_index("mon"), weekday_index("Fri"), weekday_index("mon-fri")) == (0, 4, 0)
    assert weekday_index("??") == 0
