"""The demo path in docs/DEMO.md, walked through the API on synthetic data (#25, A2).

Each assertion is a number or ranking the script tells the presenter to expect. When this test
fails, decide whether the script or the product is wrong before changing either.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from tests.conftest import SAMPLE_RATES


def demo_layout(root: Path) -> Path:
    """The demo start state: Fixed assets and last week's Payroll in the inbox; this week's
    Payroll waiting in ``ready/`` for step 2. Returns the file to upload."""
    from generate_sample_data import generate, generate_previous_week

    inbox, ready = root / "inbox", root / "ready"
    inbox.mkdir(parents=True)
    payroll, fixed_assets = generate(ready)
    shutil.move(str(fixed_assets), inbox / fixed_assets.name)
    generate_previous_week(inbox)
    shutil.copy(SAMPLE_RATES, root / "rates.csv")
    return payroll


def demo_settings(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the app at ``root`` (as ``make demo`` does), without a pinned analysis date."""
    env = {
        "OKANE_DATA_DIR": root, "OKANE_INBOX_DIR": root / "inbox",
        "OKANE_RATES_PATH": root / "rates.csv", "OKANE_DB_PATH": root / "okane.duckdb",
        "OKANE_SAMPLE_DIR": root / "sample", "OKANE_FIXTURES_DIR": root / "fixtures",
        "OKANE_ENABLE_WATCHER": "false", "OKANE_ENABLE_SCHEDULER": "false",
        "OKANE_RUN_ON_STARTUP": "false", "OKANE_AI_ENABLED": "false",
    }  # fmt: skip
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.delenv("OKANE_AS_OF", raising=False)
    get_settings.cache_clear()


@pytest.fixture
def demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Path]]:
    payroll = demo_layout(tmp_path / "demo")
    demo_settings(tmp_path / "demo", monkeypatch)
    with TestClient(create_app(get_settings())) as client:
        yield client, payroll
    get_settings.cache_clear()


def _wait(client: TestClient) -> dict[str, object]:
    deadline = time.time() + 30
    while time.time() < deadline:
        run = client.get("/api/runs/latest").json()
        if run and run["status"] != "running":
            return run  # type: ignore[no-any-return]
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def walk_demo_path(client: TestClient, payroll: Path) -> None:
    """The six steps of docs/DEMO.md, with the figures the script promises."""
    # Before the demo: last week's run (the app's run on start-up, or "Run now").
    assert client.post("/api/runs", params={"wait": True}).json()["status"] == "finished"
    assert client.get("/api/runs/latest").json()["as_of"] == "2026-10-16"

    # Step 1, the old report: 72 lines "overdue", 11.36M.
    kpis = client.get("/api/kpis").json()
    assert kpis["old_rule_lines"] == 72
    assert round(kpis["old_rule_overdue_abs"] / 1e6, 2) == 11.36
    assert kpis["exceptions"] == 13

    # Step 2, upload this week's Payroll extract: a run starts, the extract is dated 23 Oct.
    response = client.post(
        "/api/uploads", params={"filename": payroll.name}, content=payroll.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
    )  # fmt: skip
    assert response.status_code == 202, response.text
    run = _wait(client)
    assert (run["trigger"], run["status"], run["as_of"]) == ("upload", "finished", "2026-10-23")
    sources = {s["kind"]: s for s in run["sources"]}  # type: ignore[union-attr]
    payroll_source = sources["Payroll"]
    assert (payroll_source["route"], payroll_source["extract_date"]) == ("upload", "2026-10-23")

    # Step 3, real exposure: 3 of 6 accounts remain at 500K; 6 findings need a look first.
    exposure = client.get("/api/exposure/payroll").json()
    assert (exposure["groups_above"], len(exposure["groups"])) == (3, 6)
    kpis = client.get("/api/kpis").json()
    assert (kpis["exceptions"], kpis["inbox_views"]["attention"]) == (14, 6)
    assert kpis["inbox_views"]["prompts"] == 3 and kpis["inbox_views"]["repeats"] == 1
    assert kpis["median_days_earlier"] == 16  # closing line: "Spotted earlier by"

    # Step 4, the top finding is the C192 social security gap, with a wrong-month prompt.
    attention = client.get("/api/exceptions", params={"view": "attention"}).json()
    top = attention[0]
    assert (top["type"], top["entity"], top["account"], top["score"]) == (
        "pulse_gap", "C192", "279006", 90.0)  # fmt: skip
    assert top["facts"]["lead_badge"] == "Today's process would miss this"
    assert client.get(f"/api/exceptions/{top['id']}").json()["timeline"]
    prompts = client.get("/api/exceptions", params={"view": "prompts"}).json()
    assert any(r["type"] == "label_mismatch" and r["entity"] == "C192" for r in prompts)
    comment = client.post(f"/api/exceptions/{top['id']}/comment").json()
    assert comment["comment"].startswith("Standard note (no AI was used):"), "no model in tests"

    # Step 5, Sentinel: the person-posted Payroll outlier, caught before the close review.
    outliers = client.get("/api/exceptions", params={"type": "sentinel_outlier"}).json()
    payroll_outlier = next(r for r in outliers if r["workgroup"] == "Payroll")
    assert (payroll_outlier["entity"], payroll_outlier["account"]) == ("C192", "279002")
    assert payroll_outlier["facts"]["posted_by"] == "person"
    assert payroll_outlier["facts"]["lead_badge"] == "Caught 32 days before the close review"
    # ... and the repeated manual posting that arrived with this week's extract (#31 card).
    [miner] = client.get("/api/exceptions", params={"view": "repeats"}).json()
    assert (miner["entity"], miner["facts"]["months"], miner["facts"]["entities"]) == ("C132", 6, 2)

    # Step 6, Rules: materiality 100K with a reason; 3 accounts become 4; the change is logged.
    rules = client.get("/api/rules").json()
    body = {"rules": {**rules, "materiality_eur": 100_000}, "reason": "Quarter-end review",
            "changed_by": "controller"}  # fmt: skip
    assert client.put("/api/rules", json=body).status_code == 200
    _wait(client)
    assert client.get("/api/exposure/payroll").json()["groups_above"] == 4
    assert client.get("/api/kpis").json()["inbox_views"]["attention"] == 6
    [entry] = client.get("/api/rules/log").json()
    assert (entry["field"], entry["reason"]) == ("materiality_eur", "Quarter-end review")
    top = client.get("/api/exceptions", params={"view": "attention"}).json()[0]
    assert (top["type"], top["entity"]) == ("pulse_gap", "C192")


def test_demo_path_on_synthetic_data(demo: tuple[TestClient, Path]) -> None:
    client, payroll = demo
    walk_demo_path(client, payroll)
