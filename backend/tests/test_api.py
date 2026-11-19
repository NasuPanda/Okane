"""API tests: every endpoint on synthetic data, plus events, jobs, fixtures and static serving."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.runs import events
from app.config import get_settings
from app.jobs import InboxHandler, Jobs, is_workbook
from app.main import create_app


@pytest.fixture
def client(app_env: Path) -> Iterator[TestClient]:
    with TestClient(create_app(get_settings())) as test_client:
        yield test_client


@pytest.fixture
def ran(client: TestClient) -> TestClient:
    response = client.post("/api/runs", params={"wait": True})
    assert response.status_code == 202
    assert response.json()["status"] == "finished", response.json().get("error")
    return client


def wait_for_run(client: TestClient, timeout: float = 30) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get("/api/runs/latest").json()
        if run and run["status"] != "running":
            return run  # type: ignore[no-any-return]
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def by_type(client: TestClient, type_: str) -> list[dict[str, object]]:
    return client.get("/api/exceptions", params={"type": type_}).json()  # type: ignore[no-any-return]


# ----- before the first run -----------------------------------------------------------------
def test_empty_state(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/runs/latest").json() is None
    assert client.get("/api/exceptions").status_code == 404
    assert client.get("/api/exposure/payroll").status_code == 404
    kpis = client.get("/api/kpis").json()
    assert kpis["run_id"] is None and kpis["exceptions"] == 0


# ----- runs ---------------------------------------------------------------------------------
def test_run_synchronously(ran: TestClient) -> None:
    run = ran.get("/api/runs/latest").json()
    assert run["status"] == "finished"
    assert run["synthetic"] is False  # synthetic files were copied into the temp inbox
    assert sorted(run["source_files"]) == ["Fixed_assets_sample.xlsx", "Payroll_sample.xlsx"]
    assert run["counts"]["exceptions"] > 0
    assert len(ran.get("/api/runs").json()) == 1


def test_run_in_background_and_conflict(client: TestClient) -> None:
    started = client.post("/api/runs")
    assert started.status_code == 202
    assert started.json()["status"] == "running"
    assert wait_for_run(client)["status"] == "finished"
    pipeline = client.app.state.okane.pipeline  # type: ignore[attr-defined]
    pipeline._lock.acquire()
    try:
        assert client.post("/api/runs").status_code == 409
    finally:
        pipeline._lock.release()


def test_run_without_workbooks_fails_clearly(client: TestClient, app_env: Path) -> None:
    for workbook in (app_env / "inbox").iterdir():
        workbook.unlink()
    run = client.post("/api/runs", params={"wait": True}).json()
    assert run["status"] == "failed"
    assert "generate-sample-data" in run["error"]


def test_events_stream_yields_run_events(client: TestClient) -> None:
    state = client.app.state.okane  # type: ignore[attr-defined]

    async def scenario() -> list[str]:
        request = SimpleNamespace(is_disconnected=_never_disconnected)
        response = await events(request, state)  # type: ignore[arg-type]
        iterator = response.body_iterator
        received = [(await anext(iterator))["event"]]  # type: ignore[index]
        state.bus.publish("run_started", {"run_id": "r1"})
        state.bus.publish("run_finished", {"run_id": "r1", "status": "finished"})
        for _ in range(2):
            received.append((await anext(iterator))["event"])  # type: ignore[index]
        await iterator.aclose()  # type: ignore[attr-defined]
        return received

    assert asyncio.run(scenario()) == ["ready", "run_started", "run_finished"]


async def _never_disconnected() -> bool:
    return False


def test_pipeline_publishes_start_and_finish(client: TestClient) -> None:
    state = client.app.state.okane  # type: ignore[attr-defined]

    async def scenario() -> list[str]:
        queue = state.bus.subscribe()
        await asyncio.to_thread(state.pipeline.run_now, "manual")
        names = []
        for _ in range(2):
            message = await asyncio.wait_for(queue.get(), timeout=5)
            names.append(message["event"])
        payload = json.loads(message["data"])
        assert payload["status"] == "finished"
        state.bus.unsubscribe(queue)
        return names

    assert asyncio.run(scenario()) == ["run_started", "run_finished"]


# ----- exceptions ---------------------------------------------------------------------------
def test_exceptions_sorted_and_filtered(ran: TestClient) -> None:
    records = ran.get("/api/exceptions").json()
    scores = [r["score"] for r in records]
    assert scores == sorted(scores, reverse=True)
    assert all(r["evidence"] or r["type"] == "pulse_missing_batch" for r in records)
    assert all("rule" in r["facts"] for r in records)
    assert {r["type"] for r in by_type(ran, "pulse_gap")} == {"pulse_gap"}
    fixed = ran.get("/api/exceptions", params={"workgroup": "Fixed assets"}).json()
    assert fixed and all(r["workgroup"] == "Fixed assets" for r in fixed)
    c218 = ran.get("/api/exceptions", params={"entity": "C218"}).json()
    assert c218 and all(r["entity"] == "C218" for r in c218)
    big = ran.get("/api/exceptions", params={"min_exposure": 1_000_000}).json()
    assert big and all(abs(r["exposure_eur"]) >= 1_000_000 for r in big)
    assert ran.get("/api/exceptions", params={"status": "dismissed"}).json() == []
    assert ran.get("/api/exceptions", params={"type": "nonsense"}).status_code == 422


def test_exception_detail(ran: TestClient) -> None:
    gap = by_type(ran, "pulse_gap")[0]
    detail = ran.get(f"/api/exceptions/{gap['id']}").json()
    assert detail["exception"]["id"] == gap["id"]
    assert detail["evidence_lines"], "evidence lines are one click away"
    assert {line["document"] for line in detail["evidence_lines"]} <= set(gap["evidence"])
    assert detail["timeline"] and {"balance", "expected", "gap"} <= set(detail["timeline"][0])
    outlier = by_type(ran, "sentinel_outlier")[0]
    assert ran.get(f"/api/exceptions/{outlier['id']}").json()["timeline"] is None
    assert ran.get("/api/exceptions/does-not-exist").status_code == 404


def test_decision_needs_reason_and_survives_rerun(ran: TestClient) -> None:
    gap = by_type(ran, "pulse_gap")[0]
    url = f"/api/exceptions/{gap['id']}"
    assert ran.patch(url, json={"status": "dismissed"}).status_code == 422
    assert ran.patch(url, json={"status": "dismissed", "decision_reason": "  "}).status_code == 422
    body = {"status": "explained", "decision_reason": "Timing: paid in October",
            "decided_class": "Timing item", "decided_by": "preparer"}  # fmt: skip
    updated = ran.patch(url, json=body).json()
    assert (updated["status"], updated["decided_class"]) == ("explained", "Timing item")
    edited = ran.patch(url, json={"edited_comment": "Checked with payroll."}).json()
    assert edited["edited_comment"] == "Checked with payroll."
    assert edited["decision_reason"] == "Timing: paid in October"
    ran.post("/api/runs", params={"wait": True})
    again = ran.get(url).json()
    assert again["exception"]["status"] == "explained", "stable ids keep decisions"
    assert [d["decided_by"] for d in again["decisions"]] == ["preparer", "controller"]


def test_comment_without_model_is_labelled_template(ran: TestClient) -> None:
    gap = by_type(ran, "pulse_gap")[0]
    comment = ran.post(f"/api/exceptions/{gap['id']}/comment").json()
    assert comment["source"] == "template"
    assert comment["verifier"] == "not_run"
    assert comment["comment"].startswith("Standard note")
    stored = ran.get(f"/api/exceptions/{gap['id']}").json()["exception"]
    assert stored["ai_comment"] == comment["comment"]


# ----- exposure, pulse, kpis ----------------------------------------------------------------
def test_exposure_with_live_materiality(ran: TestClient) -> None:
    default = ran.get("/api/exposure/payroll").json()
    assert default["materiality_eur"] == 500_000
    assert default["groups_above"] == 3
    assert default["old_rule_lines"] > 0 and default["old_rule_overdue_abs"] > 0
    lower = ran.get("/api/exposure/payroll", params={"materiality": 100_000}).json()
    assert lower["groups_above"] == 4
    c192 = next(g for g in default["groups"] if (g["entity"], g["account"]) == ("C192", "279006"))
    assert c192["exception_id"] is not None
    assert ran.get("/api/exposure/payroll", params={"materiality": -1}).status_code == 422


def test_pulse_timeline(ran: TestClient) -> None:
    accounts = ran.get("/api/pulse/accounts").json()
    assert accounts == ["P20/C192/279006", "BPP/C242/34900015"]
    timeline = ran.get("/api/pulse/P20/C192/279006/timeline").json()
    assert timeline["label"] == "C192 social security"
    months = [p["month"] for p in timeline["points"]]
    assert "2026-09" in months and months == sorted(months)
    assert sum(b["matched"] for b in timeline["batches"]) == 16
    assert timeline["lag_p90"] is not None
    assert ran.get("/api/pulse/P20/C192/999999/timeline").status_code == 404


def test_kpis(ran: TestClient) -> None:
    kpis = ran.get("/api/kpis").json()
    assert kpis["exceptions"] == sum(kpis["by_type"].values())
    assert kpis["median_days_earlier"] is not None and kpis["median_days_earlier"] > 0
    assert kpis["blind_spots"] >= 1
    assert kpis["exposure_groups_above"] == 3


# ----- rules --------------------------------------------------------------------------------
def test_rules_change_is_logged_and_reruns(ran: TestClient) -> None:
    rules = ran.get("/api/rules").json()
    assert rules["materiality_eur"] == 500_000 and rules["weights"]["exposure"] == 40
    first_run = ran.get("/api/runs/latest").json()["run_id"]
    assert ran.put("/api/rules", json={"rules": rules, "reason": ""}).status_code == 422
    unchanged = ran.put("/api/rules", json={"rules": rules, "reason": "no change"})
    assert unchanged.status_code == 200 and ran.get("/api/rules/log").json() == []
    bad = {**rules, "typo_max_edits": 0}
    refused = ran.put("/api/rules", json={"rules": bad, "reason": "slip"})
    assert refused.status_code == 422, "#13: typo thresholds are bounded"
    bad = {**rules, "missing_payment_lookback_months": 0}
    refused = ran.put("/api/rules", json={"rules": bad, "reason": "slip"})
    assert refused.status_code == 422, "#20: the missing-payment look-back is at least 1 month"
    assert ran.get("/api/rules/log").json() == []

    rules["materiality_eur"] = 100_000
    rules["weights"]["repeats"] = 5
    body = {"rules": rules, "reason": "Quarter-end review", "changed_by": "controller.a"}
    assert ran.put("/api/rules", json=body).json()["materiality_eur"] == 100_000
    log = ran.get("/api/rules/log").json()
    assert {e["field"] for e in log} == {"materiality_eur", "weights.repeats"}
    entry = next(e for e in log if e["field"] == "materiality_eur")
    assert json.loads(entry["old_value"]) == 500_000
    assert json.loads(entry["new_value"]) == 100_000
    assert entry["changed_by"] == "controller.a" and entry["reason"] == "Quarter-end review"

    run = wait_for_run(ran)
    assert run["trigger"] == "rules_change" and run["run_id"] != first_run
    assert ran.get("/api/exposure/payroll").json()["groups_above"] == 4


def test_saved_rules_from_before_17_load_without_a_phantom_change(tmp_path: Path) -> None:
    """Rules saved before #17 carry close_review_days and lack the new lead-time fields: they
    load with the defaults, and saving them unchanged logs nothing (A8)."""
    from pydantic import ValidationError

    from app.api.rules import diff_rules
    from app.database import Database
    from app.schemas import Rules

    old = json.loads(Rules().model_dump_json())
    for field in ("close_review_working_day", "close_review_holidays", "lead_time_view",
                  "weekly_run_weekday", "miner_min_score", "miner_by_user"):  # fmt: skip
        old.pop(field)
    old["close_review_days"] = 5
    db = Database(tmp_path / "rules.duckdb")
    with db.cursor() as cur:
        cur.execute("INSERT INTO rules VALUES (1, ?)", [json.dumps(old)])
    loaded = db.get_rules()
    db.close()
    assert loaded.close_review_working_day == 5 and loaded.lead_time_view == "weekly"
    assert not hasattr(loaded, "close_review_days")
    assert diff_rules(loaded, Rules()) == [], "no phantom change-log entry"
    with pytest.raises(ValidationError):
        Rules(close_review_working_day=0)
    assert Rules(close_review_working_day=1).close_review_working_day == 1


def test_saved_rules_from_before_19_load_without_a_phantom_change(tmp_path: Path) -> None:
    """Rules saved before #19 carry repeats_cap and lack repeats_min_months: they load with the
    default (3) and saving them unchanged logs nothing (A9)."""
    from pydantic import ValidationError

    from app.api.rules import diff_rules
    from app.database import Database
    from app.schemas import Rules

    old = json.loads(Rules().model_dump_json())
    old.pop("repeats_min_months")
    old["repeats_cap"] = 5
    db = Database(tmp_path / "rules.duckdb")
    with db.cursor() as cur:
        cur.execute("INSERT INTO rules VALUES (1, ?)", [json.dumps(old)])
    loaded = db.get_rules()
    db.close()
    assert loaded.repeats_min_months == 3
    assert not hasattr(loaded, "repeats_cap")
    assert diff_rules(loaded, Rules()) == [], "no phantom change-log entry"
    with pytest.raises(ValidationError):
        Rules(repeats_min_months=0)


# ----- jobs ---------------------------------------------------------------------------------
def test_watcher_debounces_workbook_events() -> None:
    fired: list[str] = []
    handler = InboxHandler(fired.append, debounce_s=0.05)
    for name in ("Payroll.xlsx", "Payroll.xlsx", "~$Payroll.xlsx", "notes.txt"):
        handler.on_any_event(SimpleNamespace(is_directory=False, event_type="created",
                                             src_path=f"/inbox/{name}", dest_path=""))  # fmt: skip
    time.sleep(0.3)
    assert fired == ["watcher"]
    assert is_workbook("a.xlsm") and not is_workbook("~$a.xlsx") and not is_workbook("a.csv")


def test_watcher_starts_a_run_when_a_workbook_lands(app_env: Path) -> None:
    import os
    import shutil

    os.environ["OKANE_ENABLE_WATCHER"] = "true"
    os.environ["OKANE_WATCHER_DEBOUNCE_S"] = "0.2"
    get_settings.cache_clear()
    inbox = app_env / "inbox"
    held = app_env / "held"
    held.mkdir()
    for workbook in inbox.iterdir():
        shutil.move(workbook, held / workbook.name)
    with TestClient(create_app(get_settings())) as test_client:
        for workbook in held.iterdir():
            shutil.copy(workbook, inbox / workbook.name)
        deadline = time.time() + 30
        run = None
        while time.time() < deadline:
            run = test_client.get("/api/runs/latest").json()
            if run and run["status"] == "finished":
                break
            time.sleep(0.2)
        assert run and run["trigger"] == "watcher" and run["status"] == "finished"
        assert {s["route"] for s in run["sources"]} == {"watcher"}


def test_scheduler_registers_monday_job(app_env: Path) -> None:
    settings = get_settings().model_copy(update={"enable_scheduler": True})
    jobs = Jobs(settings, lambda name: None)
    jobs.start()
    try:
        job = jobs.scheduler.get_job("weekly-run")  # type: ignore[union-attr]
        assert job.next_run_time.weekday() == 0
        assert (job.next_run_time.hour, job.next_run_time.minute) == (6, 0)
    finally:
        jobs.stop()


# ----- extract intake (A38) -----------------------------------------------------------------
def upload(client: TestClient, path: Path, name: str | None = None):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/uploads", params={"filename": name or path.name}, content=path.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
    )  # fmt: skip


def test_upload_starts_a_run(client: TestClient, synthetic_dir: Path) -> None:
    response = upload(client, synthetic_dir / "Payroll_sample.xlsx")
    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["status"], body["kind"]) == ("accepted", "Payroll")
    run = wait_for_run(client)
    assert (run["trigger"], run["status"]) == ("upload", "finished"), run.get("error")
    routes = {s["kind"]: s["route"] for s in run["sources"]}  # type: ignore[union-attr]
    # the upload, plus the Fixed assets file the run's folder scan picked up
    assert routes == {"Payroll": "upload", "Fixed assets": "manual"}
    payroll = next(s for s in run["sources"] if s["kind"] == "Payroll")  # type: ignore[union-attr]
    assert payroll["extract_date"] == "2026-10-23" and payroll["received_by"] == "controller"
    assert payroll["late"] is False and payroll["next_due"]


def test_upload_refuses_a_wrong_file_and_a_duplicate(
    client: TestClient, synthetic_dir: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "notes.xlsx"
    bad.write_text("hello")
    assert upload(client, bad).status_code == 422
    assert upload(client, bad, "notes.csv").status_code == 422
    assert upload(client, bad, "../evil.xlsx").status_code == 422
    assert client.get("/api/runs/latest").json() is None  # no run for a refused file

    assert upload(client, synthetic_dir / "Payroll_sample.xlsx").status_code == 202
    first = wait_for_run(client)
    again = upload(client, synthetic_dir / "Payroll_sample.xlsx", "Payroll_again.xlsx")
    assert again.status_code == 409 and "already loaded" in again.json()["detail"]
    assert client.get("/api/runs/latest").json()["run_id"] == first["run_id"]


def test_the_newest_upload_wins_and_the_old_one_is_archived(
    client: TestClient, synthetic_dir: Path, app_env: Path
) -> None:
    from tests.conftest import rewrite_workbook

    assert upload(client, synthetic_dir / "Payroll_sample.xlsx").status_code == 202
    wait_for_run(client)
    newer = rewrite_workbook(synthetic_dir / "Payroll_sample.xlsx", app_env / "Payroll_w47.xlsx",
                             drop_last_rows=1)  # fmt: skip
    assert upload(client, newer).status_code == 202
    run = wait_for_run(client)
    assert "Payroll_w47.xlsx" in run["source_files"]  # type: ignore[operator]
    [archived] = (app_env / "archive").iterdir()
    assert archived.name.endswith("Payroll_sample.xlsx")


def test_the_watched_folder_reaches_the_same_store(ran: TestClient, app_env: Path) -> None:
    run = ran.get("/api/runs/latest").json()
    assert {s["route"] for s in run["sources"]} == {"manual"}
    stored = sorted(p.name for p in (app_env / "extracts").rglob("*.xlsx"))
    assert stored == sorted(p.name for p in (app_env / "inbox").iterdir())
    assert all((app_env / "inbox" / name).exists() for name in stored)  # folder untouched


def test_analysis_date_is_the_payroll_extract_date(
    app_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OKANE_AS_OF")
    get_settings.cache_clear()
    with TestClient(create_app(get_settings())) as test_client:
        run = test_client.post("/api/runs", params={"wait": True}).json()
    assert run["as_of"] == "2026-10-23"
    assert {s["kind"]: s["extract_date"] for s in run["sources"]} == {
        "Payroll": "2026-10-23", "Fixed assets": "2026-10-02"}  # fmt: skip


def test_a_monday_run_without_a_new_extract_is_flagged_late(
    ran: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta

    from app.services import schedule

    later = datetime.now() + timedelta(days=15)
    monday_run = schedule.last_scheduled_run(later, 0, 6, 0)
    monkeypatch.setattr(schedule, "local_now", lambda: monday_run)
    run = ran.post("/api/runs", params={"wait": True}).json()
    assert run["status"] == "finished"
    assert all(s["late"] for s in run["sources"])
    assert any("No new Payroll extract since" in w for w in run["warnings"])


# ----- fixtures and static serving ----------------------------------------------------------
def test_fixture_export_is_synthetic(tmp_path: Path) -> None:
    from app.services.fixtures import export_fixtures

    names = export_fixtures(tmp_path)
    assert {"exceptions", "exposure", "timelines", "rules", "kpis", "run"} <= set(names)
    for name in names:
        payload = json.loads((tmp_path / f"{name}.json").read_text("utf-8"))
        assert payload["synthetic"] is True
    exposure = json.loads((tmp_path / "exposure.json").read_text("utf-8"))["data"]
    assert exposure["groups_above"] == 3


def test_serves_built_frontend(app_env: Path) -> None:
    dist = app_env / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>okane</html>", "utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", "utf-8")
    settings = get_settings().model_copy(update={"frontend_dist": dist})
    with TestClient(create_app(settings)) as test_client:
        assert "okane" in test_client.get("/").text
        assert "okane" in test_client.get("/inbox").text
        assert test_client.get("/assets/app.js").text == "console.log(1)"
        assert test_client.get("/api/nope").status_code == 404
        assert test_client.get("/api/health").json() == {"status": "ok"}
