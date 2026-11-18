"""DuckDB connection and queries.

One file (``data/okane.duckdb``). Tables:

- ``snapshots`` / ``lines``: one snapshot per ingested workbook set, keyed by file hashes.
- ``runs`` / ``exceptions`` / ``run_artifacts``: one result set per run (a run reads one
  snapshot with one version of the rules).
- ``decisions`` / ``decision_log``: a person's decision per stable exception id, plus the audit
  trail. Decisions are joined onto every later run's exceptions.
- ``rules`` / ``rule_changes``: current rules and the append-only change log.
- ``ai_cache``: AI comments keyed by exception id plus facts hash.

All access goes through one connection guarded by a lock; DuckDB is fast enough that the
prototype does not need a pool.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from app.schemas import (
    DecisionEntry,
    ExceptionRecord,
    RuleChange,
    Rules,
    Run,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id VARCHAR PRIMARY KEY, created_at TIMESTAMP, files JSON, hashes JSON,
    synthetic BOOLEAN, row_counts JSON, warnings JSON);
CREATE TABLE IF NOT EXISTS lines (
    snapshot_id VARCHAR, line_id INTEGER, workbook VARCHAR, erp VARCHAR, sheet VARCHAR,
    source_row INTEGER, entity VARCHAR, account VARCHAR, account_name VARCHAR,
    document_no VARCHAR, item INTEGER, year INTEGER, period INTEGER, doc_type VARCHAR,
    posting_date DATE, doc_date DATE, amount_dc DOUBLE, currency_dc VARCHAR, amount_lc DOUBLE,
    currency_lc VARCHAR, amount_eur DOUBLE, eur_rate DOUBLE, partner VARCHAR, user_name VARCHAR,
    text VARCHAR, header_text VARCHAR, reference VARCHAR, assignment VARCHAR, age_days INTEGER,
    allowed_age INTEGER, overdue_abs DOUBLE, reversal VARCHAR);
CREATE TABLE IF NOT EXISTS runs (run_id VARCHAR PRIMARY KEY, started_at TIMESTAMP, payload JSON);
CREATE TABLE IF NOT EXISTS exceptions (
    run_id VARCHAR, id VARCHAR, type VARCHAR, workgroup VARCHAR, entity VARCHAR,
    score DOUBLE, exposure_eur DOUBLE, payload JSON);
CREATE TABLE IF NOT EXISTS run_artifacts (run_id VARCHAR, kind VARCHAR, key VARCHAR, payload JSON);
CREATE TABLE IF NOT EXISTS decisions (exception_id VARCHAR PRIMARY KEY, payload JSON);
CREATE SEQUENCE IF NOT EXISTS decision_seq;
CREATE TABLE IF NOT EXISTS decision_log (seq BIGINT, exception_id VARCHAR, payload JSON);
CREATE TABLE IF NOT EXISTS rules (id INTEGER PRIMARY KEY, payload JSON);
CREATE SEQUENCE IF NOT EXISTS rule_seq;
CREATE TABLE IF NOT EXISTS rule_changes (seq BIGINT, payload JSON);
CREATE TABLE IF NOT EXISTS ai_cache (cache_key VARCHAR PRIMARY KEY, payload JSON);
"""


def utcnow() -> datetime:
    """Timezone-aware now, stored as naive UTC in DuckDB."""
    return datetime.now(UTC).replace(tzinfo=None)


class Database:
    """Thin, thread-safe wrapper around one DuckDB connection."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self.path)
        self._lock = threading.RLock()
        with self.cursor() as cur:
            cur.execute(SCHEMA)

    @contextmanager
    def cursor(self) -> Iterator[duckdb.DuckDBPyConnection]:
        with self._lock:
            cur = self._con.cursor()
            try:
                yield cur
            finally:
                cur.close()

    def close(self) -> None:
        with self._lock:
            self._con.close()

    # ----- snapshots and lines -------------------------------------------------------------
    def snapshot_exists(self, snapshot_id: str) -> bool:
        with self.cursor() as cur:
            row = cur.execute(
                "SELECT 1 FROM snapshots WHERE snapshot_id = ?", [snapshot_id]
            ).fetchone()
        return row is not None

    def write_snapshot(
        self,
        snapshot_id: str,
        lines: pd.DataFrame,
        files: list[str],
        hashes: list[str],
        synthetic: bool,
        row_counts: dict[str, int],
        warnings: list[str],
    ) -> None:
        """Store the lines of one workbook set. Idempotent per snapshot id."""
        frame = lines.copy()
        frame.insert(0, "snapshot_id", snapshot_id)
        with self.cursor() as cur:
            cur.execute("DELETE FROM lines WHERE snapshot_id = ?", [snapshot_id])
            cur.execute("DELETE FROM snapshots WHERE snapshot_id = ?", [snapshot_id])
            cur.register("incoming_lines", frame)
            columns = ", ".join(frame.columns)
            cur.execute(f"INSERT INTO lines ({columns}) SELECT {columns} FROM incoming_lines")
            cur.unregister("incoming_lines")
            cur.execute(
                "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
                [snapshot_id, utcnow(), json.dumps(files), json.dumps(hashes), synthetic,
                 json.dumps(row_counts), json.dumps(warnings)],
            )  # fmt: skip

    def read_lines(self, snapshot_id: str) -> pd.DataFrame:
        """All lines of a snapshot as a DataFrame (identifier columns stay strings)."""
        with self.cursor() as cur:
            frame = cur.execute(
                "SELECT * EXCLUDE (snapshot_id) FROM lines WHERE snapshot_id = ? ORDER BY line_id",
                [snapshot_id],
            ).df()
        for col in ("posting_date", "doc_date"):
            frame[col] = pd.to_datetime(frame[col]).dt.date
        for col in ("item", "year", "period", "age_days", "allowed_age"):
            frame[col] = frame[col].astype("Int64")
        return frame

    def snapshot_info(self, snapshot_id: str) -> dict[str, Any] | None:
        with self.cursor() as cur:
            row = cur.execute(
                "SELECT files, hashes, synthetic, row_counts, warnings FROM snapshots "
                "WHERE snapshot_id = ?",
                [snapshot_id],
            ).fetchone()
        if row is None:
            return None
        return {
            "files": json.loads(row[0]),
            "hashes": json.loads(row[1]),
            "synthetic": bool(row[2]),
            "row_counts": json.loads(row[3]),
            "warnings": json.loads(row[4]),
        }

    # ----- runs ----------------------------------------------------------------------------
    def save_run(self, run: Run) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM runs WHERE run_id = ?", [run.run_id])
            cur.execute(
                "INSERT INTO runs VALUES (?, ?, ?)",
                [run.run_id, run.started_at, run.model_dump_json()],
            )

    def get_run(self, run_id: str) -> Run | None:
        with self.cursor() as cur:
            row = cur.execute("SELECT payload FROM runs WHERE run_id = ?", [run_id]).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def latest_run(self, finished_only: bool = True) -> Run | None:
        sql = "SELECT payload FROM runs"
        if finished_only:
            sql += " WHERE json_extract_string(payload, '$.status') = 'finished'"
        sql += " ORDER BY started_at DESC LIMIT 1"
        with self.cursor() as cur:
            row = cur.execute(sql).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def list_runs(self, limit: int = 20) -> list[Run]:
        with self.cursor() as cur:
            rows = cur.execute(
                "SELECT payload FROM runs ORDER BY started_at DESC LIMIT ?", [limit]
            ).fetchall()
        return [Run.model_validate_json(r[0]) for r in rows]

    # ----- exceptions ----------------------------------------------------------------------
    def save_exceptions(self, run_id: str, records: list[ExceptionRecord]) -> None:
        rows = [
            [run_id, r.id, r.type, r.workgroup, r.entity, r.score, r.exposure_eur,
             r.model_dump_json()]
            for r in records
        ]  # fmt: skip
        with self.cursor() as cur:
            cur.execute("DELETE FROM exceptions WHERE run_id = ?", [run_id])
            if rows:
                cur.executemany("INSERT INTO exceptions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

    def list_exceptions(self, run_id: str) -> list[ExceptionRecord]:
        with self.cursor() as cur:
            rows = cur.execute(
                "SELECT payload FROM exceptions WHERE run_id = ? ORDER BY score DESC, id",
                [run_id],
            ).fetchall()
        records = [ExceptionRecord.model_validate_json(r[0]) for r in rows]
        return self.apply_decisions(records)

    def get_exception(self, run_id: str, exception_id: str) -> ExceptionRecord | None:
        with self.cursor() as cur:
            row = cur.execute(
                "SELECT payload FROM exceptions WHERE run_id = ? AND id = ?",
                [run_id, exception_id],
            ).fetchone()
        if row is None:
            return None
        return self.apply_decisions([ExceptionRecord.model_validate_json(row[0])])[0]

    def update_exception_comment(
        self, run_id: str, exception_id: str, comment: str, verifier: str
    ) -> None:
        record = self.get_exception(run_id, exception_id)
        if record is None:
            return
        record = record.model_copy(update={"ai_comment": comment, "verifier": verifier})
        with self.cursor() as cur:
            cur.execute(
                "UPDATE exceptions SET payload = ? WHERE run_id = ? AND id = ?",
                [record.model_dump_json(), run_id, exception_id],
            )

    # ----- run artifacts (pulse timelines and batch matches) -------------------------------
    def save_artifact(self, run_id: str, kind: str, key: str, payload: str) -> None:
        with self.cursor() as cur:
            cur.execute(
                "DELETE FROM run_artifacts WHERE run_id = ? AND kind = ? AND key = ?",
                [run_id, kind, key],
            )
            cur.execute(
                "INSERT INTO run_artifacts VALUES (?, ?, ?, ?)", [run_id, kind, key, payload]
            )

    def get_artifact(self, run_id: str, kind: str, key: str) -> str | None:
        with self.cursor() as cur:
            row = cur.execute(
                "SELECT payload FROM run_artifacts WHERE run_id = ? AND kind = ? AND key = ?",
                [run_id, kind, key],
            ).fetchone()
        return row[0] if row else None

    # ----- decisions -----------------------------------------------------------------------
    def save_decision(self, entry: DecisionEntry) -> None:
        payload = entry.model_dump_json()
        with self.cursor() as cur:
            cur.execute("DELETE FROM decisions WHERE exception_id = ?", [entry.exception_id])
            cur.execute("INSERT INTO decisions VALUES (?, ?)", [entry.exception_id, payload])
            cur.execute(
                "INSERT INTO decision_log VALUES (nextval('decision_seq'), ?, ?)",
                [entry.exception_id, payload],
            )

    def decisions_for(self, exception_id: str) -> list[DecisionEntry]:
        with self.cursor() as cur:
            rows = cur.execute(
                "SELECT payload FROM decision_log WHERE exception_id = ? ORDER BY seq",
                [exception_id],
            ).fetchall()
        return [DecisionEntry.model_validate_json(r[0]) for r in rows]

    def apply_decisions(self, records: list[ExceptionRecord]) -> list[ExceptionRecord]:
        """Overlay the latest human decision on each record (ids are stable across runs)."""
        if not records:
            return records
        with self.cursor() as cur:
            rows = cur.execute("SELECT exception_id, payload FROM decisions").fetchall()
        latest = {r[0]: DecisionEntry.model_validate_json(r[1]) for r in rows}
        out = []
        for record in records:
            decision = latest.get(record.id)
            if decision is not None:
                record = record.model_copy(
                    update={
                        "status": decision.status,
                        "decision_reason": decision.decision_reason,
                        "decided_class": decision.decided_class,
                        "edited_comment": decision.edited_comment,
                    }
                )
            out.append(record)
        return out

    # ----- rules ---------------------------------------------------------------------------
    def get_rules(self) -> Rules:
        with self.cursor() as cur:
            row = cur.execute("SELECT payload FROM rules WHERE id = 1").fetchone()
        return Rules.model_validate_json(row[0]) if row else Rules()

    def save_rules(self, rules: Rules, changes: list[RuleChange]) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM rules WHERE id = 1")
            cur.execute("INSERT INTO rules VALUES (1, ?)", [rules.model_dump_json()])
            for change in changes:
                cur.execute(
                    "INSERT INTO rule_changes VALUES (?, ?)", [change.seq, change.model_dump_json()]
                )

    def next_rule_seq(self) -> int:
        with self.cursor() as cur:
            return int(cur.execute("SELECT nextval('rule_seq')").fetchone()[0])

    def rule_log(self) -> list[RuleChange]:
        with self.cursor() as cur:
            rows = cur.execute("SELECT payload FROM rule_changes ORDER BY seq DESC").fetchall()
        return [RuleChange.model_validate_json(r[0]) for r in rows]

    # ----- AI cache ------------------------------------------------------------------------
    def cache_get(self, key: str) -> dict[str, Any] | None:
        with self.cursor() as cur:
            row = cur.execute("SELECT payload FROM ai_cache WHERE cache_key = ?", [key]).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, key: str, payload: dict[str, Any]) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM ai_cache WHERE cache_key = ?", [key])
            cur.execute("INSERT INTO ai_cache VALUES (?, ?)", [key, json.dumps(payload)])
