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
| A4 | Sentinel S2 rule | Decide | Two document currencies in one document, or two local currencies in one company code |
| A5 | Sentinel S3 rule | Decide | Invalid ISO code, or an amount copied unconverted |
| A6 | Typo prompts: fields, thresholds, dictionary | Decide | Per-account dictionary, similarity 80, rarity 2.5x |
| A7 | Recurring-Correction Miner and the CC06 definition | Decide | Person-posted text fingerprint in 3+ months |
| A8 | Lead time: "today's detection date" per type | Decide | Ageing rule / close review + 5 days / never |
| A9 | Risk score scaling | Decide | Linear 0..1 per component, caps in Rules |
| A10 | AI prompt contract and model | Decide | `{"comment": str}`, qwen2.5 7B instruct, temperature 0 |
| A11 | Fixed assets EUR rates (JPY, USD, PLN, CNY) | Confirm | Placeholder values in the sample rates |
| A12 | Pulse match preference differs by profile | Info | Confirmed (#4): per-profile switch kept |
| A13 | 27 Sep 2024 label mismatch settles July, not August | Info | Confirmed (#4): July kept |
| A14 | Missing-batch look-back | Info | Confirmed (#4): 24 months |
| A15 | 21 missing-payment alerts on real data | Decide | Kept, one per unmatched batch |
| A16 | Screens: Inbox, Exposure, Sentinel, Rules | Confirm | Built to the UI reference |
| A34 | Landing version-1 on main; required CI checks | Decide | Merged by pull request; checks not enforceable on the current plan |
| A35 | Where real identifiers may live in Git | Decide | Decided (#6): brief-quoted values only, in the brief, this file and real golden tests |

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

**A20. Inbox and sample data.** *Info.* A run reads the newest Payroll and the newest Fixed
assets workbook in `data/inbox/`. If the inbox has none, it reads `data/sample/` (synthetic)
and marks the run `synthetic`. Owner: team.

**A21. Analysis date.** *Info.* Engines use `OKANE_AS_OF` if set, otherwise today. Golden tests
use 18 Nov 2026 so "the September 2026 batch is expected by 21 Nov 2026" is not yet late.
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

**A15. Missing payments on real data.** *Decide.* The rule yields 21 alerts (C192: 18 across
2023 to 2026; C242: 3). Older C192 batches are probably settled by payment patterns outside the
profile (quarterly CFE and GARP payments). Options: keep (current), restrict to batches inside
the current gap period, or widen the C192 payment profile. Owner: team.

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
median). With our lead-time rule (A8) it is flagged 19 days before that month's close review.
The alternative candidate (Fixed assets P20 C218 119001 document 7750001797) needs the Fixed
assets workbook. Owner: team.

**A4. S2 two currencies.** *Decide.* Implemented as: one document whose lines carry more than
one document currency, or one company code whose lines carry more than one local currency.
Real Payroll data: no hits. Owner: team.

**A5. S3 currency code.** *Decide.* Implemented as: a document currency that is not an ISO 4217
code, or a line whose document and local currencies differ while the amounts are equal (copied
unconverted; amounts below 1 ignored). Real Payroll data: no hits. Owner: team.

**A26. S5 reversal mismatch.** *Info.* P1; not built. The type exists in the schema.
Owner: team.

**A6. Typo prompts.** *Decide.* (1) Spelling: per account, words of 5+ letters used at least
`typo_dictionary_min_count` (5) times form a dictionary; a word at least `typo_min_similarity`
(80) similar to a dictionary word used `typo_rarity_ratio` (2.5) times as often is flagged;
prefix pairs (plurals, longer forms) are skipped; NAME placeholders are ignored. (2) Period
label: a line whose text names a different period than most lines of its document. Real data:
22 prompts (15 spelling, including "Auzahl" for "Auszahl" and "URSAAF" for "URSSAF"; 7 period
labels). Owner: team.

**A7. Recurring-Correction Miner (CC06).** *Decide.* The CC06 definition is unknown. A manual
correction is a person-posted (USER_###) line; its fingerprint is ERP, entity, account,
document type and text with names and digits removed; a fingerprint in at least
`miner_min_repeats` (3) distinct posting months is a cluster. Real data: 42 clusters, too many
for one demo card; the card shows the highest-scored one. Confirm the CC06 meaning and whether
clusters should require a matching bot posting they correct. Owner: team.

## Lead time and score

**A8. Today's detection date.** *Decide.* Per type:
- `pulse_missing_payment`: accrual date + the account's Ageing Allowed (Days) (when the 365-day
  rule would first show it); exempt (pension-type) accounts: never.
- `sentinel_*`, `typo`, `label_mismatch`, `pulse_spike`: the month-end close review, month end
  + `Rules.close_review_days` (5). Badge: "N days before the close review".
- `pulse_gap`, `pulse_missing_batch`, `miner_cluster`: never (today's process has no check that
  sees them). The UI shows "today's process: not detected".
Real data: median 19 days earlier over findings with a date; 45 findings are blind spots.
Owner: team.

**A9. Risk score.** *Decide.* Weights come from Rules (40/20/20/10/10). Each component is scaled
to 0..1: exposure = |exposure| / (5 x materiality), capped; days past expected = days / 90,
capped (a gap counts from its first month above materiality); penalty account = 1 if the
account is in `Rules.penalty_accounts` (default C192 279006, social security); error type =
`Rules.error_type_severity`; repeats = (same type on the same account - 1) / 5, capped (a Miner
cluster counts its months, a gap its months above materiality). With these, the C192 gap ranks
first on real data (89.4), as the demo needs. Owner: team.

**A27. Suggested class.** *Confirm.* Code (never the model) suggests: gap, outliers, S2, S3 =
Required Adjustment Item; missing payment = Timing item if at most 30 days late, otherwise
Required Adjustment Item; missing batch, label mismatch = Timing item; spike, typo, Miner = none.
Owner: team.

## AI layer

**A10. Prompt contract.** *Decide.* The model receives a system prompt and one JSON message with
the masked title, type, workgroup, entity and `facts`; never document numbers, user ids or raw
lines. It must answer `{"comment": "..."}` (pydantic-validated, 10 to 1,200 characters). Default
model `qwen2.5:7b-instruct` (any 7 to 9B instruct model works; set `OKANE_OLLAMA_MODEL`),
temperature 0, one retry when the verifier fails. Only model output is cached (key: exception
id + hash of title, facts and prompt version). The top 3 findings are pre-drafted during a run
when Ollama is reachable. Owner: team.

**A28. Verifier rule.** *Info.* Every number and date in a comment must equal a fact at the
precision shown (1,838,461.53 may appear as 1,838,462, 1.84M or 1.8M, not 1.85M); percentages
may be a percent fact or a fraction fact x 100; signs are ignored; entity and account codes are
allowed; dates must match a fact date (day precision when a day is given). Owner: team.

**A29. Template fallback.** *Info.* Without Ollama, comments start with "Standard note (no AI
was used):" and carry `verifier = "not_run"`. Every template is tested to pass the
verifier anyway. Owner: team.

## API and governance

**A30. Schema additions.** *Confirm.* Additive only: `ExceptionRecord.decided_class` and
`ExceptionRecord.edited_comment` (the person's class and edited comment, kept apart from the AI
draft); `Rules` gains `payment_profiles`, `sentinel_s1_scope`, spike, look-back, close-review,
typo, Miner and score-scaling parameters, so no threshold lives in an engine. Owner: team.

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
