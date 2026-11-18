# Okane

A read-only reconciliation copilot for payroll and fixed-asset open items (Nokia and Corvinus
Finance Hackathon, Budapest, November 2026).

Today's month-end report flags every open item older than 365 days. That is **too loud**
(payroll shows 145.7M scaled "overdue" on 5,475 lines, mostly accruals already matched by
payments) and **blind** (it cannot see a real gap, a mislabelled payment or a posting error
until the close). Okane matches each accrual to what settled it, shows the real exposure with an
"expected by" date, catches posting errors on the day they are posted, and tells you how many
days earlier than today's process each finding appears. The controller sets every threshold;
code computes every number; a local language model only words comments, and a verifier checks
every figure it writes.

- Requirements: [docs/BRIEF.md](docs/BRIEF.md)
- Open decisions and interpretations: [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md)
- How it fits together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- How we work: [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
- Rules for Claude Code sessions: [CLAUDE.md](CLAUDE.md)

## Quick start (synthetic data, about ten minutes)

Prerequisites: Python 3.12+, Node 22+, GNU make (on Windows: Git Bash with `mingw32-make` or
`make` from MSYS2), and optionally [Ollama](https://ollama.com) for AI comments.

```bash
git clone <repo-url> okane && cd okane
make setup                 # backend venv + deps, data/rates.csv from the sample, npm install
make generate-sample-data  # synthetic workbooks into data/sample/ (git-ignored)
make dev                   # API on :8000, UI on http://localhost:5173
```

The first start runs the pipeline on the newest workbooks. With an empty `data/inbox/` it uses
`data/sample/` and the UI marks the run "synthetic sample". Click **Run now** in the dock at the
bottom to run again.

Optional AI comments: `ollama pull qwen2.5:7b-instruct` and keep `ollama serve` running. Without
Ollama everything works; comments are a clearly labelled template.

No backend at all? `cd frontend && VITE_API_MODE=fixtures npm run dev` serves the UI from the
synthetic JSON in `fixtures/`.

## Using the real workbooks (locally only)

1. Copy the Payroll and Fixed assets workbooks into `data/inbox/`. Everything under `data/` and
   every `*.xlsx` is git-ignored; CI fails if one is ever tracked.
2. Check `data/rates.csv` (units per EUR). The Fixed assets rates in the sample are placeholders
   until the team confirms them (ASSUMPTIONS A11).
3. With `make dev` running, the folder watcher starts a run as soon as a workbook lands; a
   toast shows it starting and finishing. A weekly run fires every Monday at 06:00.

Never paste real figures, document numbers or names into issues, PRs, commits or fixtures.

## Demo path (the 3-minute video)

1. **Exposure**: the old report, 145.7M "overdue" on 5,475 lines.
2. Drop a new extract into `data/inbox/`: the run toast starts and finishes.
3. **Show real exposure**: matched accounts fold away; 4 remain at 500K materiality.
4. Open the top finding, **C192 social security**: gap chart, a "you may have made a mistake"
   prompt on a wrong period label, and the comment with its figures ticked green.
5. **Sentinel**: an outlier flagged on posting day, "N days before the close review".
6. **Rules**: lower materiality to 100K with a reason; 4 becomes 7 and the change is logged.

## Commands

| Command | What it does |
|---|---|
| `make setup` | Create `backend/.venv`, install backend and dev deps, copy sample rates, `npm install` |
| `make generate-sample-data` | Write synthetic workbooks to `data/sample/` |
| `make dev` | Uvicorn on :8000 with reload, Vite on :5173; warns if Ollama is not on :11434 |
| `make test` | `pytest` (real-data golden tests skip when `data/inbox/` is empty) |
| `make lint` | `ruff check`, `ruff format --check`, frontend `tsc` |
| `make fixtures` | Regenerate `fixtures/*.json` from synthetic data only |
| `make types` | Regenerate `frontend/src/api/schema.d.ts` from the OpenAPI schema |
| `make build` / `make serve` | Build the UI; serve API and UI together on :8000 |

Docker: `docker build -t okane . && docker run -p 8000:8000 -v "$PWD/data:/data" okane`. The
image never contains data; `/data` is a volume.

## Repository layout

```
backend/        FastAPI app: ingest, engines, AI layer, API, jobs; tests (pytest)
frontend/       React + TypeScript UI (Vite, Tailwind, shadcn/ui, TanStack, Recharts)
fixtures/       Synthetic JSON the UI can run on (generated, committed, marked synthetic)
scripts/        generate_sample_data.py: synthetic workbooks with planted cases
data/           Git-ignored: inbox/, sample/, rates.csv, okane.duckdb (only .gitkeep is tracked)
docs/           BRIEF, ASSUMPTIONS, ARCHITECTURE, CONTRIBUTING; reference/ is private, git-ignored
```

Files outside the agreed tree, and why they exist: `CLAUDE.md` (project rules for AI coding
sessions), `docs/` (brief, assumptions, architecture, contributing), `.github/workflows/ci.yml`
(lint, tests, build, forbidden-files check), `Dockerfile` and `.dockerignore` (single-port
deploy without data), `backend/tests/conftest.py` and `backend/tests/data/rates.sample.csv`
(synthetic test data and the sample rate table), `scripts/` (the synthetic-data generator),
`.vscode/settings.json` (shared formatter and interpreter settings).

## Out of scope for this prototype

Pulse for every payroll account, a full lead-time replay engine, roles and single sign-on, a
second-approver workflow, Excel write-back, anomaly models, a debt index, Sentinel S5, and
anything Intercompany (removed on 17 Nov 2026). Okane never writes to an ERP or a workbook.
