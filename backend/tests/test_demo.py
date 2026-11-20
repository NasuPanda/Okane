"""The demo path in docs/DEMO.md, walked through the API on synthetic data (#25, A2).

Each assertion is a number or ranking the script tells the presenter to expect. When this test
fails, decide whether the script or the product is wrong before changing either.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def demo_layout(root: Path) -> Path:
    """The demo start state (scripts/demo_reset.py): Fixed assets and last week's Payroll in the
    inbox; this week's Payroll waiting in ``ready/`` for step 2. Returns the file to upload."""
    from demo_reset import build_demo_folder

    return build_demo_folder(root)


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
    feed_types = {
        "sentinel_outlier",
        "sentinel_two_currencies",
        "sentinel_currency_code",
        "sentinel_reversal",
        "typo",
        "label_mismatch",
    }  # SentinelPage "all" feed
    feed = [r for r in client.get("/api/exceptions").json() if r["type"] in feed_types]
    newest = max(feed, key=lambda r: str(r["facts"].get("posting_date", r["first_signal"])))
    assert newest["id"] == payroll_outlier["id"], "#26: the step-5 example tops the feed"
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


# ----- the demo reset (#26) -----------------------------------------------------------------
def _state(root: Path) -> dict[str, list[list[str]]]:
    """Every file under ``root`` with its sheets' contents (workbooks) or text."""
    import pandas as pd

    out: dict[str, list[list[str]]] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        key = path.relative_to(root).as_posix()
        if path.suffix == ".xlsx":
            sheets = pd.read_excel(path, sheet_name=None, engine="calamine", dtype=str)
            out[key] = [frame.fillna("").values.tolist() for frame in sheets.values()]
        else:
            out[key] = [[path.read_text(encoding="utf-8")]]
    return out


def test_reset_twice_gives_the_same_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from demo_reset import reset

    target = tmp_path / "demo"
    reset(target, yes=True)
    first = _state(target)
    (target / "okane.duckdb").write_text("a database left by a demo run")
    reset(target, yes=True)
    assert _state(target) == first
    assert sorted(first) == ["inbox/Fixed_assets_sample.xlsx",
                             "inbox/Payroll_sample_previous_week.xlsx",
                             "rates.csv", "ready/Payroll_sample.xlsx"]  # fmt: skip
    assert "delete" in capsys.readouterr().out, "the plan is printed before anything is deleted"


def test_reset_changes_nothing_without_yes(tmp_path: Path) -> None:
    from demo_reset import reset

    target = tmp_path / "demo"
    reset(target, yes=True)
    (target / "okane.duckdb").write_text("runs and decisions")
    plan = reset(target)
    assert target / "okane.duckdb" in plan.delete
    assert (target / "okane.duckdb").read_text() == "runs and decisions"


def test_reset_refuses_anything_that_is_not_the_demo(tmp_path: Path) -> None:
    from demo_reset import DATA_DIR, REPO_ROOT, RefusedError, main, reset

    for protected in (REPO_ROOT, DATA_DIR, DATA_DIR / "inbox", REPO_ROOT / "backend"):
        with pytest.raises(RefusedError):
            reset(protected, yes=True)

    target = tmp_path / "demo"
    reset(target, yes=True)
    stray = target / "notes.txt"
    stray.write_text("my notes")
    with pytest.raises(RefusedError):
        reset(target, yes=True)
    assert stray.exists()
    stray.unlink()

    # A workbook that is not a synthetic sample (an invented stand-in for a real extract).
    real = target / "inbox" / "Payroll_extract.xlsx"
    import pandas as pd

    pd.DataFrame({"Payroll": ["not a sample"]}).to_excel(real, sheet_name="Summary", index=False)
    with pytest.raises(RefusedError):
        reset(target, yes=True)
    assert real.exists() and (target / "ready" / "Payroll_sample.xlsx").exists()
    assert main(["--dir", str(target), "--yes"]) == 2, "the command refuses too"


@pytest.mark.parametrize("where", ["tmp", "inbox/elsewhere"])
def test_reset_refuses_a_link_before_deleting_anything(tmp_path: Path, where: str) -> None:
    from demo_reset import RefusedError, reset

    target = tmp_path / "demo"
    reset(target, yes=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("not the demo's")
    link = target / where
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:  # Windows without the right to create links
        pytest.skip("cannot create a symlink here")
    (target / "okane.duckdb").write_text("runs and decisions")
    with pytest.raises(RefusedError, match="is a link"):
        reset(target, yes=True)
    assert (target / "okane.duckdb").read_text() == "runs and decisions", "nothing was deleted"
    assert (target / "inbox" / "Fixed_assets_sample.xlsx").exists()
    assert (outside / "keep.txt").exists() and link.is_symlink()


def test_real_reset_moves_and_never_deletes(tmp_path: Path) -> None:
    from demo_reset import apply, real_plan

    data = tmp_path / "data"
    (data / "inbox").mkdir(parents=True)
    (data / "extracts" / "payroll").mkdir(parents=True)
    (data / "inbox" / "extract.xlsx").write_text("the watched folder's file")
    (data / "extracts" / "payroll" / "extract.xlsx").write_text("Okane's copy")
    (data / "okane.duckdb").write_text("runs and decisions")
    (data / ".env").write_text("OKANE_X=1")
    plan = real_plan(data, stamp="T")
    assert plan.delete == [] and plan.create == []
    apply(plan)
    aside = data / "archive" / "reset-T"
    assert (aside / "okane.duckdb").read_text() == "runs and decisions"
    assert (aside / "extracts" / "payroll" / "extract.xlsx").exists()
    assert (data / "inbox" / "extract.xlsx").exists() and (data / ".env").exists()
    assert not (data / "okane.duckdb").exists()


def test_demo_path_after_a_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset, walk the demo, reset again and walk it again: the demo is repeatable."""
    from demo_reset import reset

    target = tmp_path / "demo"
    for _ in range(2):
        reset(target, yes=True)
        demo_settings(target, monkeypatch)
        with TestClient(create_app(get_settings())) as client:
            walk_demo_path(client, target / "ready" / "Payroll_sample.xlsx")
    get_settings.cache_clear()
