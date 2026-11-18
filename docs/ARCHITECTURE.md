# Architecture

One Python backend computes everything; the React frontend only displays and collects
decisions. Nothing is written back to an ERP or a workbook.

```
data/inbox/*.xlsx ──watchdog──┐            Monday 06:00 ──APScheduler──┐
                              ▼                                        ▼
                     services/pipeline.py  (one run at a time, SSE run_started/run_finished)
                              │
   ingest.py  ── calamine ──► common model, EUR ──► DuckDB snapshot (keyed by file hashes)
                              │
   engines (pure functions of lines + Rules):
     pairs ► pulse ► sentinel ► typos ► miner ► leadtime ► exposure/score
                              │
   ai/client.py ── masked facts ──► Ollama ──► ai/verifier.py (every figure vs facts) ──► cache
                              │
   api/*  (FastAPI) ──► frontend (React) ── decisions, rule changes ──► DuckDB audit logs
```

## Data model

- `Line` (`schemas.py`): one open line item in the common model (brief section 6 mapping).
  Identifiers are strings; a document is (CoCd, Year, DocumentNo) because numbers repeat
  across fiscal years. Evidence is written `DocumentNo/Year`.
- `ExceptionRecord`: the one shape every engine emits (brief section 7). `facts` holds every
  number the UI or the model may show; `evidence` the documents; `first_signal`,
  `today_detection` and `lead_days` the lead time; `score_breakdown` the points per weight.
- `Rules`: every threshold, the payment profiles and the Sentinel scope. Stored in DuckDB;
  every change is logged per field with who, when, old, new and why.

## Storage (DuckDB, `data/okane.duckdb`)

`snapshots`/`lines` (one per workbook set), `runs`/`exceptions`/`run_artifacts` (one result set
per run; pulse timelines are artifacts), `decisions` + `decision_log` (keyed by stable exception
id, so decisions survive later runs), `rules` + `rule_changes`, `ai_cache`.

## Engines

| Module | Rule (brief section) | Output |
|---|---|---|
| `pairs.py` | Exact offsetting pairs (8) | pair id per line |
| `pulse.py` | Payment profiles, matching, gap timeline, five alerts (8) | records + timelines |
| `sentinel.py` | S1 outlier (8); S2, S3 (A4, A5, decided in #10) | records |
| `typos.py` | Spelling and period-label prompts (assumption) | records |
| `miner.py` | Recurring manual corrections, CC06 (assumption) | records |
| `leadtime.py` | Today's detection date per type (assumption) | fills lead time |
| `exposure.py` | Payroll netting (8); risk score (weights from 7, scaling an assumption) | groups, scores |

Engines never read files, the clock or the database; the pipeline passes the analysis date in.

## AI layer

The model receives the masked title, type and `facts` (no document numbers, user ids or raw
lines) and must answer `{"comment": "..."}`. `verifier.py` extracts every number and date and
accepts it only if it equals a fact at the precision shown. A failing draft is retried once and
shown with the offending figures struck through. Without Ollama a labelled template is used.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/runs/latest`, `GET /api/runs`, `POST /api/runs[?wait=true]` | Run status and start |
| `GET /api/events` | Server-sent events `run_started`, `run_finished` |
| `GET /api/exceptions?type&workgroup&entity&min_exposure&status` | Inbox, by score |
| `GET /api/exceptions/{id}` | Record, evidence lines, gap series, decision history |
| `PATCH /api/exceptions/{id}` | Status, class, reason (required), edited comment |
| `POST /api/exceptions/{id}/comment[?refresh=true]` | AI draft with verifier result |
| `GET /api/exposure/payroll?materiality=` | Old-rule totals and per-account netting |
| `GET /api/pulse/accounts`, `GET /api/pulse/{erp}/{entity}/{account}/timeline` | Gap chart |
| `GET/PUT /api/rules`, `GET /api/rules/log` | Rules and change log (PUT re-runs) |
| `GET /api/kpis` | Median days earlier, blind spots, counts |

The OpenAPI schema is the contract: `make types` regenerates the frontend types from it.

## Frontend

`frontend/src/api/client.ts` exposes one interface with two sources selected by
`VITE_API_MODE` (`live` or `fixtures`). Pages: Inbox, Exposure, Sentinel, Rules; the exception
drawer opens from anywhere via `?finding=<id>`. Design tokens live in `src/index.css`.
