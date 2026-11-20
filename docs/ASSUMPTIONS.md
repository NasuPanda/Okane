# Assumptions and open decisions

Every behaviour the brief does not specify, every place where the brief and the data disagree,
and every TODO lives here. Code that implements one of these carries an `# ASSUMPTION:` comment.
Real-data figures below are aggregates (counts and totals), plus the few row-level values the
brief itself quotes (A35).

Owner lines read **Owner: team** until someone takes the item; replace with a name when you do.
Status: **Decide** (the team must choose), **Confirm** (check our reading), **Info** (recorded
so nobody re-investigates).

## Summary: what the team must decide

| # | Item | Status | Default we shipped |
|---|------|--------|--------------------|
| A1 | Sentinel S1 scope (brief open item 2) | Decide | Decided (#9): `people_only` |
| A2 | Demo step 5 Sentinel example (brief open item 1) | Decide | C242 48900002 document 7910008634 |
| A3 | Do Fixed assets feed Sentinel and the Miner? (brief open item 4) | Info | Confirmed (#7): Sentinel, typos, Miner; not Pulse or netting |
| A4 | Sentinel S2 rule | Decide | Decided (#10): the same amount in two currencies on one day, at least 1,000 |
| A5 | Sentinel S3 rule | Decide | Decided (#10): not an ISO code, or replaced by the euro |
| A6 | Typo prompts: fields, thresholds, dictionary | Decide | Decided (#12), built (#13): one letter from a word 20x as common, Text and header, allow-list |
| A7 | Recurring-Correction Miner and the CC06 definition | Decide | Decided (#14): original fingerprint, score = entities x months, Inbox at 12+; card "Repeated manual posting" |
| A8 | Lead time: "today's detection date" per type | Decide | Decided (#16): close review on the 5th working day; weekly view from the Monday run; pending mentor Q2 |
| A9 | Risk score scaling | Decide | Linear 0..1 per component, caps in Rules |
| A10 | AI prompt contract and model | Decide | Decided (#28, #45), built (#29): comment and typo check; the model names figures and code fills them in; retry with feedback; template if rejected twice; qwen2.5 7B, local |
| A11 | Fixed assets EUR rates (JPY, USD, PLN, CNY) | Confirm | Placeholder values in the sample rates |
| A12 | Pulse match preference differs by profile | Info | Confirmed (#4): per-profile switch kept |
| A13 | 27 Sep 2024 label mismatch settles July, not August | Info | Confirmed (#4): July kept |
| A14 | Missing-batch look-back | Info | Confirmed (#4): 24 months |
| A15 | 21 missing-payment alerts on real data | Decide | Decided (#20): expected by within the last 12 months; 7 on real data |
| A16 | Screens: Inbox, Exposure, Sentinel, Rules | Confirm | Built to the UI reference |
| A34 | Landing version-1 on main; required CI checks | Decide | Merged by pull request; checks not enforceable on the current plan |
| A35 | Where real identifiers may live in Git | Decide | Decided (#6): brief-quoted values only, in the brief, this file and real golden tests |
| A36 | Mentor questions (#2) | Decide | Drafted, not yet sent; each question's default is in the Mentor questions section |
| A37 | Original rules as the default; where agreed rules live | Decide | Decided (#3): original rules minus Intercompany are the default; agreed rules go here, BRIEF.md section 9 indexes them |
| A38 | How the weekly extract reaches Okane | Decide | Decided (#23), built (#24): upload page plus watched folder through one intake step; analysis date = extract date; late at the Monday run; archive |

## Data and ingestion

**A11. Fixed assets EUR rates.** *Confirm.* The brief lists the Payroll rates but only says
rates.csv "also needs rates for JPY, USD, PLN and CNY". `backend/tests/data/rates.sample.csv`
holds placeholder values for these four (JPY 162.5, USD 1.09, PLN 4.29, CNY 7.85, dated
2 Oct 2026). Confirm the real rates and the date before using Fixed assets figures. On the
real file the Fixed assets local currencies are only EUR (BPP), JPY and PLN (P20); USD and CNY
appear only as document currencies, so today only the JPY and PLN rates affect EUR amounts.
Owner: team.

**A17. Payroll keeps its own EUR amount.** *Info.* Per the brief, Payroll sheets keep
`Amount in EUR`; the rate is checked against rates.csv (all match). On the real file, 18 lines
differ from `amount_lc / rate` by at most 0.06 (source rounding). Ingest warns only above 0.10.
Owner: team.

**A18. Document numbers repeat across fiscal years.** *Info.* In the real data the same
DocumentNo appears in several years (for example payment documents in C192). A document is
therefore identified by (CoCd, Year, DocumentNo) and evidence is written `DocumentNo/Year`.
Without this, the C192 matching finds 7 instead of 21 batches. Owner: team.

**A19. Fixed assets workbook.** *Info (resolved 18 Nov 2026, #7).* The real workbook is now
available and every mapped column (`Amount in DC`, `Amount in Local Currency`, `Lcurr`, `Type`,
`Item`, `Doc. Date`, `Ageing(No of days)`, `Reversal`) is present. It ingests with no warnings:
BPP 5,976 and P20 4,222 lines, so the four sheets total 24,165 as the brief says. Each sheet
holds one account; local currency is EUR on BPP and JPY / PLN on P20. `Reversal` exists on BPP
only. Extra source columns (Clrng doc., Entry Date, PK, Profit Ctr, Supplier, Vendor name and
others) are ignored. Real golden tests cover row counts, column mapping and EUR conversion.
Owner: team.

**A3. Fixed assets scope.** *Info (confirmed 18 Nov 2026, #7; brief open item 4).* Fixed
assets lines go through Sentinel S1 to S3, typo prompts and the Miner. They are excluded from
payroll netting, Pulse and lead time. On the real Payroll plus Fixed assets workbooks S1 returns
exactly the brief's 185 hits / 12 person-posted (Payroll alone 183 / 11; Fixed assets P20 adds
2 / 1), and netting and Pulse give the same figures as on Payroll alone. Owner: team.

**A20. Inbox and sample data.** *Info (built in #24, A38).* A run reads the current Payroll and
Fixed assets extract from Okane's store (`data/extracts/`), filled by the intake step from an
upload or the watched folder (`OKANE_INBOX_DIR`, default `data/inbox/`). If the store has none,
it reads `data/sample/` (synthetic) and marks the run `synthetic`. Owner: team.

**A21. Analysis date.** *Info (built in #24, A38).* A run uses `OKANE_AS_OF` if set, otherwise
the day the Payroll extract was taken, otherwise today. Golden tests pin 18 Nov 2026 so "the
September 2026 batch is expected by 21 Nov 2026" is not yet late; one golden test measures the
real figures at the extract date (A38). Owner: team.

**A38. How the weekly extract reaches Okane.** *Decided (#23, 19 Nov 2026; mentor question 9
had no answer by its due date, so its default applies, which is also the team's choice).* Built
in #24.
- Cadence: one Payroll and one Fixed assets extract a week. A new extract starts its own run;
  the Monday 06:00 job is the backstop when none came. Okane first sees a posting in the next
  weekly extract, not on its posting day, so the weekly lead-time view (A8, #16) is the honest
  figure.
- One intake step, several routes. Every route hands the file to the same intake step, which
  checks it by its sheets and columns (not its file name), skips it when its hash is already
  known, copies it into Okane's store (`data/extracts/`, current file per kind), moves the file
  it replaces to `data/archive/`, and starts a run with the route as its trigger. Runs read only
  from the store, never from the source location.
  - (a) Upload page in Okane (`POST /api/uploads`, trigger `upload`): the demo route. A wrong
    file or a duplicate gets a plain message and no run.
  - (b) Watched folder: `OKANE_INBOX_DIR` may point at a synced SharePoint, OneDrive or Teams
    folder the preparer already uses (trigger `watcher`). Same intake code as (a), so building
    (a) keeps (b) working; one test feeds a file through each route. Okane only reads and
    copies from this folder and never moves or deletes anything in it. Synced folders can miss
    file events, so the Monday job also scans the folder (trigger `schedule`).
  - (c) Connector polling a SharePoint library or a cloud bucket: not built; shown in the deck
    as the production route (a third source that downloads the file and calls intake, with no
    change to the pipeline or engines). It needs credentials and a sign-in.
  - Real data does not go into a cloud folder during the hackathon unless the mentor allows it;
    (b) is documented and tested with synthetic workbooks.
  - Read-only toward every source (CLAUDE.md rules 2 and 3); the store and the archive stay
    under `data/`, which Git ignores.
- Analysis date: the day the Payroll extract was taken (Pulse and the score use only Payroll),
  worked out from the data as posting date + ageing days. On the real files this gives
  23 Oct 2026 for Payroll and 2 Oct 2026 for Fixed assets (the ageing dates in brief section 6).
  Each workbook's own extract date is shown on the data-source line. ASSUMPTION: when a sheet's
  lines give different dates, the most common one is used and the run warns; when none can be
  worked out, the run date is used. `OKANE_AS_OF` still overrides.
  - Why: with the run date, a payment made after the extract looks missing until the next
    extract arrives.
  - Re-measured in #24 (real Payroll, aggregates, as of 23 Oct 2026 instead of 18 Nov, with
    the 12-month missing-payment limit from #20, which counts back from the analysis date): 6
    missing-payment alerts instead of 7 (C242's October 2026 batch is expected by 13 Nov,
    after the extract, so it is not yet due), so 45 findings and 36 with a date; the C192 gap
    still ranks first at 89.4; 4 exposure groups stay above 500K; the lead-time median stays
    11 days (daily 16.5, was 17); blind spots stay 9.
    Golden test: `test_real_figures_at_the_extract_date`. Other golden tests keep pinning
    18 Nov. On-screen counts no longer change with the calendar day (helps #25).
  - On the real Payroll BPP sheet, 395 lines (nearly all pension-type accounts) give a date one
    day later: those accounts count ageing days one day differently. ASSUMPTION (#24): a line
    within one day of the most common date agrees, so the real files give no warning.
- Late: an extract is late when no new file (new hash) of that kind has arrived since the
  previous Monday 06:00 run. That Monday run still goes ahead on last week's file, and the
  Inbox says "No new extract since <date>".
- Archive: replaced extracts are kept in `data/archive/`, so a past week can be re-run; a run
  still reads the newest file per kind.
- Built in #24, with these choices (each marked `# ASSUMPTION` in code):
  - `app/intake.py` is the intake step; `POST /api/uploads?filename=` takes the workbook as
    the raw request body (no multipart dependency); 422 for a wrong file, 409 for a duplicate,
    413 above `OKANE_UPLOAD_MAX_MB` (50). The store keeps one folder per kind; the `extracts`
    table records every arrival (route, who, when, rows) as an audit trail.
  - A workbook must carry both its P20 and its BPP sheet.
  - The newest arrival wins, even if its extract date is earlier; the Inbox shows the extract
    date, so a person sees it. A folder scan only loads the newest file per kind, never an
    older one over a newer one.
  - A trigger that arrives during a run (an upload, a file event) is remembered and runs
    once when the current run ends.
  - A refused file in the watched folder becomes a run warning once, and is not re-read
    until it changes.
  - `OKANE_SCHEDULE_DAY_OF_WEEK` as a list or range ("mon-fri") counts its first day for the
    late rule.
  - The Inbox shows a data-source line per workbook: file name, extract date, how and by whom
    it arrived, lines read, when the next extract is due, and a warning when it is late.
- Rejected: folder only, with no upload page (the demo would not show a pipeline anyone could
  use); the run date as the analysis date (false missing payments between extracts); "late
  after 7 days" with old files overwritten (no re-run of a past week).
Owner: team.

## Pulse

**A12. Match preference per profile.** *Info (confirmed 18 Nov 2026, #4).* The brief: "keep the
one with the smallest difference within tolerance, then the shortest lag". Taken literally, C192
gives a 90th percentile lag of 59 days (brief: 37). Preferring the fewest payment units first
reproduces every C192 value (21 matched, median 30, p90 37, Sep 2026 expected by 21 Nov 2026).
But C242 August 2025 must be settled by 4 lines (brief), which needs the literal rule. So each
payment profile carries `prefer_fewest_units` (C192 true, C242 false). Tested alternative: one
rule for both profiles, shortest lag first and then smallest difference, also reproduces every
Expected value, but on 4 C192 batches it picks a two-payment combination over a single payment
and raises the C192 label-mismatch prompts from 5 to 8. The per-profile switch stays because it
raises fewer false prompts. Owner: team.

**A22. Tolerance floor.** *Info.* A batch matches within `max(profile tolerance % x batch,
Rules.tolerance_eur)`, following the `Rules` comment in the brief. With 500K+ batches the
percentage always dominates. Owner: team.

**A13. The 27 Sep 2024 payment.** *Info (confirmed 18 Nov 2026, #4).* The brief says the
payment labelled Sep'2024 "settles August (-0.30%)". Greedy date-order matching (the rule that
yields the brief's own lag statistics) assigns it to the July 2024 batch (+0.09%), because July
is matched first and the payment is inside July's window. Measured against the August batch the
payment is exactly -0.30%, so the brief compared it with August, a batch date-order matching
leaves unmatched; no matching order tried for A12 gives it to August. July is kept, and a label
mismatch fires either way. On real data the rule yields 6 label mismatches (5 on C192, 1 on
C242); the brief cites two examples. Owner: team.

**A14. Missing batch look-back.** *Info (confirmed 18 Nov 2026, #4).* "When a month has no
batch" would flag 2023 months in C192, because fully cleared batches drop out of an open-items
extract. Months are checked only within `Rules.missing_batch_lookback_months` (24) of the latest
batch. This yields exactly August 2025 for C192, as expected; C242 also shows October 2025. A
36-month look-back gives the same result; with no look-back C192 adds four months in 2023.
Owner: team.

**A15. Missing payments on real data.** *Decided (19 Nov 2026, #20).* Without a limit the rule
yields 21 alerts (C192: 18 across 2023 to 2026; C242: 3). The C192 gap stayed below materiality
until May 2025, so the older C192 batches were most likely settled by payments the profile does
not recognise (quarterly CFE and GARP payments or another ERP), not left unpaid.
- Rule: a missing payment is raised only when the batch's expected-by date falls within
  `Rules.missing_payment_lookback_months` (12) before the run date. Older unmatched batches
  are not raised on their own; they stay in the gap alert's evidence and its count of
  accruals without a payment. Controllers can change the number on the Rules page.
- Real data (as of 18 Nov 2026): 7 alerts, C192 April to July 2026 (4) and C242 (3), down from
  21. An 18-month limit gives 12, 24 months gives 13.
- Rejected: widening the C192 profile (a window to +100 or +130 days with 3 or 4 payments still
  leaves 18; a 5% tolerance leaves 17, so the extract holds no further payments to match);
  keeping only batches inside the current gap run (it drops C242's October 2026 batch, the
  freshest signal, because C242 has no gap alert); keeping all 21 (mostly false alarms, and
  the inbox gets noisier, #21).
- Synthetic sample: June 2026 on C192 is also left unpaid, so the demo keeps one missing
  payment (May and June 2025 are past the limit and only drive the gap).
- Mentor question 4: a "yes, some are paid quarterly" answer needs no change.
- Since #24 the 12 months count back from the analysis date, which is now the Payroll extract
  date (A38): 6 alerts as of 23 Oct 2026, as C242's October 2026 batch is not yet due then.
Owner: team.

**A23. Gap alert.** *Info.* Fires when the latest |gap| is at or above materiality. Its first
signal is the month-end where the current unbroken run above materiality began (31 May 2025 for
C192). Its evidence is the unmatched batches. Owner: team.

**A24. Spike.** *Info.* Needs at least 3 earlier batches in the trailing window; otherwise no
median is computed. Real data: August 2026 for C192 (4.1x of 620,878), as expected, and
January 2026 for C242 (3.5x). Owner: team.

**A25. Netting groups are not Exception records.** *Info.* The brief's demo says "4 exceptions
remain at 500K" on the Exposure page, but the Exception `type` list has no netting type. Netting
groups are returned by `/api/exposure/payroll` (4 at 500K, 7 at 100K on real data) and each
links to the highest-scored exception on its account. Owner: team.

## Sentinel, typos, Miner

**A1. Sentinel S1 scope.** *Decided (#9, brief open item 2).* `Rules.sentinel_s1_scope`
defaults to `people_only`: S1 flags person-posted lines only. On Payroll plus Fixed assets
this gives the brief's 12 hits (11 Payroll, 1 Fixed assets); the unrestricted rule gives 185,
173 of them bot postings (Payroll P20 alone: 174, 165 by bots). `exempt_bot_upload` (44
hits, 42 of them Payroll) and `all` stay selectable on the Rules page. Golden test:
`test_real_sentinel_s1_default_scope`. Owner: team.

**A2. Demo step 5 example.** *Decide (brief open item 1).* With `people_only` the top hit is
Payroll BPP C242 48900002 document 7910008634 (2019, USER_120, about 57,769x the account
median). With the lead-time rule (A8, decided in #16) it is caught 16 days before that
month's close review (weekly view; 21 days counted from the posting date).
The alternative candidate (Fixed assets P20 C218 119001 document 7750001797) needs the Fixed
assets workbook. Owner: team.

**A4. S2 two currencies.** *Decided (#10).* S2 flags the same amount posted in different
document currencies on the same ERP, entity, account and posting date, when the amount in
document currency is at least `Rules.sentinel_s2_min_amount` (1,000; on the Rules page). "The
same amount" is compared in whole units: a currency without decimals cannot repeat the cents of
one with them, and compared to the cent the real data has no hit. One record per group: its
evidence is every document in the group, its exposure the largest EUR value in the group, and
its id comes from the posting date and the amount, so a decision survives when one of the lines
is cleared. Real data: exactly one hit, Fixed assets P20 C218 119001, three lines in three
documents (EUR and JPY); Payroll has none; any minimum from 0.01 to 1,000 gives the same hit.
This replaces the placeholder rule (two document currencies in one document, or two local
currencies in one company code), which found nothing and which SAP does not normally produce.
Golden test: `test_real_sentinel_s2`. Built in #48 (#11). Synthetic plants: Payroll C132 (EUR and
RWF) and Fixed assets C219 (EUR and PLN), asserted in `test_synthetic_sentinel_typos_miner`.
Owner: team.

**A5. S3 currency code.** *Decided (#10).* S3 flags a document currency that is not an ISO 4217
code ("not a valid currency code"), or one the euro had already replaced on the posting date
("replaced by the euro"). The replaced codes are the 21 national currencies of euro-area
members, each from the first day it could no longer be used: 1 Jan 2002 for the 1999 and 2001
joiners, the changeover day for later ones (BGN from 1 Jan 2026). A replaced code posted before
that day is not flagged. The earlier branch for amounts copied without conversion (document and
local currency differ, amounts equal) is dropped: it is not part of the agreed rule and found
nothing on real data. Real data: one hit, a DEM line on Fixed assets P20 C238; Payroll has
none. Golden test: `test_real_sentinel_s3`. Built in #48 (#11). Synthetic plants: Payroll C141
(GHC) and Fixed assets C218 (FRF). Owner: team.

**A26. S5 reversal mismatch.** *Info.* P1; not built. The type exists in the schema.
Owner: team.

**A6. Typo prompts.** *Decided (#12), built (#13).* (1) Spelling: words of at least
`Rules.typo_min_word_length` (5) letters are counted over Text and Doc.Header Text of every
line in the run (Payroll and Fixed assets together, case ignored, NAME placeholders removed). A word seen at most `Rules.typo_max_rare_count` (3) times
that is `typo_max_edits` (1) letter away (Levenshtein: one letter added, removed or replaced)
from a word seen at least `typo_common_ratio` (20) times as often is flagged. Plurals and
shortened forms (one word starts with the other) are skipped. Known abbreviations and foreign
words go on `typo_allow_list` (default alloc, avance, recov, reverse), which controllers edit
on the Rules page; the model check of each candidate is #30. Two swapped letters count as two
edits, so "Langrf" or "recalss" are not flagged (chosen to keep the agreed rule; OSA distance
would add 3 such words on real data). (2) Period label (unchanged; demo step 4): a line whose
text names a different period than most lines of its document. ASSUMPTION (#13): only
documents with at least `Rules.period_label_min_lines` (3) lines that name a period are
checked, so "most lines" means something. All typo thresholds are on the Rules page and bounded
(edits 1 to 3, rare count at least 1, ratio above 0, word length at least 2, lines at least 2);
each prompt's facts show the values that applied. Real data: 11 prompts, all
Payroll; Fixed assets has none. Spelling: Adjustmnt, retirment, SwissLlife, URSAAF (6 before
the allow-list, which removes Alloc and recov); period labels: 7. The previous per-account rule
(similarity 80, rarity 2.5x, Text only) gave 15 spelling prompts, several false ("Advance" for
"avance", "Auszahlung" for "Barzahlung"); it found "Auzahl", which the new rule does not, as
"Auszahl" is not 20 times as common. Golden test: `test_real_typo_prompts`. Owner: team.

**A7. Recurring-Correction Miner.** *Decided (#14, 19 Nov 2026; the original rule per A37,
pending mentor question 5).* The CC06 cluster was in the removed Intercompany workbook, so
the name "CC06" is dropped.
- Lines: person-posted (USER_###) lines that have a header text; bot postings and lines
  without a header text are ignored.
- Fingerprint: ERP, user, account, document type and the header text, lower-cased, with name
  placeholders replaced, "corr" spelled out as "correction" and digits masked. The entity is
  not part of the fingerprint, so one pattern can span entities. Such a pattern is one record,
  placed on the lowest entity code in it (never on the one with most lines), so its id stays
  the same when a later extract shifts lines between entities (CLAUDE.md rule 10).
- Score: distinct entities x distinct posting months. A cluster reaches the Inbox when its
  score is at least `Rules.miner_min_score` (12) and it appears in at least
  `Rules.miner_min_repeats` (3) distinct months.
- Demo card: the top cluster by score (ties: more months, then more lines), chosen by rule,
  not by a fixed identifier.
- Card wording: "Repeated manual posting: N months", labelled a hypothesis ("This may be a
  correction made by hand every month. Check whether the automated posting or mapping can
  do it."). On real Payroll none of the top clusters' header texts contain a correction word,
  so the card does not call them corrections.
- Real Payroll (aggregates): 165 fingerprints, 33 in 3+ months; in the Inbox (both
  thresholds) 6 at score 12+ (16 at 6+, 4 at 20+). Each top cluster sits in one entity, so
  its score equals its months.
- Real Fixed assets (aggregates, measured in the review of PR #50): 8 patterns at score 12+,
  top score 159.
- Rejected: the earlier rule (entity, account, document type and line text, 3+ months; 42
  Payroll and about 38 Fixed assets clusters, no score) and the original without the user.
Owner: team.

## Lead time and score

**A8. Lead time.** *Decided (#16, 19 Nov 2026; the original rule per A37; the close review day
is pending mentor question 2).*
- Today's detection date, per type:
  - `sentinel_*`, `typo`, `label_mismatch`, `pulse_spike`: the close review on the
    `Rules.close_review_working_day` (5th) working day after the end of the posting month.
    Working days are Monday to Friday, minus the dates in `Rules.close_review_holidays`
    (empty by default; the close team's public holidays can be added once the mentor answers).
  - `pulse_missing_payment`: accrual date + the account's Ageing Allowed (Days), the day the
    ageing rule would first show it (not "posting + 365"); exempt (pension-type) accounts:
    never.
  - `pulse_gap`, `pulse_missing_batch`, `miner_cluster`: never (today's process has no check
    that sees them). The badge says "Today's process would miss this".
- First signal (set by each engine): the posting date for Sentinel and typo findings; the day
  after the expected-by date for a missing payment (a payment can still arrive on its
  expected-by day; the original uses the expected-by date itself, one day earlier).
- Weekly view (`Rules.lead_time_view` = `weekly`): Okane runs weekly, so lead days count from
  the run on or after the first signal (`Rules.weekly_run_weekday`, 0 = Monday, matching the
  Monday 06:00 job) to today's detection date. The badge, the record's `lead_days` and the KPI
  "median days earlier" use this figure; the daily figure (from the first signal itself) is
  kept in the facts and shown in the badge's tooltip. `daily` switches back.
- Badge: "Caught N days before the close review" or "Caught N days before the 365-day ageing
  rule" (the account's own allowed age); "Seen N days after ..." when negative.
- Real Payroll (aggregates, as of 18 Nov 2026, with the typo rule A6 from #12 and the
  missing-payment limit A15 from #20): 37 findings with a date, 9 blind spots; median 11 days
  earlier (weekly, 5th working day), against 17 daily. Before #20 cut missing payments from 21
  to 7 (each had about 300 or more days of lead time against the 365-day rule): 51 findings,
  median 25 (29 daily). Before #12 cut the typo prompts from 22 to 11: 62 findings, median 17.5
  (21 daily); under the earlier lead-time rule (month end + 5 calendar days, daily) it was 19.
- Rejected: month end + 5 calendar days (it can fall on a weekend); a daily-only badge
  (overstates what a Monday run delivers by up to 6 days).
Owner: team.

**A9. Risk score.** *Decide.* Weights come from Rules (40/20/20/10/10). Each component is scaled
to 0..1: exposure = |exposure| / (5 x materiality), capped; days past expected = days / 90,
capped (a gap counts from its first month above materiality); penalty account = 1 if the
account is in `Rules.penalty_accounts` (default C192 279006, social security); error type =
`Rules.error_type_severity`; repeats = (same type on the same account - 1) / 5, capped (a Miner
cluster counts its months, a gap its months above materiality). With these, the C192 gap ranks
first on real data (89.4), as the demo needs. Owner: team.

**A27. Suggested class.** *Info (confirmed 18 Nov 2026, #5).* Code (never the model) suggests:
gap, outliers, S2, S3 = Required Adjustment Item; missing payment = Timing item if at most 30
days late, otherwise Required Adjustment Item; missing batch, label mismatch = Timing item;
spike, typo, Miner = none. The person always decides the class. Checked against the engines:
the code matches this list. Follow-up #51: the 30-day cut-off is a literal in `pulse.py` and
moves into `Rules` (no behaviour change at the default). Owner: team.

## AI layer

**A10. Prompt contract.** *Decided (#28 and #45, 19 Nov 2026; built in #29).*
- Tasks: the comment draft (#29) and the typo check (#30). The Miner card (#31) uses the same
  client. Key extraction is dropped (it was for the Intercompany keys, which are removed).
- Local only: Ollama, default `qwen2.5:7b-instruct` (any 7 to 9B instruct model works; set
  `OKANE_OLLAMA_MODEL`), temperature 0, 60-second timeout, JSON output passed to Ollama as a
  JSON schema and validated with pydantic (`{"comment": "..."}`, 10 to 1,200 characters).
- What the model sees: a sentence about the finding type written by code, each number and date
  fact as a named figure already formatted by code (`gap_eur`: "1,838,462 EUR", "the gap: month-end
  balance minus the expected balance"), the remaining text facts masked, the entity and the
  check to suggest. It never sees the title (it carries rounded amounts the model re-expanded
  wrongly, #45), document numbers, user ids or raw lines. The Miner score is not shown either,
  as the comment may not give a score.
- Figures by name: the model writes `{gap_eur}` instead of a number, and code fills in the exact
  value, so code writes every figure in the comment. A unit the model repeats next to a name
  ("{multiple} times", "EUR {gap_eur}") is dropped, and `{{name}}` counts as `{name}`. A number
  the model types itself is still checked by the verifier (A28).
- Wording rules: at most 60 words, two or three sentences; a cause only as "a possible cause"
  (naming a cause to check, "check the cause of the gap", is fine); no deadline, due date,
  "by the end of" or "within N days"; no class, risk level or score. Code checks these as well
  (`verifier.wording_issues`).
- Retry with feedback: a rejected draft goes back to the model once, as its own earlier reply,
  followed by the reasons and the figure names it may use. (At temperature 0 a plain retry
  returned the same text, #45.)
- Rejected twice: the comment is the labelled template (A29), and the last draft is kept with
  its reasons behind "Show the assistant's draft". The reasons shown to the person are in plain
  words (no figure names in braces; those go to the model only). A draft with an unconfirmed
  figure is never the note the preparer sees.
- Cache: every model outcome (a passed draft, or the template after two rejections) is cached by
  task, model, exception id and a hash of the prompt version, system prompt, output schema and
  prompt. Changing the model or any prompt text therefore drafts again; an outage is not cached.
  `PROMPT_VERSION` is `v3` (the checks changed in the #61 review).
- Logs and errors never carry the model's text, which can quote line texts or amounts (rule 3):
  a failed call logs only the kind of error.
- The top 3 findings (`ai_predraft_top`) are pre-drafted during a run when Ollama is reachable.

Owner: team.

**A28. Verifier rule.** *Info (updated in #29).* The verifier runs on the comment after the
figures are filled in. Every number and date in it must equal a fact at the precision shown
(1,838,461.53 may appear as 1,838,462, 1.84M or 1.8M, not 1.85M); percentages may be a percent
fact or a fraction fact x 100; signs are ignored; entity and account codes are allowed; dates
must match a fact date (day precision when a day is given). The parts of a fact date (year,
month, day) are not numbers on their own, so "within 21 days" fails even when a fact date falls
on the 21st (#61 review). A small number that happens to equal a count fact (3 lines) still
passes; the wording rules catch the deadline forms of it. A name in braces that is not a
figure rejects the draft, and so does a wording rule from A10. Known limit: the verifier cannot
prove that a figure is described correctly ("the liability" for the gap). Naming each figure
with its meaning reduces this, and the preparer still reads the draft. Owner: team.

**A29. Template fallback.** *Info (updated in #29).* Without Ollama, or after two rejected
drafts, the comment starts with "Standard note (no AI was used):" and carries
`verifier = "not_run"`. Templates use the same named figures and formatter as the model, end
with the same suggested check, and are tested to pass the verifier. Owner: team.

## API and governance

**A30. Schema additions.** *Info (confirmed 18 Nov 2026, #5).* Additive only:
`ExceptionRecord.decided_class` and `ExceptionRecord.edited_comment` (the person's class and
edited comment, kept apart from the AI draft); `Rules` gains `payment_profiles`,
`sentinel_s1_scope`, `sentinel_s2_min_amount`, spike, look-back, close-review, typo, Miner and
score-scaling parameters, so no threshold lives in an engine. Checked against `schemas.py`: the
code matches; every addition is marked `# ADDITION`. Owner: team.

**A31. Decisions.** *Info.* "Accept" in the UI sets status `explained`, "Dismiss" `dismissed`,
"Escalate" `escalated`; each needs a reason (HTTP 422 otherwise). Every decision is appended to
an audit log and survives later runs through the stable exception id. Owner: team.

**A32. Who.** *Info.* No sign-on (out of scope). The person's name comes from the request body
(`decided_by`, `changed_by`) or `OKANE_DEFAULT_USER`. Owner: team.

**A33. Rules changes re-run.** *Info.* Each PUT on `/api/rules` logs one entry per changed field
and starts a new run on the same snapshot (trigger `rules_change`), so the inbox reflects the
new rules without re-reading the workbooks. Owner: team.

**A16. Screens.** *Confirm.* Built to the UI reference supplied with the task: Inbox, Exposure,
Sentinel, Rules, plus the exception drawer. Owner: team.

## Repository

**A34. Landing version-1 on main; required checks.** *Decide.* `version-1` and the scaffold
`main` had unrelated histories. Chosen: merge `main` into `version-1` with
`--allow-unrelated-histories -s ours` (the build's tree is kept unchanged) and land it by pull
request, rather than force-pushing over `main`. Consequence: the scaffold commits stay in
history, including a since-removed private scratch file. Required status checks cannot be set:
GitHub refuses branch protection and rulesets on a private repo on the Free plan. Until the
team upgrades (Pro or Team) or makes the repo public, merges go through pull requests by habit
and the `main-is-red` CI job opens an issue when a push to `main` fails. Owner: team.

**A35. Where real identifiers may live in Git.** *Decide (decided 18 Nov 2026, #6).* The brief
turns every Expected value into a golden-test assertion, and some of them are row-level
(document numbers, user ids, single amounts). Chosen: they may stay in this private repo, but
only values the brief quotes, and only in `docs/BRIEF.md`, this file and the `test_real_*`
golden tests, each with a citation. Fixtures, the generator, engine and UI code, prompts, logs,
issues, PRs and commits carry none; synthetic data uses invented user ids (`USER_9##`). Entity
and account codes are structural and allowed everywhere. Rejected: moving row-level values to
a git-ignored file, because the authoritative brief and Git history already hold them.
Governance line: "Real workbooks never enter Git; the repo holds only synthetic fixtures and the
handful of reference figures the brief itself quotes." Owner: team.

**A37. Original rules as the default; where agreed rules live.** *Decide (decided 18 Nov 2026,
#3).* The committed brief stopped inside the Sentinel section; the team's original, longer brief
(private, in `docs/reference/`) specifies the missing items. Chosen: (a) the original's rules,
minus Intercompany, are the default recommendation for #10 to #18, #28 and #33. Each issue still
records the team's decision, and our placeholders (A4 to A10, A26) are the fallback until then.
#9 and #10 were already decided and are unchanged. Any new risk-score scaling must keep the C192
gap first (demo step 4). (b) The original's text is not restored into the committed brief,
because `CLAUDE.md` forbids copying `docs/reference/` content into committed files. Each agreed
rule is written in our own words in this file under its A# item, with no contact details and no
Intercompany material, and `docs/BRIEF.md` section 9 is an index from item to issue to A#.
Rejected: restoring the original's sections into BRIEF.md, which would need the private-content
rule loosened and could carry text never meant for the repo. Owner: team.

## Mentor questions

**A36. Mentor questions.** *Decide (#2).* Several decisions wait on the mentor: the questions
below come from issue #2 and are asked in one message, with lettered options so each can be
answered in a few words. When an answer arrives, record it here (status, answer, date), update
the A# item it affects, and comment on each issue it unblocks with a link to this section. If
there is no answer by the issue's due date, apply the default and set the status to "no answer,
default applied". Issue #2 closes when every row is answered or has its default applied. No
names or contact details go in this file. Owner: team.

Status values: `drafted, not yet sent`, `asked`, `answered`, `no answer, default applied`.

| Q | Question | Unblocks | Status | Default if no answer | Answer | Date |
|---|----------|----------|--------|----------------------|--------|------|
| 1 | Exact deadline and format for the deck, video and summary | #36, #37, #38, #39 | drafted, not yet sent | Brief section 2: deck at most 12 slides plus appendix (PDF), video at most 3 minutes (MP4), one-page summary (PDF); submit Tue 24 Nov, with Mon 23 Nov as code freeze | | |
| 2 | Which working day after month end the close review falls on | #16 (then #17) | drafted, not yet sent | The original rule: the 5th working day after month end, Monday to Friday, no holidays listed (what the code does since #17, A8) | | |
| 3 | Group closing rates for the run date, or ECB reference rates | #8 | drafted, not yet sent | ECB euro reference rates on each workbook's ageing date (public and reproducible), A11 | | |
| 4 | Is the cross-ERP posting text on C192's payment lines a known route, and are some C192 batches paid quarterly? | #20 | drafted, not yet sent | Decided in #20 without waiting: missing payments only for batches due in the last 12 months (A15); a "quarterly" answer needs no change | | |
| 5 | What repeated manual corrections on payroll and fixed-asset accounts usually fix (replaces the CC06 question) | #14 (then #15, #31) | drafted, not yet sent | The original Miner rule: person-posted lines with a header text, score = distinct entities x distinct months; the card is labelled a hypothesis and not called CC06 (A7) | | |
| 6 | Which payroll accounts count as tax or social-security accounts for the risk-score penalty | #18 (then #19) | drafted, not yet sent | C192 279006 only, as built (A9) | | |
| 7 | May masked single findings go to a cloud model, or must the model stay local? | #28 (then #29 to #32) | drafted, not yet sent | Local model only (Ollama), as the data notice requires (A10) | | |
| 8 | May the video and deck show the real (scaled) data, or must they use the synthetic sample? | #25 (then #26, #37, #38) | drafted, not yet sent | Synthetic sample on screen; real figures only as the aggregates the brief quotes | | |
| 9 | How the extract reaches the team today, whether a weekly extract is realistic, and whether real data may sit in a cloud folder during the hackathon | #23 (then #24, #25) | no answer, default applied | Issue #23's recommendation: an upload page in Okane for the demo, the local watched folder kept, no real data in the cloud; a cloud connector shown in the deck as the production route | Default applied in #23 (A38); revisit A38 if the mentor answers, especially on cloud folders | 19 Nov 2026 |
