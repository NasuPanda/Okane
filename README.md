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

The first start runs the pipeline on the newest workbooks. With no extract loaded and an empty
`data/inbox/` it uses `data/sample/` and the UI marks the run "practice data". Click **Check now** in the dock at
the bottom to run again.

New here? Press **Tutorial** in the top bar for a guided tour of every page by Mr. Kentaro. It
only shows and explains; it never changes data (A39).

Optional AI comments: `ollama pull qwen2.5:7b-instruct` and keep `ollama serve` running. Without
Ollama everything works; comments are a clearly labelled template.

No backend at all? `cd frontend && VITE_API_MODE=fixtures npm run dev` serves the UI from the
synthetic JSON in `fixtures/`.

Hosted demo: the same practice-data UI runs on Cloudflare (a static Worker; link to follow). It has no
backend; decisions reset on reload. Setup and limits: `deploy/README.md` (ASSUMPTIONS A41).

## Using the real workbooks (locally only)

1. Bring in the Payroll and Fixed assets workbooks: click **Upload extract** in the dock (or
   drop a file anywhere on the page), or copy them into the watched folder `data/inbox/`. Both
   routes go through one intake step (ASSUMPTIONS A38): it checks the sheets and columns,
   refuses a wrong file or one already loaded, keeps a copy in `data/extracts/` and moves the
   extract it replaces to `data/archive/`. Your file is never changed. Everything under
   `data/` and every `*.xlsx` is git-ignored; CI fails if one is ever tracked.
2. Check `data/rates.csv` (units per EUR). The Fixed assets rates in the sample are placeholders
   until the team confirms them (ASSUMPTIONS A11).
3. With `make dev` running, an upload or a new file in the watched folder starts a run; a toast
   shows it starting and finishing. A weekly run fires every Monday at 06:00, also scans the
   folder, and flags an extract as late when none arrived since the previous Monday run.
4. The analysis date is the day the Payroll extract was taken (worked out from the posting
   date and ageing days), so a payment made after the extract never looks missing.
   `OKANE_AS_OF` overrides it.

**A shared folder instead of uploads.** Set `OKANE_INBOX_DIR` in `backend/.env` to a synced
SharePoint, OneDrive or Teams folder the preparer already uses; no code change. Okane only reads
and copies from it. Keep real data out of cloud folders unless the mentor allows it (A38).

Never paste real figures, document numbers or names into issues, PRs, commits or fixtures.

## Demo path (the 3-minute video)

The full script, with the numbers each step must show and how to reset between takes
(`make demo-reset`, then `make demo`), is in [docs/DEMO.md](docs/DEMO.md).

1. **Exposure**: the old report, 145.7M "overdue" on 5,475 lines.
2. Click **Upload extract** (or drop the workbook on the page): the run toast starts and
   finishes, and the Inbox shows where the extract came from and the day it was taken.
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
