"""Run orchestration (brief section 5, "Pipeline, per run").

1. Scan the watched folder through the intake step (A38), which copies a new extract into
   Okane's store; then read the current Payroll and Fixed assets extracts from the store (or the
   synthetic sample folder when the store is empty). Uploads reach the store the same way.
2. Ingest them into a DuckDB snapshot keyed by the file hashes (reused if already ingested).
   The analysis date is the day the Payroll extract was taken (A38), unless OKANE_AS_OF is set.
3. Run the engines in the brief's order: pairs, pulse, sentinel, typos, miner, lead time,
   exposure and score.
4. Attach cached AI comments; draft new ones for the top findings when a model is available.
5. Store the exceptions and pulse timelines for the run and emit ``run_started`` /
   ``run_finished`` events.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from app.ai import client as ai
from app.config import Settings
from app.database import Database, utcnow
from app.engines.exposure import inbox_view, payroll_netting, score_records
from app.engines.leadtime import apply_lead_time
from app.engines.miner import run_miner
from app.engines.pairs import paired_count
from app.engines.pulse import run_pulse
from app.engines.sentinel import run_sentinel
from app.engines.typos import run_typos
from app.ingest import IngestError, extract_dates, file_hash, find_workbooks, ingest, load_rates
from app.intake import Intake
from app.schemas import ExceptionRecord, ExtractRoute, ExtractSource, Rules, Run, RunTrigger
from app.services import schedule

log = logging.getLogger("okane.pipeline")


class RunInProgressError(RuntimeError):
    """A run is already going; runs never overlap."""


# ----- events -------------------------------------------------------------------------------
@dataclass
class EventBus:
    """Fan-out of run events to server-sent-event subscribers (thread-safe publish)."""

    _subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]] = field(
        default_factory=set
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers.add((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers = {s for s in self._subscribers if s[1] is not queue}

    def publish(self, event: str, data: dict[str, Any]) -> None:
        message = {"event": event, "data": json.dumps(data, default=str)}
        with self._lock:
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, message)
            except RuntimeError:  # the subscriber's loop has closed
                self.unsubscribe(queue)


# ----- engines (pure) -----------------------------------------------------------------------
@dataclass
class EngineOutput:
    records: list[ExceptionRecord]
    timelines: dict[str, str]
    counts: dict[str, int]


def run_engines(lines: pd.DataFrame, rules: Rules, as_of: Any) -> EngineOutput:
    """All engines in the brief's order. Pure: no I/O."""
    paired = paired_count(lines)
    pulse = run_pulse(lines, rules, as_of)
    records = pulse.records
    records += run_sentinel(lines, rules)
    records += run_typos(lines, rules)
    records += run_miner(lines, rules)
    records = apply_lead_time(records, lines, rules)
    netting = payroll_netting(lines, rules.materiality_eur)
    records = score_records(records, rules, as_of)
    records = [r.model_copy(update={"inbox_view": inbox_view(r, rules)}) for r in records]
    by_type = Counter(r.type for r in records)
    counts = {
        "lines": len(lines),
        "paired_lines": paired,
        "exceptions": len(records),
        "old_rule_lines": netting.old_rule_lines,
        "exposure_groups_above": netting.groups_above(),
        **{f"type:{k}": v for k, v in sorted(by_type.items())},
    }
    timelines = {key: r.to_timeline().model_dump_json() for key, r in pulse.profiles.items()}
    return EngineOutput(records=records, timelines=timelines, counts=counts)


# ----- orchestration ------------------------------------------------------------------------
class Pipeline:
    """Owns run state: one run at a time, events on start and finish."""

    def __init__(self, db: Database, settings: Settings, bus: EventBus | None = None) -> None:
        self.db = db
        self.settings = settings
        self.bus = bus or EventBus()
        self.intake = Intake(settings, db)
        self._lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: RunTrigger | None = None
        self._lines_cache: dict[str, pd.DataFrame] = {}

    # -- inputs
    def workbooks(self) -> tuple[list[Path], bool]:
        """The current extracts in Okane's store; else the synthetic sample folder."""
        paths = self.intake.current_paths()
        if paths:
            return paths, False
        return find_workbooks(self.settings.sample_dir), True

    def lines(self, snapshot_id: str) -> pd.DataFrame:
        if snapshot_id not in self._lines_cache:
            self._lines_cache = {snapshot_id: self.db.read_lines(snapshot_id)}
        return self._lines_cache[snapshot_id]

    def _scan(self, trigger: RunTrigger) -> list[str]:
        """Pick up new files in the watched folder (A38); returns warnings for refused files."""
        route: ExtractRoute = "manual" if trigger in ("upload", "rules_change") else trigger
        results = self.intake.scan_folder(self.settings.inbox_dir, route)
        return [
            f"{r.file_name} in the watched folder was not loaded: {r.message}"
            for r in results
            if r.status == "rejected"
        ]

    def _snapshot(self) -> tuple[str, list[str], list[str], bool, list[str]]:
        paths, synthetic = self.workbooks()
        if not paths:
            raise IngestError(
                f"No workbook found in {self.settings.inbox_dir} or {self.settings.sample_dir}. "
                "Upload an extract, drop one in the watched folder, or run "
                "`make generate-sample-data`."
            )
        hashes = [file_hash(p) for p in paths]
        snapshot_id = hashlib.sha256("|".join(sorted(hashes)).encode()).hexdigest()[:16]
        if self.db.snapshot_exists(snapshot_id):
            info = self.db.snapshot_info(snapshot_id) or {}
            return snapshot_id, info.get("files", []), hashes, synthetic, info.get("warnings", [])
        result = ingest(paths, load_rates(self.settings.rates_path))
        self.db.write_snapshot(
            snapshot_id, result.lines, result.files, result.hashes, synthetic,
            result.row_counts, result.warnings,
        )  # fmt: skip
        log.info("ingested snapshot %s (%d lines)", snapshot_id, len(result.lines))
        return snapshot_id, result.files, result.hashes, synthetic, result.warnings

    def sources(
        self, lines: pd.DataFrame, files: list[str], hashes: list[str]
    ) -> tuple[list[ExtractSource], list[str]]:
        """Where each workbook of the run came from, its extract date and whether it is late."""
        dates = extract_dates(lines)
        rows = lines.groupby("workbook").size().to_dict()
        stored = {e["file_hash"]: e for e in self.db.current_extracts()}
        weekday = schedule.weekday_index(self.settings.schedule_day_of_week)
        now = schedule.local_now()
        sources: list[ExtractSource] = []
        warnings: list[str] = []
        for name, digest in zip(files, hashes, strict=False):
            entry = stored.get(digest) or self.db.get_extract(digest)
            kind = entry["kind"] if entry else _kind_of(name, lines, dates)
            if kind is None:
                continue
            taken, disagree = dates.get(kind, (None, 0))
            if disagree:
                warnings.append(
                    f"{disagree} {kind} line(s) give a different extract date than {taken}; "
                    f"{taken} is used."
                )
            source = ExtractSource(
                kind=kind, file_name=name, file_hash=digest, extract_date=taken,
                rows=int(rows.get(kind, 0)),
            )  # fmt: skip
            if entry:
                received = schedule.utc_to_local(entry["received_at"])
                late, due = schedule.extract_status(
                    received, now, weekday, self.settings.schedule_hour,
                    self.settings.schedule_minute,
                )  # fmt: skip
                source = source.model_copy(
                    update={"route": entry["route"], "received_by": entry["received_by"],
                            "received_at": entry["received_at"], "late": late, "next_due": due}
                )  # fmt: skip
                if late:
                    warnings.append(
                        f"No new {kind} extract since {received:%d %b %Y}. This check used the "
                        "last extract received."
                    )
            sources.append(source)
        return sorted(sources, key=lambda s: s.kind, reverse=True), warnings

    def analysis_date(self, sources: list[ExtractSource]) -> Any:
        """OKANE_AS_OF, else the Payroll extract date, else today (A38)."""
        if self.settings.as_of is not None:
            return self.settings.as_of
        payroll = next((s for s in sources if s.kind == "Payroll" and s.extract_date), None)
        return payroll.extract_date if payroll else self.settings.today()

    # -- runs
    def start(self, trigger: RunTrigger, reuse_snapshot: bool = False) -> Run:
        """Begin a run and return it in state 'running'. Call ``execute`` to finish it."""
        if not self._lock.acquire(blocking=False):
            raise RunInProgressError("A run is already in progress")
        try:
            previous = self.db.latest_run() if reuse_snapshot else None
            run = Run(
                run_id=f"run_{utcnow():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}",
                snapshot_id=previous.snapshot_id if previous else "",
                trigger=trigger,
                status="running",
                source_files=previous.source_files if previous else [],
                file_hashes=previous.file_hashes if previous else [],
                synthetic=previous.synthetic if previous else False,
                as_of=previous.as_of if previous else self.settings.today(),
                sources=previous.sources if previous else [],
                started_at=utcnow(),
            )
            self.db.save_run(run)
            self.bus.publish("run_started", {"run_id": run.run_id, "trigger": trigger})
            return run
        except Exception:
            self._lock.release()
            raise

    def execute(self, run: Run) -> Run:
        """Finish a started run. Always releases the run lock and emits an event."""
        try:
            run = self._execute(run)
        except Exception as exc:
            log.exception("run %s failed", run.run_id)
            run = run.model_copy(
                update={"status": "failed", "error": str(exc), "finished_at": utcnow()}
            )
            self.db.save_run(run)
        finally:
            self._lock.release()
        self.bus.publish("run_finished", run.model_dump(mode="json"))
        self._run_pending()
        return run

    def _run_pending(self) -> None:
        with self._pending_lock:
            pending, self._pending = self._pending, None
        if pending is not None:
            log.info("running the %s trigger that arrived during the last run", pending)
            self.trigger(pending)

    def _execute(self, run: Run) -> Run:
        warnings: list[str] = list(run.warnings) if run.snapshot_id else []
        if not run.snapshot_id:
            warnings = self._scan(run.trigger)
            snapshot_id, files, hashes, synthetic, ingest_warnings = self._snapshot()
            lines = self.lines(snapshot_id)
            sources, source_warnings = self.sources(lines, files, hashes)
            warnings += ingest_warnings + source_warnings
            run = run.model_copy(
                update={"snapshot_id": snapshot_id, "source_files": files,
                        "file_hashes": hashes, "synthetic": synthetic, "sources": sources,
                        "as_of": self.analysis_date(sources)}
            )  # fmt: skip
            self.db.save_run(run)
        lines = self.lines(run.snapshot_id)
        rules = self.db.get_rules()
        output = run_engines(lines, rules, run.as_of)
        records = [r.model_copy(update={"run_id": run.run_id}) for r in output.records]
        records = self.attach_comments(records)
        self.db.save_exceptions(run.run_id, records)
        for key, payload in output.timelines.items():
            self.db.save_artifact(run.run_id, "timeline", key, payload)
        run = run.model_copy(
            update={"status": "finished", "finished_at": utcnow(), "counts": output.counts,
                    "warnings": warnings}
        )  # fmt: skip
        self.db.save_run(run)
        log.info("run %s finished: %d exceptions", run.run_id, len(records))
        return run

    def attach_comments(self, records: list[ExceptionRecord]) -> list[ExceptionRecord]:
        """Cached AI comments; new drafts for the top-ranked findings when a model runs."""
        predraft = self.settings.ai_enabled and self.settings.ai_predraft_top > 0
        if predraft and not ai.ollama_available(self.settings):
            predraft = False
        out = []
        for index, record in enumerate(records):
            hit = ai.cached_comment(record, self.db)
            if hit is None and predraft and index < self.settings.ai_predraft_top:
                drafted = ai.draft_comment(record, self.db, self.settings)
                hit = drafted if drafted.source == "model" else None
            if hit is not None:
                record = record.model_copy(
                    update={"ai_comment": hit.comment, "verifier": hit.verifier}
                )
            out.append(record)
        return out

    def run_now(self, trigger: RunTrigger, reuse_snapshot: bool = False) -> Run:
        """Start and finish a run in the calling thread."""
        return self.execute(self.start(trigger, reuse_snapshot))

    def run_in_background(self, trigger: RunTrigger, reuse_snapshot: bool = False) -> Run:
        """Start a run and finish it on a worker thread."""
        run = self.start(trigger, reuse_snapshot)
        threading.Thread(target=self.execute, args=(run,), daemon=True, name="okane-run").start()
        return run

    def trigger(self, trigger: RunTrigger) -> Run | None:
        """Fire-and-forget entry point for jobs and uploads.

        A busy pipeline remembers the trigger and runs it when the current run ends.
        """
        try:
            return self.run_in_background(trigger)
        except RunInProgressError:
            with self._pending_lock:
                self._pending = trigger  # ASSUMPTION (A38): run once more when this one ends
            log.info("%s trigger queued: a run is in progress", trigger)
            return None


def _kind_of(name: str, lines: pd.DataFrame, dates: dict[str, tuple[Any, int]]) -> str | None:
    """Kind of a workbook not in the store (the synthetic sample): by elimination or name.

    ASSUMPTION (A38): only the synthetic sample folder reaches this; real extracts get their
    kind from the intake step, which reads the sheets.
    """
    kinds = sorted(dates)
    if len(kinds) == 1:
        return kinds[0]
    lowered = name.lower()
    if "payroll" in lowered and "Payroll" in kinds:
        return "Payroll"
    if ("fixed" in lowered or "asset" in lowered) and "Fixed assets" in kinds:
        return "Fixed assets"
    return None
