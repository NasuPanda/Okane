"""The hosted demo's comment seed (A48): loading, safety and coverage of the committed file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.client import cache_key, load_seed
from app.config import REPO_ROOT, get_settings
from app.database import Database
from app.main import create_app
from app.services.ai_seed import demo_settings

SEED = REPO_ROOT / "fixtures" / "ai_cache.json"


def drafted(exception_id: str, text: str) -> dict[str, object]:
    return {
        "exception_id": exception_id, "comment": text, "source": "model", "verifier": "passed",
        "checked_figures": [], "failed_figures": [],
    }  # fmt: skip


def write_seed(path: Path, data: dict[str, object], synthetic: bool = True) -> Path:
    wrapped = {"synthetic": synthetic, "generated_at": "2026-10-23", "data": data}
    path.write_text(json.dumps(wrapped))
    return path


def test_seed_never_overwrites_a_cached_outcome(tmp_path: Path) -> None:
    db = Database(tmp_path / "okane.duckdb")
    db.cache_put("k1", drafted("a", "Drafted here."))
    seed = write_seed(
        tmp_path / "seed.json", {"k1": drafted("a", "From the seed."), "k2": drafted("b", "New.")}
    )
    assert load_seed(seed, db) == 1
    assert db.cache_get("k1")["comment"] == "Drafted here."
    assert db.cache_get("k2")["comment"] == "New."
    db.close()


def test_seed_without_the_synthetic_marker_is_refused(tmp_path: Path) -> None:
    db = Database(tmp_path / "okane.duckdb")
    seed = write_seed(tmp_path / "seed.json", {"k1": drafted("a", "x" * 20)}, synthetic=False)
    with pytest.raises(ValueError, match="not marked synthetic"):
        load_seed(seed, db)
    assert db.cache_dump() == {}
    db.close()


def test_seeded_comment_is_served_without_a_model(
    app_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(create_app(get_settings())) as client:
        assert client.post("/api/runs", params={"wait": True}).json()["status"] == "finished"
        state = client.app.state.okane
        exc = client.get("/api/exceptions").json()[0]
        run = state.db.latest_run()
        assert run is not None
        record = state.db.get_exception(run.run_id, exc["id"])
        assert record is not None
        key = cache_key(record, state.settings)
    seed = write_seed(app_env / "seed.json", {key: drafted(exc["id"], "Drafted earlier.")})

    monkeypatch.setenv("OKANE_AI_SEED_PATH", str(seed))
    monkeypatch.setenv("OKANE_AI_ENABLED", "true")
    monkeypatch.setenv("OKANE_OLLAMA_URL", "http://127.0.0.1:9")  # nothing answers there
    get_settings.cache_clear()
    with TestClient(create_app(get_settings())) as client:
        comment = client.post(f"/api/exceptions/{exc['id']}/comment").json()
    assert comment["source"] == "model"
    assert comment["cached"] is True
    assert comment["comment"] == "Drafted earlier."


def test_committed_seed_covers_every_sample_finding(tmp_path: Path) -> None:
    """Fails when prompts, engines, rules or the generator changed: run ``make ai-seed``."""
    wrapped = json.loads(SEED.read_text("utf-8"))
    assert wrapped["synthetic"] is True
    settings = demo_settings(tmp_path, ai_enabled=False)
    with TestClient(create_app(settings)) as client:
        run = client.post("/api/runs", params={"wait": True}).json()
        assert run["as_of"] == wrapped["generated_at"]
        state = client.app.state.okane
        missing = [
            exc["id"]
            for exc in client.get("/api/exceptions").json()
            if cache_key(state.db.get_exception(run["run_id"], exc["id"]), settings)
            not in wrapped["data"]
        ]
    assert not missing, f"fixtures/ai_cache.json is stale for {len(missing)} findings"
