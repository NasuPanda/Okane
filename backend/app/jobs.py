"""Folder watcher (watchdog) and weekly scheduler (APScheduler).

- A workbook created in or moved into ``data/inbox`` starts a run after a short debounce, so a
  file still being copied is not read half-written. Excel lock files (``~$...``) are ignored.
- APScheduler runs the pipeline every Monday at 06:00 (configurable).

Both only call ``trigger(name)``; the pipeline decides whether a run is already going.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import Settings
from app.ingest import WORKBOOK_SUFFIXES

log = logging.getLogger("okane.jobs")
Trigger = Callable[[str], None]


def is_workbook(path: str) -> bool:
    name = Path(path).name
    return name.lower().endswith(WORKBOOK_SUFFIXES) and not name.startswith("~$")


class InboxHandler(FileSystemEventHandler):
    """Debounced: many file events for one copy produce one run."""

    def __init__(self, trigger: Trigger, debounce_s: float) -> None:
        self.trigger = trigger
        self.debounce_s = debounce_s
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory or event.event_type not in {"created", "moved", "modified"}:
            return
        path = getattr(event, "dest_path", "") or event.src_path
        if not is_workbook(str(path)):
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_s, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        log.info("new workbook in inbox: starting a run")
        self.trigger("watcher")

    def cancel(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()


class Jobs:
    """Starts and stops the watcher and the scheduler according to settings."""

    def __init__(self, settings: Settings, trigger: Trigger) -> None:
        self.settings = settings
        self.trigger = trigger
        self.observer: Observer | None = None  # type: ignore[valid-type]
        self.handler: InboxHandler | None = None
        self.scheduler: BackgroundScheduler | None = None

    def start(self) -> None:
        if self.settings.enable_watcher:
            self.settings.inbox_dir.mkdir(parents=True, exist_ok=True)
            self.handler = InboxHandler(self.trigger, self.settings.watcher_debounce_s)
            self.observer = Observer()
            self.observer.schedule(self.handler, str(self.settings.inbox_dir), recursive=False)
            self.observer.daemon = True
            self.observer.start()
            log.info("watching %s", self.settings.inbox_dir)
        if self.settings.enable_scheduler:
            self.scheduler = BackgroundScheduler(daemon=True)
            self.scheduler.add_job(
                self.trigger,
                CronTrigger(
                    day_of_week=self.settings.schedule_day_of_week,
                    hour=self.settings.schedule_hour,
                    minute=self.settings.schedule_minute,
                ),
                args=["schedule"],
                id="weekly-run",
            )
            self.scheduler.start()
            log.info(
                "weekly run scheduled: %s %02d:%02d",
                self.settings.schedule_day_of_week,
                self.settings.schedule_hour,
                self.settings.schedule_minute,
            )

    def stop(self) -> None:
        if self.handler is not None:
            self.handler.cancel()
        if self.observer is not None:
            self.observer.stop()
            self.observer.join(timeout=5)
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
