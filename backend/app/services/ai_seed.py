"""Export the hosted demo's comment seed (``make ai-seed``; A48).

The hosted demo has no model. It runs only the synthetic sample, with the extract date as the
analysis date, so every run there produces the same findings and the same prompts. This module
runs that same setup here, with a local Ollama, drafts a comment for every finding (and the
spelling checks a run makes), and saves the comment cache to ``fixtures/ai_cache.json``. The
demo image loads it at startup (``OKANE_AI_SEED_PATH``), so the same prompt finds a cached,
checked outcome.

Like ``make fixtures``, it ALWAYS works on freshly generated synthetic workbooks in a temporary
folder, never on data/inbox, and the file carries the ``"synthetic": true`` marker CI checks.
Regenerate it after changing prompts, engines, default rules, rates or the generator.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.ai.client import ollama_available
from app.config import REPO_ROOT, Settings, get_settings

OUT = REPO_ROOT / "fixtures" / "ai_cache.json"


def demo_settings(root: Path, **overrides: Any) -> Settings:
    """The demo image's setup in ``root``: the synthetic sample in its own folder, an empty
    inbox, the sample rates and no analysis date override (the extract date is used)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from generate_sample_data import generate

    generate(root / "sample")
    rates = root / "rates.csv"
    rates.write_text((REPO_ROOT / "backend/tests/data/rates.sample.csv").read_text("utf-8"))
    base: dict[str, Any] = {
        "data_dir": root, "inbox_dir": root / "inbox", "sample_dir": root / "sample",
        "rates_path": rates, "db_path": root / "okane.duckdb", "as_of": None,
        "enable_watcher": False, "enable_scheduler": False, "run_on_startup": False,
        "ai_seed_path": None, "frontend_dist": root / "no-dist",
    }  # fmt: skip
    return Settings(**{**base, **overrides})


def export_seed(out: Path = OUT) -> dict[str, int]:
    """Draft every comment on the synthetic sample and write the cache. Returns counts."""
    from app.main import create_app

    local = get_settings()  # only the Ollama address and model come from the environment
    with tempfile.TemporaryDirectory() as tmp:
        settings = demo_settings(
            Path(tmp), ai_enabled=True, ai_predraft_top=1000, ollama_url=local.ollama_url,
            ollama_model=local.ollama_model, ollama_timeout_s=max(local.ollama_timeout_s, 180.0),
        )  # fmt: skip
        if not ollama_available(settings):
            raise SystemExit(f"Ollama does not answer at {settings.ollama_url}; nothing written")
        with TestClient(create_app(settings)) as client:
            run = client.post("/api/runs", params={"wait": True})
            run.raise_for_status()
            as_of = run.json()["as_of"]
            counts = {"passed": 0, "rejected": 0}
            for exc in client.get("/api/exceptions").json():
                response = client.post(f"/api/exceptions/{exc['id']}/comment")
                response.raise_for_status()
                comment = response.json()
                if comment["source"] == "model":
                    counts["passed"] += 1
                elif comment.get("rejected_draft"):
                    counts["rejected"] += 1  # two drafts rejected: the template, cached
                else:  # the template without a draft: the model did not answer (not cached)
                    raise SystemExit("the model stopped answering; nothing written")
            entries = client.app.state.okane.db.cache_dump()
    _write(out, as_of, entries)
    return {"entries": len(entries), **counts}


def _write(out: Path, as_of: str, entries: dict[str, Any]) -> None:
    wrapped = {"synthetic": True, "generated_at": as_of, "data": entries}
    text = json.dumps(wrapped, indent=1, sort_keys=True) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    counts = export_seed()
    print(f"wrote {OUT.relative_to(REPO_ROOT)}: {counts}")


if __name__ == "__main__":
    main()
