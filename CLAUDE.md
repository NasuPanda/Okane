# Okane: rules for Claude Code sessions

Okane is a **read-only reconciliation copilot** for Nokia Finance (Nokia and Corvinus Finance
Hackathon, Budapest, Nov 2026). Requirements live in `docs/BRIEF.md`; open interpretations and
undecided items live in `docs/ASSUMPTIONS.md`. If this file and the brief disagree, the brief wins.

## WHAT we build

- Today's main alarm is a 365-day ageing rule on open line items. It is **too loud** (payroll
  shows 145.7M scaled "overdue" on 5,475 lines, mostly matched accruals and payments) and
  **blind** (it cannot see a real gap, a mislabelled payment or a posting error before month end).
- Okane matches what is owed to what settled it and shows only the **real exposure**, with an
  "expected by" date from the account's own payment rhythm.
- Must have: Payroll Liability Pulse (real exposure) and Detection lead time.
- Baselines: EUR conversion, at least weekly runs, "you may have made a mistake" prompts,
  Recurring-Correction Miner, Posting-Day Error Sentinel.
- Spreadsheet-driven pipeline: a workbook dropped in `data/inbox/` or the Monday 06:00 job
  starts a run.
- Data: **Payroll** and **Fixed assets** workbooks only, each with P20 and BPP sheets.
- **Intercompany is removed.** No WHT Triangle, no P10, no Intercompany workbook, no stubs.

## WHO it is for

- **Preparer (accountant):** a short ranked list, evidence one click away, a draft comment.
- **Approver / Reviewer / Controller:** why it was flagged, which rule or parameter caused it,
  an audit trail of every decision and parameter change.
- Humans classify each exception: **List component**, **Timing item** or **Required
  Adjustment Item**. Okane may suggest; the person decides.
- Plain accountant language in every UI string: open item, accrual, payment, exposure,
  expected by. No model or ML jargon, no unexplained scores.

## Non-negotiable rules

1. Code computes every number. The language model only reads messy text and writes comments;
   `ai/verifier.py` checks every figure against `ExceptionRecord.facts`. A model never sets a
   score, amount, date, class or risk level.
2. Read-only: nothing is ever written to an ERP or back to a source workbook.
3. Real financial data never enters Git. Never print, log or commit row-level data
   (aggregates in tests are fine; so are the row-level values the brief quotes, in the brief,
   `docs/ASSUMPTIONS.md` and real golden tests only, see A35). Committed fixtures come from the
   synthetic generator only and use invented user ids.
4. Amounts are scaled in the source; label figures "scaled" in the UI.
5. Document numbers are strings (leading zeros matter). Document numbers repeat across fiscal
   years, so a document is identified by (CoCd, Year, DocumentNo).
6. Mask name placeholders such as `NAME122` before any model call.
7. Every threshold (materiality, tolerance, grace days, outlier multiple, weights, payment
   profiles, Sentinel scope) comes from `Rules`, never a literal inside an engine.
8. Every finding carries evidence (document numbers), the rule that fired and its lead time.
9. Engines are pure functions (snapshot + Rules -> records). No I/O inside `engines/`.
10. Exception ids are stable hashes of type, ERP, entity, account and key documents, so a
    person's decision survives the next run.
11. Unspecified behaviour: implement the simplest version, mark it `# ASSUMPTION:` in code and
    add it to `docs/ASSUMPTIONS.md`. Never invent silently.

## Git ignore rules (decided; only append, never weaken)

- `.gitignore` starts with the agreed block: `data/**` (except `.gitkeep`), `*.xlsx`, `*.xls`,
  `*.xlsm`, `*.feather`, `*.joblib`, `docs/reference`, `.env*` (except `.env.example`),
  editor files, `docs/NOTE.md`.
- `data/` holds only `.gitkeep` files in Git. Real workbooks go in `data/inbox/` locally.
- Spreadsheets are never committed. Synthetic workbooks are generated at test time
  (`backend/tests/conftest.py`) or by `make generate-sample-data` into `data/sample/`.
- No `.feather` / `.joblib` caches; use JSON or DuckDB under `data/`.
- CI fails if `git ls-files` shows a spreadsheet, DuckDB file, cache, `.env`, anything in
  `data/` other than `.gitkeep`, `docs/reference`, or a fixture not marked synthetic.

## Private material

- `docs/reference/` is private (kick-off deck with mentor contact details, terminology guide,
  UI reference, personal notes). Read for context only. **Never copy its contents into
  committed files, prompts, fixtures or comments; never write mentor names or contact details.**
- `docs/NOTE.md` is a personal scratch file: do not create, read or write it.

## Working conventions

- Backend: `cd backend && .venv/Scripts/python -m pytest` (Windows) or `make test`.
  Lint: `ruff check . && ruff format --check .`.
- Frontend: `cd frontend && npm run typecheck && npm run build`. API types: `make types`.
- Real-data golden tests skip automatically when `data/inbox/` has no workbook; synthetic tests
  always run. Keep both green.
- Scope is the brief's P0 list. Out of scope: Pulse for every payroll account, full lead-time
  replay, roles/SSO, second approver, Excel write-back, anomaly models, debt index, Intercompany.
