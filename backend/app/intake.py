"""The single intake step (docs/ASSUMPTIONS.md A38).

Every route that brings a weekly extract (an upload in Okane, a file in the watched folder, a
future connector) hands the file to ``Intake``. It:

1. skips a file whose hash is already known ("already loaded"),
2. checks it by its sheets and columns, not its file name (a Payroll or Fixed assets workbook
   with both its P20 and BPP sheets),
3. copies it into Okane's store (``extracts_dir/<kind>/``), moving the file it replaces to
   ``archive_dir`` so a past week can be re-run,
4. records the arrival (route, who, when) in the ``extracts`` table.

Runs read only from the store. The source is never changed: the watched folder may be a synced
shared folder, so nothing in it is moved, renamed or deleted (CLAUDE.md rule 2). Messages carry
file names and column names only, never row data (rule 3).
"""

from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import Settings
from app.database import Database, utcnow
from app.ingest import IngestError, file_hash, find_workbooks, workbook_kind
from app.schemas import ExtractRoute

log = logging.getLogger("okane.intake")

KIND_FOLDERS = {"Payroll": "payroll", "Fixed assets": "fixed-assets"}
NOT_AN_EXTRACT = "{name} could not be read as a Payroll or Fixed assets extract."


@dataclass(frozen=True)
class IntakeResult:
    status: Literal["accepted", "duplicate", "rejected"]
    message: str
    file_name: str
    kind: str | None = None


class Intake:
    """Thread-safe: an upload and a folder scan never store at the same time."""

    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self._lock = threading.RLock()
        # In-memory only: a refused file in the watched folder is not re-read on every run.
        self._refused: dict[str, str] = {}
        self._hashes: dict[tuple[str, int, int], str] = {}

    # ----- public ---------------------------------------------------------------------------
    def accept(
        self,
        src: Path,
        route: ExtractRoute,
        original_name: str | None = None,
        received_by: str | None = None,
    ) -> IntakeResult:
        """Check one file and, if it is a new extract, make it the current one of its kind."""
        name = Path(original_name or src.name).name
        digest = file_hash(src)
        with self._lock:
            known = self._known(digest, name)
            if known is not None:
                return known
            checked = self._check(src, digest, name)
            if isinstance(checked, IntakeResult):
                return checked
            kind, rows = checked
            return self._store(src, digest, name, kind, rows, route, received_by)

    def scan_folder(self, folder: Path, route: ExtractRoute) -> list[IntakeResult]:
        """Accept the newest new workbook per kind in ``folder``; the folder is left untouched.

        Older files of a kind whose newest file is already known are not loaded, so a scan never
        replaces a newer extract with an older one.
        """
        results: list[IntakeResult] = []
        seen: set[str] = set()
        with self._lock:
            for path in find_workbooks(folder):
                try:
                    digest = self._hash(path)
                except OSError as exc:  # a synced file still downloading, or removed meanwhile
                    log.warning("cannot read %s in the watched folder: %s", path.name, exc)
                    continue
                entry = self.db.get_extract(digest)
                if entry is not None:
                    seen.add(entry["kind"])
                    continue
                if digest in self._refused:
                    continue
                checked = self._check(path, digest, path.name)
                if isinstance(checked, IntakeResult):
                    results.append(checked)
                    continue
                kind, rows = checked
                if kind in seen:
                    continue
                seen.add(kind)
                received_by = self.settings.default_user
                results.append(self._store(path, digest, path.name, kind, rows, route, received_by))
        return results

    def current_paths(self) -> list[Path]:
        """The stored current file per kind (Payroll and Fixed assets), by kind."""
        paths = [Path(e["stored_path"]) for e in self.db.current_extracts()]
        return [p for p in paths if p.exists()]

    # ----- steps ----------------------------------------------------------------------------
    def _hash(self, path: Path) -> str:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key not in self._hashes:
            self._hashes[key] = file_hash(path)
        return self._hashes[key]

    def _known(self, digest: str, name: str) -> IntakeResult | None:
        entry = self.db.get_extract(digest)
        if entry is None:
            return None
        when = f"{entry['received_at']:%d %b %Y}"
        return IntakeResult(
            "duplicate",
            f"This extract was already loaded on {when} (as {entry['file_name']}). "
            "Nothing new to check.",
            name,
            entry["kind"],
        )

    def _check(self, src: Path, digest: str, name: str) -> tuple[str, int] | IntakeResult:
        try:
            kind, counts = workbook_kind(src)
        except IngestError as exc:
            message = str(exc)
            if message.startswith("Cannot read workbook"):  # the reader's wording is too technical
                message = NOT_AN_EXTRACT.format(name=name) + " Is it an Excel workbook?"
        except Exception:  # unreadable content: say so without echoing any cell value
            message = NOT_AN_EXTRACT.format(name=name)
        else:
            return kind, sum(counts.values())
        if src.name != name:
            message = message.replace(src.name, name)
        self._refused[digest] = message
        log.warning("refused %s: %s", name, message)
        return IntakeResult("rejected", message, name)

    def _store(
        self,
        src: Path,
        digest: str,
        name: str,
        kind: str,
        rows: int,
        route: ExtractRoute,
        received_by: str | None,
    ) -> IntakeResult:
        folder = self.settings.store_dir / KIND_FOLDERS[kind]
        folder.mkdir(parents=True, exist_ok=True)
        incoming = folder / f".incoming-{digest[:12]}{Path(name).suffix}"
        shutil.copy2(src, incoming)  # a copy: the source stays where it is

        archived: str | None = None
        for previous in self.db.current_extracts():
            if previous["kind"] != kind:
                continue
            old = Path(previous["stored_path"])
            if old.exists():
                archive = self.settings.archive_path
                archive.mkdir(parents=True, exist_ok=True)
                target = archive / (
                    f"{previous['received_at']:%Y%m%d}_{previous['file_hash'][:8]}_{old.name}"
                )
                shutil.move(old, target)
                archived = str(target)

        dest = folder / name
        incoming.replace(dest)
        self.db.add_extract(
            {
                "file_hash": digest, "kind": kind, "file_name": name, "stored_path": str(dest),
                "route": route, "received_by": received_by or self.settings.default_user,
                "received_at": utcnow(), "rows": rows,
            },
            archived,
        )  # fmt: skip
        log.info("stored new %s extract %s (route %s)", kind, name, route)
        return IntakeResult("accepted", f"{kind} extract {name} accepted.", name, kind)
