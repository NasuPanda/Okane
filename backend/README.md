# Okane backend

FastAPI, pandas (calamine engine), DuckDB, rapidfuzz, watchdog, APScheduler, httpx (Ollama).
Setup and the overall picture are in the root [README](../README.md) and
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

```bash
make setup                                   # from the repo root
cd backend
.venv/Scripts/python -m pytest               # Windows (bin/ on macOS/Linux)
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

- Settings: `OKANE_*` environment variables, documented in [.env.example](.env.example).
- `app/engines/` are pure functions; `app/services/pipeline.py` orchestrates a run.
- Tests: `test_ingest.py`, `test_engines.py` (engines and the AI layer), `test_api.py` (every
  endpoint, events, jobs, fixtures), `test_golden.py` (the brief's Expected values on real data,
  skipped without `data/inbox/`, plus synthetic assertions that always run).
- Synthetic workbooks are generated per test session by `tests/conftest.py`; spreadsheets are
  never committed.
