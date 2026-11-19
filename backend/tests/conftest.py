"""Shared fixtures.

Real workbooks are never in Git: tests that need them use ``real_payroll`` / ``real_lines``
(Payroll), ``real_fixed_assets`` (Fixed assets) or ``real_all_lines`` (both), and skip when
``data/inbox/`` lacks the workbook they need. Synthetic workbooks are generated once per
session into a temp folder (spreadsheets are git-ignored and never committed).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.config import REPO_ROOT
from app.ingest import IngestResult, find_workbooks, ingest, load_rates

TESTS_DIR = Path(__file__).resolve().parent
SAMPLE_RATES = TESTS_DIR / "data" / "rates.sample.csv"
REAL_INBOX = REPO_ROOT / "data" / "inbox"
SYNTHETIC_AS_OF = date(2026, 11, 18)
REAL_AS_OF = date(2026, 11, 18)

sys.path.insert(0, str(REPO_ROOT / "scripts"))


@pytest.fixture(scope="session")
def rates() -> dict[str, float]:
    """The committed sample rates (the brief's payroll rates plus Fixed assets currencies)."""
    return load_rates(SAMPLE_RATES)


def _real_paths(kind_word: str) -> list[Path]:
    return [p for p in find_workbooks(REAL_INBOX) if kind_word in p.name.lower()]


@pytest.fixture(scope="session")
def real_payroll_path() -> Path:
    """The real Payroll workbook, or skip."""
    paths = _real_paths("payroll")
    if not paths:
        pytest.skip("real Payroll workbook not present in data/inbox/")
    return paths[0]


@pytest.fixture(scope="session")
def real_payroll(real_payroll_path: Path, rates: dict[str, float]) -> IngestResult:
    """Ingested real Payroll lines (session cached)."""
    return ingest([real_payroll_path], rates)


@pytest.fixture(scope="session")
def real_lines(real_payroll: IngestResult) -> pd.DataFrame:
    return real_payroll.lines


@pytest.fixture(scope="session")
def real_fixed_assets_path() -> Path:
    """The real Fixed assets workbook, or skip."""
    paths = _real_paths("fixed")
    if not paths:
        pytest.skip("real Fixed assets workbook not present in data/inbox/")
    return paths[0]


@pytest.fixture(scope="session")
def real_fixed_assets(real_fixed_assets_path: Path, rates: dict[str, float]) -> IngestResult:
    """Ingested real Fixed assets lines (session cached)."""
    return ingest([real_fixed_assets_path], rates)


@pytest.fixture(scope="session")
def real_all_lines(
    real_payroll_path: Path, real_fixed_assets_path: Path, rates: dict[str, float]
) -> pd.DataFrame:
    """Payroll and Fixed assets ingested together, as a run sees them (session cached)."""
    return ingest([real_payroll_path, real_fixed_assets_path], rates).lines


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Synthetic Payroll and Fixed assets workbooks, generated once per session."""
    from generate_sample_data import generate

    out = tmp_path_factory.mktemp("synthetic")
    generate(out)
    return out


@pytest.fixture(scope="session")
def synthetic(synthetic_dir: Path, rates: dict[str, float]) -> IngestResult:
    return ingest(find_workbooks(synthetic_dir), rates)


@pytest.fixture(scope="session")
def synthetic_lines(synthetic: IngestResult) -> pd.DataFrame:
    return synthetic.lines


@pytest.fixture
def app_env(tmp_path: Path, synthetic_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the app at a temp database and a temp inbox seeded with synthetic workbooks."""
    import shutil

    from app.config import get_settings

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for workbook in synthetic_dir.iterdir():
        shutil.copy(workbook, inbox / workbook.name)
    rates_path = tmp_path / "rates.csv"
    shutil.copy(SAMPLE_RATES, rates_path)
    env = {
        "OKANE_DATA_DIR": str(tmp_path),
        "OKANE_INBOX_DIR": str(inbox),
        "OKANE_SAMPLE_DIR": str(tmp_path / "sample"),
        "OKANE_RATES_PATH": str(rates_path),
        "OKANE_DB_PATH": str(tmp_path / "okane.duckdb"),
        "OKANE_FIXTURES_DIR": str(tmp_path / "fixtures"),
        "OKANE_AS_OF": SYNTHETIC_AS_OF.isoformat(),
        "OKANE_ENABLE_WATCHER": "false",
        "OKANE_ENABLE_SCHEDULER": "false",
        "OKANE_RUN_ON_STARTUP": "false",
        "OKANE_AI_ENABLED": "false",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def rewrite_workbook(
    src: Path,
    dest: Path,
    *,
    drop_last_rows: int = 0,
    drop_sheets: tuple[str, ...] = (),
    drop_column: str | None = None,
) -> Path:
    """A changed copy of a synthetic workbook (new hash): fewer rows, sheets or columns."""
    from app.ingest import STRING_COLUMNS

    sheets = pd.read_excel(
        src, sheet_name=None, engine="calamine", dtype=dict.fromkeys(STRING_COLUMNS, str)
    )
    with pd.ExcelWriter(dest, engine="xlsxwriter") as writer:
        for name, frame in sheets.items():
            if name in drop_sheets:
                continue
            if drop_last_rows and name != "Summary":
                frame = frame.iloc[: len(frame) - drop_last_rows]
            if drop_column and drop_column in frame.columns:
                frame = frame.drop(columns=[drop_column])
            frame.to_excel(writer, sheet_name=name, index=False)
    return dest
