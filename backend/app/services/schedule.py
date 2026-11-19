"""When a weekly extract is due and when it is late (docs/ASSUMPTIONS.md A38). Pure functions.

The weekly run fires on ``schedule_day_of_week`` at ``schedule_hour:schedule_minute`` (Monday
06:00 by default). Let B be the most recent scheduled run at or before now. One extract is
expected per week, so:

- an extract is **late** when it was received before B - 7 days (nothing new since the run
  before last; at the Monday run itself that means "none since last Monday's run");
- the **next extract is due** by the next scheduled run, B + 7 days.

Times are naive local time; ``received_at`` is stored as naive UTC and converted first.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEK = timedelta(days=7)


def weekday_index(day_of_week: str) -> int:
    """'mon' -> 0. ASSUMPTION (A38): a list or range ('mon-fri') counts its first day only."""
    first = day_of_week.strip().lower()[:3]
    return WEEKDAYS.index(first) if first in WEEKDAYS else 0


def last_scheduled_run(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    """The most recent scheduled run at or before ``now``."""
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate -= timedelta(days=(now.weekday() - weekday) % 7)
    if candidate > now:
        candidate -= WEEK
    return candidate


def utc_to_local(moment: datetime) -> datetime:
    """Naive UTC (as stored) -> naive local time."""
    return moment.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)


def local_now() -> datetime:
    """Naive local now; tests monkeypatch this."""
    return datetime.now()


def extract_status(
    received_at_local: datetime, now: datetime, weekday: int, hour: int, minute: int
) -> tuple[bool, datetime]:
    """``(late, next_due)`` for an extract received at ``received_at_local``."""
    boundary = last_scheduled_run(now, weekday, hour, minute)
    return received_at_local < boundary - WEEK, boundary + WEEK
