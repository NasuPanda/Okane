# Demo script (the 3-minute video)

The six steps of the brief's demo path (`docs/BRIEF.md`, "The demo path"), as clicks, words and
the numbers the screen must show. Decisions behind it: A2 (step 5 example, analysis date, what
is on screen), A9 (risk score), A25 (inbox), A38 (extract intake).

- **On screen: the synthetic sample** (the default of mentor question 8). Every number below is
  synthetic and amounts are scaled EUR. `backend/tests/test_demo.py` walks these steps through
  the API and checks each number; if it fails, decide whether this script or the product is
  wrong before changing either.
- **Real data** is for rehearsal only. Its figures stay out of Git: fill the blanks marked
  `[real: ____]` in your local copy by hand, and do not commit them.
- **Start state:** last week's Payroll extract and the Fixed assets extract are already loaded
  (analysis date 16 Oct 2026); this week's Payroll extract (taken 23 Oct 2026) waits in the
  demo folder's `ready/` for step 2.
- **Tutorial mode** (the Tutorial button, A39) is not part of the video: close it (X or Esc)
  before a take.

## Before each take: reset the demo

Stop the app first (the reset clears the demo database), then rebuild the start state and run
the app on it. The demo has its own folder, `data/demo/` (git-ignored): `data/inbox`,
`data/okane.duckdb` and `.env` are never touched.

```bash
make demo-reset   # prints what it deletes and creates, then rebuilds data/demo
make demo         # API on :8000 on data/demo (runs last week's extract on start-up) + Vite on :5173
```

In PowerShell, without `make`:

```powershell
backend\.venv\Scripts\python scripts\demo_reset.py --yes
$d = "$PWD\data\demo"
$env:OKANE_DATA_DIR = $d; $env:OKANE_INBOX_DIR = "$d\inbox"; $env:OKANE_DB_PATH = "$d\okane.duckdb"
$env:OKANE_RATES_PATH = "$d\rates.csv"; $env:OKANE_SAMPLE_DIR = "$d\sample"; $env:OKANE_ENABLE_SCHEDULER = "false"
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000   # then, in a second window: cd frontend; npm run dev
```

- Without `--yes` the reset only prints its plan. It refuses a folder holding anything other
  than the demo's own files, a workbook not marked synthetic, the repository or `data/` itself.
- Leave `OKANE_AS_OF` unset: the analysis date is the extract date (A2, A38).
- `--real` (rehearsing on real data): moves `data/okane.duckdb` and Okane's extract store into
  `data/archive/reset-<time>/` (never deletes). It does not move the workbook out of
  `data/inbox` (Okane never changes the watched folder, A38); to show the upload in step 2 on
  real data, take the Payroll workbook out of `data/inbox` yourself first.

## Step 1: the old report (Exposure)

- **Click:** Exposure.
- **Say:** "This is what today's ageing report gives the payroll team every month: everything
  older than a year is 'overdue', most of it already paid."
- **Screen:** the old report calls **72 lines** "overdue", **11,358,855** in total (the Inbox
  card "Old report says overdue" shows it as 11.36M). `[real: ____ lines, ____ M]`

## Step 2: this week's extract arrives (Upload extract)

- **Click:** Upload extract, then choose `Payroll_sample.xlsx` from the demo folder's `ready/`
  (or drop it on the page).
- **Say:** "The preparer uploads this week's payroll extract. Okane checks the file, keeps a
  copy and runs every check. Nothing goes back to SAP or to the file."
- **Screen:** the toast shows the run starting and finishing; the Inbox data-source line says
  the Payroll extract was **taken 23 Oct 2026** and arrived by upload. A new repeated manual
  posting appears with it (14 findings in all, up from 13).

## Step 3: show real exposure (Exposure, then Inbox)

- **Click:** "Show real exposure" on Exposure, then Inbox.
- **Say:** "Once accruals are matched to what paid them, only a few accounts are really open.
  The inbox starts with the findings at or above the materiality limit."
- **Screen:** **3 accounts remain** at 500K (of 6 with overdue lines) `[real: ____]`. The Inbox
  header: "Today's report calls 72 lines overdue. After matching what was paid, only 3 accounts
  are really open, and **6 findings at or above 500K** need a look first." `[real: ____ findings]`
  The tabs: Above 500K **6**, Mistake prompts **3**, Repeated postings **1**, Everything **14**.

## Step 4: the top finding (C192 social security)

- **Click:** the first row of the Inbox.
- **Say:** "The first one is the social security liability in C192. The balance has been off
  the expected level for well over a year, and today's ageing rule cannot see it. Here is a
  payment with the wrong month on it, and a draft note whose figures are all checked."
- **Screen:** first row **C192 279006, the gap** (priority **90**) `[real: ____]`, badge
  "Today's process would miss this", the gap chart. The Mistake prompts tab holds the wrong
  month label on C192 ("Payment labelled 2026-01 settles 2026-02").
- **Comment:** without a local model the note reads "Standard note (no AI was used): ...". With
  Ollama running and the comment contract of PR #61 merged, the drafted note shows its figures
  ticked green (pending #61 and #32).

## Step 5: Sentinel, a posting-day outlier

- **Click:** Sentinel.
- **Say:** "This line was typed by hand and is thousands of times the account's usual size.
  Okane flags it on the day it is posted, weeks before the month-end review would look."
- **Screen:** the Payroll outlier on **C192 279002**, "Amount **4,874x** the account's usual
  size, posted by a person", badge "**Caught 32 days before the close review**".
  `[real: ____ x, caught ____ days before the close review]`
- **Also on this page:** the repeated manual posting card (#31): the same posting typed by hand
  in **6 months** on 2 company codes (C132, C192), 8 lines, labelled a hypothesis.

## Step 6: Rules, lower materiality to 100K

- **Click:** Rules, set materiality to 100,000, type a reason ("Quarter-end review"), save.
- **Say:** "The controller sets the limits, not a model. Lower the limit and more accounts
  come into view; the change is logged with who, when and why."
- **Screen:** Exposure shows **4 accounts** instead of 3 `[real: ____ instead of ____]`; the
  Rules log has one entry for materiality, 500,000 to 100,000, with the reason. The C192 gap
  stays first. On the synthetic data the Inbox's "Above" tab stays at 6 (no synthetic finding
  lies between 100K and 500K). `[real: ____ findings at 100K]`

## Closing line

"Today's report is too loud and blind at the same time. Okane shows the few accounts that are
really open, and the mistakes it can see weeks before the close." The Inbox card "Spotted
earlier by" shows the median lead time (**16 days** on the synthetic data `[real: ____]`).
