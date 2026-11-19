# Okane: developer build brief

Last revised: 18 Nov 2026. Scope: Payroll and Fixed assets workbooks only. The Intercompany working group (its workbook, the P10 sheet and the WHT Triangle) was removed on 17 Nov 2026.

## Contents

1. What we're building
2. Who it is for
3. Scope for the qualifiers
4. Workflow from now to the finals
5. Stack, repo and pipeline
6. Data reference
7. Data model and API contract
8. Engine specs
9. Not yet specified
10. Changes in the Intercompany revision, and open items

---

## 1. What we're building

Every Monday, Okane reads the open line items the robot already extracts and shows a controller only what is really unpaid or wrong, instead of everything that is merely old.

**The problem.** Nokia Finance must prove each month that every balance sheet account is correct. The main alarm today is a blunt 365-day ageing rule: it is too loud (payroll shows 145.7M "overdue" on 5,475 lines, mostly matched accruals and payments) and blind at the same time (it cannot see a real gap, a mislabelled payment or a posting error until the month-end review). The hackathon challenge is to detect anomalies, prioritize risks and resolve issues in-month, before closing.

**Direction.** Make the finance team's job easier and faster without giving up control. Okane never guesses risk by itself: it works with parameters the employee sets (materiality, tolerance, grace days, risk weights).

**Main feature: real exposure.** Match each amount owed to whatever settled it, such as payroll accruals to the payments that paid them. What is left is the real exposure, with an expected-by date from the account's own payment rhythm. Every other check (Sentinel, Miner, mistake prompts, lead time) feeds the same exception list.

**Project scope, in order of importance**

1. Payroll Liability Pulse: real exposure instead of a 365-day ageing rule.
2. Detection lead time: how many days earlier Okane flags a finding than today's process.

**Baselines (must be included)**

- Convert every amount to EUR.
- Run at least every week instead of end-of-month.
- Fix input errors: for example a wrong period label produces a prompt, "you may have made a mistake".
- Recurring-Correction Miner: find the root cause behind repeated manual fixes.
- Posting-Day Error Sentinel: catch known error types on the day they are posted.

**Architecture.** A pipeline driven by spreadsheets, connected and updating automatically: a new workbook in a watched folder, or the weekly schedule, starts a run.

**Ground rules**

- Code computes every number. The language model only reads messy text and writes comments, and a verifier checks every figure it writes.
- The controller sets the rules: materiality, tolerance, grace days, risk weights. No model sets a risk score.
- Read-only: nothing is ever written to the ERP or to the source workbooks. The data stays on our laptops and in a private repo, as the data notice requires.

### The demo path the build must support (the 3-minute video)

1. The old report: payroll shows 145.7M "overdue" on 5,475 lines.
2. The preparer uploads this week's Payroll extract in Okane (the same file could instead land in the shared watched folder); a toast shows the run starting and finishing. See A38.
3. "Show real exposure": matched lines fold away and 4 exceptions remain at 500K materiality. This is the wow moment.
4. Open the top exception, C192 social security: the gap chart (more than 1M off since May 2025, 1.84M today), a mistake prompt on a wrong period label, and an AI comment with its numbers ticked green.
5. Sentinel feed: an outlier flagged on posting day, with the badge "N days before the close review". **To confirm:** the earlier example (a 9.86 billion WHT line) was Intercompany and is out of scope. See open item 1.
6. Rules panel: lower materiality to 100K; the list grows from 4 to 7 and the change is logged.

The line the demo must earn: **today's report is too loud and blind at the same time.**

## 2. Who it is for

**Users**

- **Preparer (accountant):** investigates open items, matches pairs, writes explanations. Needs a short ranked list, evidence one click away, and a draft comment to edit.
- **Approver and Reviewer / Controller:** checks policy was followed and certifies or rejects. Needs to see why something was flagged, which rule or parameter caused it, and an audit trail of every decision and every parameter change.
- Each exception can be classified by the human as **List component** (valid long-term item), **Timing item** (valid, will clear in a known future period) or **Required Adjustment Item** (wrong, needs a correcting SAP entry). Okane may suggest a class; the person decides.
- Users are accountants, not data scientists: plain language, no unexplained scores.

**The jury (qualifier scoring)**

| Criterion       | Weight | What it rewards                                                                           |
| --------------- | ------ | ----------------------------------------------------------------------------------------- |
| Business value  | 35%    | Clear finance problem, measurable benefit, earlier risk detection and in-month resolution |
| Innovation      | 20%    | Originality beyond simple automation                                                      |
| Use of AI       | 20%    | Appropriate, well-explained use of AI                                                     |
| Feasibility     | 15%    | Realistic for an enterprise finance environment                                           |
| User experience | 5%     | Intuitive for accountants and controllers                                                 |
| Presentation    | 5%     | Clarity, storytelling, handling of jury questions                                         |

The pitch must also cover governance: explainability, auditability, security.

**Deliverables.** Pitch deck (max 12 slides plus appendix), demo video (max 3 minutes), one-page executive summary. Qualifiers 25 to 26 Nov; finals 4 Dec at Nokia Skypark Budapest (10-minute pitch including demo, 5-minute Q&A).

## 3. Scope for the qualifiers

Build only what the demo path shows. Every engine emits the same Exception record (section 7), so a new check appears in the inbox without new UI; dedicated pages are extras.

**Must have (P0)**

- Ingest the two in-scope workbooks (Payroll and Fixed assets) into one data model, with EUR conversion from a rate table
- Payroll netting view for every payroll account, with a live materiality slider
- Pulse for C192 social security (P20 279006) and C242 accrued payroll (BPP 34900015): batch matching, gap timeline, five alert types
- Sentinel checks S1 to S3, typo prompts and the CC06 Miner card, all as Exception records
- Lead-time badge on every exception
- Exception inbox, detail drawer, and accept or dismiss with a reason
- Rules panel (materiality, tolerance, grace days) with a change log
- AI comment plus verifier on the C192 exception; cached outputs for the other demo items
- Folder watcher and the run-status toast

**Should have (P1), from Friday if P0 works**

- Sentinel S5 (reversal mismatch)
- A dedicated Sentinel feed page and a KPI header with median days earlier

**Out of scope (deck or finals only)**

- Pulse for every payroll account, which needs a payment profile per account
- The Intercompany working group (the WHT Triangle and every check that depends on the Intercompany workbook), removed on 17 Nov
- A full lead-time replay engine; badges are enough for now
- Roles, single sign-on, second-approver workflow, Excel write-back, anomaly model, debt index

## 4. Workflow from now to the finals

Back end (BE, Python) and front end (FE, React) run in parallel. FE builds on JSON fixtures exported from the engines until the API goes live on Friday, and the whole demo path must run end to end on live data by Friday evening. Friday's end-to-end run is the gate: anything not working by then moves to P1 or to the finals.

**Tue 17 Nov, kick-off**

- [ ] Both: create a private repo, put the two in-scope workbooks in a git-ignored data folder, read this brief
- [ ] Both: agree the Exception record and the endpoints in section 7

**Wed 18 Nov**

- [ ] BE: load every sheet into DuckDB with the common columns; EUR conversion; exact-pair matching
- [ ] BE: payroll netting view and the first golden tests
- [ ] BE: export JSON fixtures (exceptions, exposure, C192 timeline) for FE
- [ ] FE: Vite, React, TypeScript, Tailwind and shadcn/ui; app shell with the left navigation
- [ ] FE: inbox table on the fixtures

**Thu 19 Nov**

- [ ] BE: Pulse batch matching for C192 and C242, payment lags, gap timeline and the five alerts
- [ ] BE: FastAPI endpoints and the generated TypeScript types
- [ ] FE: Exposure page with the materiality slider, detail drawer, gap chart

**Fri 20 Nov**

- [ ] BE: Sentinel S1 to S3, typo prompts, CC06 Miner
- [ ] FE: rules panel with change log; switch from fixtures to the live API
- [ ] Both: checkpoint, the demo path runs end to end on live data

**Sat 21 Nov**

- [ ] BE: Ollama, prompt contract, verifier, masking and cache; lead-time badges
- [ ] FE: AI comment panel with verified numbers highlighted; badges; accept and dismiss flows
- [ ] Both, if on track: P1 items (Sentinel S5)

**Sun 22 Nov**

- [ ] BE: folder watcher and run events over server-sent events; every golden test green
- [ ] FE: run toast, skeleton loaders, polish pass
- [ ] Both: record a full backup take of the demo video

**Mon 23 Nov, freeze**

- [ ] Both: code freeze, final video, screenshots for the deck
- [ ] Pitch: 12-slide deck and one-page summary

**Tue 24 Nov**

- [ ] Buffer and submission; confirm the exact deadline with the mentor

**After submission**

- [ ] Qualifiers on 25 to 26 Nov
- [ ] Finals prep, 27 Nov to 3 Dec: Pulse for every payroll account, live-demo hardening, Q&A rehearsal
- [ ] Finals on 4 Dec

## 5. Stack, repo and pipeline

One Python back end does all the computing; the React front end only displays and collects decisions.

| Part             | Choice                                                                                                                              |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Front end        | React, TypeScript, Vite, React Router, TanStack Query                                                                               |
| UI               | shadcn/ui (Radix with Tailwind CSS), Lucide icons, Inter font; TanStack Table for lists; Recharts through shadcn's chart components |
| API              | FastAPI with pydantic and uvicorn; FE types generated from /openapi.json with openapi-typescript                                    |
| Live updates     | Server-sent events (sse-starlette)                                                                                                  |
| Data and engines | Python 3.12, pandas, DuckDB (one file, one snapshot per run)                                                                        |
| Text             | Regex for keys, rapidfuzz for typos                                                                                                 |
| Model            | Ollama with a 7 to 9B open-weight instruct model; JSON output validated by pydantic                                                 |
| Jobs             | watchdog for the folder watcher, APScheduler for the Monday 06:00 run                                                               |
| Tests            | pytest, with the expected values in section 8                                                                                       |

Parse the workbooks once and work from DuckDB afterwards: openpyxl is slow on these files, and pandas' calamine engine is faster.

```
okane/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI application
│   │   ├── config.py          # Paths, settings, environment
│   │   ├── schemas.py         # Pydantic data contracts
│   │   ├── database.py        # DuckDB connection and queries
│   │   ├── ingest.py          # Excel ingestion, EUR conversion
│   │   ├── api/               # runs, exceptions, exposure, pulse, rules, kpis
│   │   ├── engines/           # pairs, pulse, sentinel, typos, miner, leadtime, exposure
│   │   ├── ai/                # client, prompts, verifier
│   │   ├── services/          # pipeline, fixtures
│   │   └── jobs.py            # Watchdog, APScheduler
│   └── tests/                 # test_golden, test_ingest, test_engines, test_api
├── frontend/                  # React application
├── fixtures/                  # Generated JSON fixtures
├── data/                      # Git-ignored: inbox/, rates.csv, okane.duckdb
├── .gitignore
└── Makefile                   # make dev: uvicorn :8000, vite :5173, ollama :11434
```

**Pipeline, per run**

1. A new workbook is uploaded in Okane or lands in the watched folder (`OKANE_INBOX_DIR`, default data/inbox), or the Monday job fires. One intake step checks it and copies it into Okane's store before the run (A38).
2. ingest.py reads every sheet, maps the columns to the common model, converts to EUR, and writes a snapshot to DuckDB with the file hash.
3. The engines run in order: pairs, pulse, sentinel, typos, miner, lead time, exposure and score.
4. Each engine writes Exception records into the snapshot.
5. The AI layer drafts and verifies comments for new exceptions and caches them.
6. The API serves the snapshot, and a server-sent event tells the UI the run has finished.

## 6. Data reference

Two workbooks, four data sheets, 24,165 rows in total, one row per open line item. Skip each workbook's Summary tab, and drop rows with an empty CoCd.

| Workbook     | Sheet (ERP) | Rows  | Ageing date | Contents                                                       |
| ------------ | ----------- | ----- | ----------- | -------------------------------------------------------------- |
| Payroll      | P20         | 8,298 | 23 Oct 2026 | 6 entities, 19 payroll accounts; carries EUR amounts and rates |
| Payroll      | BPP         | 5,669 | 23 Oct 2026 | 6 entities, 36 accounts; carries EUR amounts and rates         |
| Fixed assets | BPP         | 5,976 | 2 Oct 2026  | One account, EUR local currency                                |
| Fixed assets | P20         | 4,222 | 2 Oct 2026  | One account, JPY and PLN local currencies                      |

**Column mapping to the common model**

| Common field             | Payroll sheets                            | Fixed-asset sheets          |
| ------------------------ | ----------------------------------------- | --------------------------- |
| amount_dc                | Ammount in DC (sic)                       | Amount in DC                |
| amount_lc                | Amount in LC                              | Amount in Local Currency    |
| currency_dc, currency_lc | Curr., LCurr                              | Curr., Lcurr                |
| amount_eur               | Amount in EUR, EURCurrencyExchangeRate    | Computed from rates.csv     |
| doc_type, item           | DocumentType, ItemNo in Doc               | Type, Item                  |
| posting_date, doc_date   | Pstng Date, Doc Date                      | Pstng Date, Doc. Date       |
| partner                  | Tr.Prt (BPP only)                         | Tr.Prt                      |
| age_days                 | Current Ageing (Days)                     | Ageing(No of days)          |
| overdue_abs, allowed_age | Overdue Amount ABS, Ageing Allowed (Days) | Not present                 |
| clearable, reversal      | Not present                               | Reversal (Fixed assets BPP) |

CoCd, Account, Description, DocumentNo, Year, Period, User Name, Text, Doc.Header Text, Reference and Assignment keep their names.

**Conventions**

- Negative amounts are credits, positive are debits. Amounts are scaled by a constant factor, so label figures "scaled" on screen.
- Keep document numbers as strings: leading zeros matter.
- Partners: P20 writes "N" plus the company code (NC### is C###); BPP uses its own TP-### codes.
- Users: BOT* prefixes are automated postings; USER*### are people.
- Payroll EUR rates, one per currency: HUF 366.2, XOF 655.957, AUD 1.6297, CZK 24.44, GBP 0.85463, IDR 20,315.3, KRW 1,539.1. For the Fixed assets sheets, rates.csv also needs rates for JPY, USD, PLN and CNY.
- Text holds name placeholders such as NAME122: mask them before any model call.
- Nokia exempts pension-type payroll accounts from the ageing rule ("no overdue"): use the file's Ageing Allowed (Days) column, never assume 365.

## 7. Data model and API contract

Every engine returns Exception records in one shape, and the pydantic models below are the source of truth for the generated TypeScript types. The id is a hash of type, ERP, entity, account and key documents, so a status set by a person survives the next run.

```python
class ExceptionRecord(BaseModel):
    id: str
    run_id: str
    type: Literal["pulse_gap", "pulse_missing_payment", "pulse_spike", "pulse_missing_batch",
                  "label_mismatch", "sentinel_outlier",
                  "sentinel_two_currencies", "sentinel_currency_code", "sentinel_reversal",
                  "typo", "miner_cluster"]
    workgroup: Literal["Payroll", "Fixed assets"]
    erp: Literal["P20", "BPP"]
    entity: str                      # CoCd, e.g. C192
    account: str
    account_name: str
    title: str                       # written by code, e.g. "Liability 1.84M above expected"
    exposure_eur: float              # signed
    facts: dict[str, float | str]    # every number the UI or the model may show
    evidence: list[str]              # document numbers behind the exception
    first_signal: date               # when Okane can first flag it
    today_detection: date | None     # when today's process would; None means never
    lead_days: int | None
    expected_by: date | None
    suggested_class: Literal["List component", "Timing item", "Required Adjustment Item"] | None
    score: float
    score_breakdown: dict[str, float]
    ai_comment: str | None
    verifier: Literal["passed", "failed", "not_run"]
    status: Literal["new", "explained", "dismissed", "escalated"]
    decision_reason: str | None

class Rules(BaseModel):
    materiality_eur: float = 500_000
    tolerance_pct: float = 0.01            # a batch matches within max(1% of batch, tolerance_eur)
    tolerance_eur: float = 1_000
    grace_days: int = 15
    outlier_multiple: float = 1_000
    weights: dict[str, int] = {"exposure": 40, "days_past_expected": 20,
                               "penalty_account": 20, "error_type": 10, "repeats": 10}
```

| Endpoint                                         | Returns                                                                           | Used by            |
| ------------------------------------------------ | --------------------------------------------------------------------------------- | ------------------ |
| GET /api/runs/latest                             | Run id, source file, start and finish times, counts                               | Header, toast      |
| POST /api/runs                                   | Starts a run on the newest workbook                                               | Demo button        |
| GET /api/events                                  | Server-sent events: run_started, run_finished                                     | Toast              |
| GET /api/exceptions                              | Exceptions sorted by score; filters for type, workgroup, entity, minimum exposure | Inbox              |
| GET /api/exceptions/{id}                         | One exception with its evidence lines and chart series                            | Drawer             |
| PATCH /api/exceptions/{id}                       | Updates status, decision reason or edited comment                                 | Accept and dismiss |
| POST /api/exceptions/{id}/comment                | AI draft with the verifier result, cached                                         | Comment panel      |
| GET /api/exposure/payroll?materiality=           | Old-rule totals and the per-account netting                                       | Exposure page      |
| GET /api/pulse/{erp}/{entity}/{account}/timeline | Month-end balance, expected balance and gap                                       | Gap chart          |
| GET and PUT /api/rules                           | The rules; each PUT appends to the change log                                     | Rules panel        |
| GET /api/rules/log                               | Who, when, old value, new value, reason                                           | Rules panel        |
| GET /api/kpis                                    | Median days earlier and exceptions by type                                        | KPI header         |

## 8. Engine specs

Each engine is a pure function from the snapshot and the Rules to Exception records. Every "Expected" value below is an assertion in `tests/test_golden.py` (skipped when the real workbooks are not present).

### EUR conversion (ingest.py)

- amount_eur = amount_lc / rate(currency_lc), with rates.csv holding units per EUR on the run date. Payroll sheets keep their own EUR column, checked against the same rate.
- Expected: the payroll rates listed in section 6.

### Exact pairs (pairs.py)

- Key: ERP, CoCd, Account, currency and |amount_dc| rounded to cents. Rank positive and negative lines by posting date within the key, then pair equal ranks.
- Expected: payroll 476 paired lines.

### Payroll netting (engines/exposure.py)

- Take payroll lines with Overdue Amount ABS above 0. Group by ERP, CoCd and Account: count, sum of Overdue Amount ABS, sum of signed EUR. An exception is a group with |net| at or above materiality.
- Expected: 5,475 lines; 145.67M absolute; net -5.69M; 4 groups at 500K and 7 at 100K. The top four nets: C242 34900001 -6,497,211; C192 279006 +1,087,864; C192 179003 +679,839; C192 279014 -649,069. C242 34900015: 15 lines, 24.94M absolute, net -2,493.
- Expected: 8,193 of 8,298 P20 payroll lines have Ageing Allowed (Days) = 365.

### Pulse (pulse.py)

Each account has a payment profile, which is part of the Rules:

| Account           | Batch                                                                                                                     | Payment unit                                                                | Window                    | Tolerance |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------- | --------- |
| C192 P20 279006   | Credit lines with Text Payroll + YYYYMM, summed per period (periods of at least 50K)                                      | A payment document over 1,000 (its debit lines summed), at most 2 per batch | Period end -5 to +70 days | 2%        |
| C242 BPP 34900015 | Credit lines of the monthly GX document from BOT_UPLOAD_002 (Text "Auszahl. Rente_MM.YYYY", sometimes misspelt "Auzahl.") | Bank (TX) lines, at most 5 per batch                                        | Accrual date to +14 days  | 1%        |

- Matching: for each batch in date order, try combinations of unused payment units inside the window and keep the one with the smallest difference within tolerance, then the shortest lag. Record the lag in days.
- Gap timeline: month-end balance = running sum of open items by posting month; expected balance = minus that month's batch (0 if none); gap = balance - expected.
- Period parser for payment texts: "Payroll202609", "January2023", "Jan'2025", "Dec' 2025", "03/2026", "P05 2021".

**Alerts and expected values**

- pulse_gap when the latest gap is at or above materiality. Expected for C192: balance +1,324,638; September 2026 batch -513,823.36 (68 lines, posted 29 Sep 2026); gap 1,838,462; gap above 500K at every month-end from May 2025 to September 2026, lowest 1,058,373 in July 2025.
- pulse_missing_payment when a batch is still unmatched after expected_by = period end + 90th-percentile lag + grace days. Expected for C192: 21 batches matched, lag median 30 and 90th percentile 37, so the September 2026 batch is expected by 21 Nov 2026.
- pulse_spike when a batch exceeds 3x the trailing 12-month median. Expected: August 2026, 2,531,445.87 against a median of 620,878 (4.1x).
- pulse_missing_batch when a month has no batch. Expected: C192, August 2025.
- label_mismatch when a payment's text period differs from the batch it settles. Expected: the 28 Mar 2024 payment labelled January 2024 settles February (654,991.96 against 653,106.90, -0.29%); the 27 Sep 2024 payment labelled Sep'2024 settles August (-0.30%).
- Expected for C242 (no alert): July 2025, 4,091,302.21 owed and 4,090,894.37 paid by 3 lines in 12 days; August, 4 lines in 9 days; September, 3 lines in 12 days, exact.

### Sentinel (sentinel.py)

- S1 outlier: |amount_lc| at or above outlier_multiple x the median |amount_lc| of the same ERP, entity and account, skipping lines with amount_dc = 0 (FX valuations).
- Expected top hit: **to be re-set** (the earlier value was an Intercompany document). On Payroll and Fixed assets only, the rule returns 185 hits at 1,000x the median: 173 posted by bots (mostly routine monthly payroll batches) and 12 by people. The top person-posted hit is Payroll BPP, C242, account 48900002, document 7910008634 (2019, USER_120).
- S1 as written fires on routine payroll batches. Restrict it to person-posted lines or exempt BOT_UPLOAD batches, exposed as a Rules option (open item 2).

## 9. Not yet specified

The source of this brief stopped inside the Sentinel section. The team's original, longer brief specifies the items below; it is private (`docs/reference/`) and is never copied into the repo.

Decided in #3 (18 Nov 2026): the original's rules, minus Intercompany, are the default recommendation for each item below. The team still decides each item in its issue, and the agreed rule is written in our own words in `docs/ASSUMPTIONS.md` (the "Agreed rule" column). Until an item is decided, the code follows that assumption, marked `# ASSUMPTION:` in code.

| Item                              | What we know                                                                                                | Decided in               | Agreed rule |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------ | ----------- |
| Sentinel S2, S3                   | Listed as P0; types sentinel_two_currencies and sentinel_currency_code exist in the Exception record        | #10 (decided); build #11 | A4, A5      |
| Sentinel S5                       | P1; type sentinel_reversal (a reversal document that does not mirror its original)                          | #33                      | A26         |
| Typo prompts                      | Spelling or period-label errors produce a "you may have made a mistake" prompt; rapidfuzz for fuzzy matches | #12; build #13           | A6          |
| Recurring-Correction Miner (CC06) | Finds the root cause behind repeated manual fixes; one card in the demo                                     | #14 (decided); build #15 | A7          |
| Lead time                         | Per exception: first signal date, today's detection date, lead days; badge "N days before the close review" | #16 (decided); build #17 | A8          |
| Risk score                        | Weights in Rules (exposure 40, days past expected 20, penalty account 20, error type 10, repeats 10)        | #18; build #19           | A9          |
| AI layer                          | Ollama, JSON output validated by pydantic, masking, cache, verifier                                         | #28; build #29           | A10, A28    |
| Screens                           | Inbox, Exposure, Sentinel, Rules; detail drawer with gap chart, AI comment, lead-time badge                 | Built to UI reference    | A16         |
| Extract intake, analysis date     | How the weekly extract reaches Okane, the analysis date, when an extract is late, archive of past weeks     | #23 (decided); built #24 | A38         |
| Mentor questions                  | Nine questions drafted; none depends on Intercompany or WHT                                                  | #2                       | A36         |

## 10. Changes in the Intercompany revision, and open items

**What was removed (17 Nov 2026)**

- WHT Triangle everywhere: engine spec, triangle.py, /api/triangle, the Triangle page and board, the June 2025 episode, exception types wht_unmatched and wht_rate, Sentinel S4, and the rules wht_rates and counterpart_grace_days (the latter on the assumption that only the Triangle used it; please confirm).
- Data: the three Intercompany sheets (P20 5,164, BPP 5,643 and P10 3,513 rows), their column mappings, the SKK and DEM rates, the workgroup value "Intercompany" and the ERP value "P10".
- Exact pairs: the P10 key change and the expected 428 paired lines. The Payroll expectation (476) is unchanged.
- Demo path: from 7 steps to 6.
- Tasks: Fri BE "Triangle engine"; Sat P1 "Triangle board" and "Sentinel S4"; finals prep "Triangle for more partners".
- Added for confirmation: rates for the Fixed assets currencies (JPY, USD, PLN, CNY) in rates.csv, and the S1 figures above.

**Open items**

1. Demo step 5 needs a non-Intercompany Sentinel example. Candidates: Payroll BPP C242 48900002 document 7910008634 (2019, USER_120, about 57,769x the account median), or Fixed assets P20 C218 119001 document 7750001797 (2012, USER_013). The "N days before the close review" value must be recomputed for whichever is picked.
2. Sentinel S1 as specified fires on routine payroll batches (165 of the 174 hits in Payroll P20 are bot postings). Decide whether to restrict S1 to person-posted lines (12 hits) or exempt BOT_UPLOAD batches, then set the golden test.
3. The unspecified items in section 9, including checking any CC06 cluster or mentor question for Intercompany or WHT dependencies.
4. With Intercompany gone, the Fixed assets sheets are not used by any must-have item. Decide whether they feed Sentinel and the Miner, or move to later.
