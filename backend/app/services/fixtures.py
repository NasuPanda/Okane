"""Export the JSON fixtures the frontend develops against (``make fixtures``).

Fixtures are ALWAYS built from freshly generated synthetic workbooks in a temporary folder,
never from data/inbox, so committing ``fixtures/`` can never leak real data. Every file is
wrapped as ``{"synthetic": true, "generated_at": ..., "data": ...}``; CI rejects any fixture
without that marker.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings

FIXTURE_AS_OF = date(2026, 11, 18)


def _write(out: Path, name: str, data: Any) -> None:
    wrapped = {"synthetic": True, "generated_at": FIXTURE_AS_OF.isoformat(), "data": data}
    text = json.dumps(wrapped, indent=1, default=str) + "\n"
    (out / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")


def export_fixtures(out: Path) -> list[str]:
    """Run the API on synthetic data and save every response the screens need."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from generate_sample_data import generate

    from app.main import create_app

    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generate(root / "inbox")
        rates = root / "rates.csv"
        rates.write_text((REPO_ROOT / "backend/tests/data/rates.sample.csv").read_text("utf-8"))
        settings = Settings(
            data_dir=root, inbox_dir=root / "inbox", sample_dir=root / "sample",
            rates_path=rates, db_path=root / "okane.duckdb", as_of=FIXTURE_AS_OF,
            enable_watcher=False, enable_scheduler=False, run_on_startup=False,
            ai_enabled=False, frontend_dist=root / "no-dist",
        )  # fmt: skip
        with TestClient(create_app(settings)) as client:
            client.post("/api/runs", params={"wait": True}).raise_for_status()
            exceptions = client.get("/api/exceptions").json()
            details = {e["id"]: client.get(f"/api/exceptions/{e['id']}").json() for e in exceptions}
            comments = {
                e["id"]: client.post(f"/api/exceptions/{e['id']}/comment").json()
                for e in exceptions
            }
            timelines = {
                key: client.get(f"/api/pulse/{key}/timeline").json()
                for key in client.get("/api/pulse/accounts").json()
            }
            files = {
                "run": client.get("/api/runs/latest").json(),
                "exceptions": client.get("/api/exceptions").json(),
                "exception_details": details,
                "comments": comments,
                "exposure": client.get("/api/exposure/payroll").json(),
                "timelines": timelines,
                "rules": client.get("/api/rules").json(),
                "rules_log": client.get("/api/rules/log").json(),
                "kpis": client.get("/api/kpis").json(),
            }
    for name, data in files.items():
        _write(out, name, data)
    return sorted(files)


def main() -> None:
    out = REPO_ROOT / "fixtures"
    for name in export_fixtures(out):
        print(f"wrote fixtures/{name}.json")


if __name__ == "__main__":
    main()
