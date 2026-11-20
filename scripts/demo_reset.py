"""Put the demo back to its start state (docs/DEMO.md, #26).

Default: rebuild the synthetic demo folder (``data/demo/``): Fixed assets and last week's Payroll
extract in its ``inbox/``, this week's Payroll extract in ``ready/`` for step 2, the sample
rates, and no database (so no runs, decisions or rule changes). Run the app on it with
``make demo``; the analysis date is the extract date (A2, A38).

Safety (#26):
- Nothing changes without ``--yes``; the plan (what is deleted, moved and created) is printed
  first.
- The synthetic reset deletes only the demo folder's own entries, and refuses a folder that
  holds anything else, a workbook not marked synthetic, a link (symlink), the repository or the
  real ``data/`` folder, or a ``.git`` or ``.env``. Every check runs before anything changes.
- ``--real`` never deletes: it moves the app's database and extract store into
  ``<archive>/reset-<time>/``. The paths are the app's own settings (the environment and
  ``backend/.env``), so a changed ``OKANE_DB_PATH`` or ``OKANE_EXTRACTS_DIR`` is honoured. It
  never touches the watched folder (only read, A38) or ``.env``.

Usage: ``python scripts/demo_reset.py [--dir PATH] [--yes]`` or ``... --real [--yes]``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DATA_DIR = REPO_ROOT / "data"
DEMO_DIR = DATA_DIR / "demo"
SAMPLE_RATES = REPO_ROOT / "backend" / "tests" / "data" / "rates.sample.csv"
SYNTHETIC_MARK = "SYNTHETIC SAMPLE"
WORKBOOK_SUFFIXES = {".xlsx", ".xls", ".xlsm"}
# What a demo folder may hold: what this script creates and what the app writes while it runs.
DEMO_ENTRIES = {
    "inbox", "ready", "extracts", "archive", "sample", "fixtures", "tmp",
    "rates.csv", "okane.duckdb", "okane.duckdb.wal",
}  # fmt: skip
WORKBOOK_FOLDERS = {"inbox", "ready", "extracts", "archive", "sample", "tmp"}


class RefusedError(Exception):
    """The reset would touch something that is not the demo's own."""


@dataclass
class Plan:
    target: Path
    delete: list[Path] = field(default_factory=list)
    move: list[tuple[Path, Path]] = field(default_factory=list)
    create: list[str] = field(default_factory=list)

    def describe(self) -> str:
        lines = [f"Demo reset for {self.target}"]
        lines += [f"  delete  {p}" for p in self.delete]
        lines += [f"  move    {src}  ->  {dest}" for src, dest in self.move]
        lines += [f"  create  {self.target / name}" for name in self.create]
        if len(lines) == 1:
            lines.append("  nothing to do")
        return "\n".join(lines)


def is_synthetic(path: Path) -> bool:
    """A workbook written by scripts/generate_sample_data.py (its Summary sheet says so)."""
    try:
        summary = pd.read_excel(path, sheet_name="Summary", engine="calamine", nrows=0)
    except Exception:  # any unreadable file counts as not synthetic
        return False
    return any(SYNTHETIC_MARK in str(column) for column in summary.columns)


def _contains(parent: Path, child: Path) -> bool:
    parent, child = parent.resolve(), child.resolve()
    return parent == child or parent in child.parents


def synthetic_plan(target: Path = DEMO_DIR) -> Plan:
    """What the synthetic reset deletes and creates in ``target``; refuses anything unsafe."""
    target = target.resolve()
    for protected in (REPO_ROOT, DATA_DIR, DATA_DIR / "inbox"):
        if _contains(target, protected):
            raise RefusedError(
                f"{target} holds {protected}: the demo reset works only in its own folder"
            )
    if _contains(REPO_ROOT, target) and not _contains(DATA_DIR, target):
        raise RefusedError(f"{target} is inside the repository but not under data/")
    plan = Plan(target=target, create=[
        "inbox/Fixed_assets_sample.xlsx", "inbox/Payroll_sample_previous_week.xlsx",
        "ready/Payroll_sample.xlsx", "rates.csv",
    ])  # fmt: skip
    if not target.exists():
        return plan
    for entry in sorted(target.iterdir()):
        if entry.name not in DEMO_ENTRIES:
            raise RefusedError(f"{entry} is not part of a demo folder; nothing was changed")
        if entry.is_symlink():
            raise RefusedError(f"{entry} is a link; nothing was changed")
        inside = sorted(entry.rglob("*")) if entry.is_dir() else []
        for path in inside:
            if path.is_symlink():
                raise RefusedError(f"{path} is a link; nothing was changed")
            if path.name == ".git" or path.name.startswith(".env"):
                raise RefusedError(f"{path} must not be deleted; nothing was changed")
            workbook = path.suffix.lower() in WORKBOOK_SUFFIXES
            if entry.name in WORKBOOK_FOLDERS and workbook and not is_synthetic(path):
                raise RefusedError(f"{path} is not a synthetic sample; nothing was changed")
        plan.delete.append(entry)
    return plan


def app_settings(**overrides: Any) -> Settings:
    """The settings a run of the app reads: the environment and ``backend/.env`` (fresh, not
    the app's cached copy)."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from app.config import Settings

    return Settings(**overrides)


def real_plan(settings: Settings | None = None, stamp: str | None = None) -> Plan:
    """What ``--real`` moves aside: the app's database and its extract store, from its settings.
    Never deletes, and refuses to touch the watched folder (A38) or a ``.env``."""
    settings = settings or app_settings()
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    aside = settings.archive_path / f"reset-{stamp}"
    plan = Plan(target=settings.data_dir.resolve())
    db = settings.db_path
    for src in (db, db.with_name(db.name + ".wal"), settings.store_dir):
        if not src.exists():
            continue
        if _contains(settings.inbox_dir, src) or _contains(src, settings.inbox_dir):
            raise RefusedError(f"{src} is or holds the watched folder; nothing was changed")
        if src.name.startswith(".env"):
            raise RefusedError(f"{src} must not be moved; nothing was changed")
        plan.move.append((src, aside / src.name))
    return plan


def as_of_note(settings: Settings) -> str | None:
    """A warning when an analysis date is pinned (environment or ``backend/.env``)."""
    if settings.as_of is None:
        return None
    return (
        f"Note: OKANE_AS_OF is set to {settings.as_of}; the demo expects the extract date (A2)."
        " Unset it in the environment and backend/.env."
    )


def apply(plan: Plan) -> None:
    """Carry out a plan made by ``synthetic_plan`` or ``real_plan``."""
    for path in plan.delete:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    for src, dest in plan.move:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    if plan.create:
        build_demo_folder(plan.target)


def build_demo_folder(target: Path) -> Path:
    """Write the demo start state into ``target``; returns this week's Payroll extract."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from generate_sample_data import generate, generate_previous_week

    inbox, ready = target / "inbox", target / "ready"
    inbox.mkdir(parents=True, exist_ok=True)
    payroll, fixed_assets = generate(ready)
    shutil.move(str(fixed_assets), inbox / fixed_assets.name)
    generate_previous_week(inbox)
    shutil.copy(SAMPLE_RATES, target / "rates.csv")
    return payroll


def reset(target: Path = DEMO_DIR, *, real: bool = False, yes: bool = False) -> Plan:
    """Print the plan; carry it out only with ``yes``."""
    plan = real_plan() if real else synthetic_plan(target)
    print(plan.describe())
    if not yes:
        print("Nothing changed. Run again with --yes to do this.")
        return plan
    apply(plan)
    print("Done.")
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=None, help="demo folder (default data/demo)")
    parser.add_argument("--real", action="store_true", help="move the real database aside")
    parser.add_argument("--yes", action="store_true", help="carry out the plan")
    args = parser.parse_args(argv)
    if args.real and args.dir is not None:
        parser.error("--real uses the app's own paths; --dir is for the synthetic demo folder")
    try:
        reset(args.dir or DEMO_DIR, real=args.real, yes=args.yes)
    except RefusedError as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    note = as_of_note(app_settings())
    if note:
        print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
