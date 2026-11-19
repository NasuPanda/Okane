import type { ExceptionClass, ExceptionRecord, ExceptionType, Status } from "@/api/types";

/** Friendly names: what a person would call each finding. */
export const TYPE_LABEL: Record<ExceptionType, string> = {
  pulse_gap: "Balance doesn't add up",
  pulse_missing_payment: "Payment not found",
  pulse_spike: "Unusually big month",
  pulse_missing_batch: "A month is missing",
  label_mismatch: "Wrong month on a payment",
  sentinel_outlier: "Unusually large amount",
  sentinel_two_currencies: "Same amount, two currencies",
  sentinel_currency_code: "Currency looks off",
  sentinel_reversal: "Reversal doesn't match",
  typo: "Possible typo",
  miner_cluster: "Repeated manual posting",
};

/** One plain sentence per finding, with the accounting term kept in it. */
export const TYPE_HINT: Record<ExceptionType, string> = {
  pulse_gap: "The account holds more or less than its usual payment rhythm says it should.",
  pulse_missing_payment: "An accrual was booked, but no payment has settled it by the date we'd expect.",
  pulse_spike: "This month's accrual is several times bigger than a normal month.",
  pulse_missing_batch: "No accrual batch was booked for this month at all.",
  label_mismatch: "The payment's text names a different month than the accrual it actually pays.",
  sentinel_outlier: "Far bigger than what this account usually sees. Worth a quick look.",
  sentinel_two_currencies: "The same amount was posted in two currencies on the same day; one is probably the wrong currency.",
  sentinel_currency_code: "The currency code doesn't exist, or the euro had replaced it when this was posted.",
  sentinel_reversal: "A reversal that doesn't mirror the entry it reverses.",
  typo: "A word or month label that looks like a slip of the keyboard.",
  miner_cluster:
    "The same posting is typed by hand month after month. It may be a correction; check whether the automated posting can do it.",
};

export type TypeGroup = "pulse" | "sentinel" | "mistakes" | "miner";

export const TYPE_GROUP: Record<ExceptionType, TypeGroup> = {
  pulse_gap: "pulse",
  pulse_missing_payment: "pulse",
  pulse_spike: "pulse",
  pulse_missing_batch: "pulse",
  label_mismatch: "mistakes",
  sentinel_outlier: "sentinel",
  sentinel_two_currencies: "sentinel",
  sentinel_currency_code: "sentinel",
  sentinel_reversal: "sentinel",
  typo: "mistakes",
  miner_cluster: "miner",
};

export const GROUP_LABEL: Record<TypeGroup, string> = {
  pulse: "Payments & accruals",
  sentinel: "Posting checks",
  mistakes: "Possible typos",
  miner: "Repeated postings",
};

/** Tailwind classes per group: solid colour, soft background, text on soft background. */
export const GROUP_TONE: Record<TypeGroup, { solid: string; soft: string; ink: string; bar: string }> = {
  pulse: { solid: "bg-pulse", soft: "bg-pulse-soft", ink: "text-pulse", bar: "var(--pulse)" },
  sentinel: { solid: "bg-sentinel", soft: "bg-sentinel-soft", ink: "text-sentinel", bar: "var(--sentinel)" },
  mistakes: { solid: "bg-mistake", soft: "bg-mistake-soft", ink: "text-mistake", bar: "var(--mistake)" },
  miner: { solid: "bg-miner", soft: "bg-miner-soft", ink: "text-miner", bar: "var(--miner)" },
};

export const toneOf = (type: ExceptionType) => GROUP_TONE[TYPE_GROUP[type]];

export const STATUS_LABEL: Record<Status, string> = {
  new: "To review",
  explained: "Accepted",
  dismissed: "Dismissed",
  escalated: "Escalated",
};

export const CLASSES: { value: ExceptionClass; hint: string }[] = [
  { value: "List component", hint: "It's fine and stays open long-term" },
  { value: "Timing item", hint: "It's fine and clears in a known later month" },
  { value: "Required Adjustment Item", hint: "It's wrong and needs a correcting entry in SAP" },
];

export const WEIGHT_LABEL: Record<string, string> = {
  exposure: "How much money",
  days_past_expected: "How late it is",
  penalty_account: "Sensitive account",
  error_type: "Kind of problem",
  repeats: "How often it happens",
};

const FACT_LABEL: Record<string, string> = {
  rule: "Rule that fired",
  gap_eur: "Gap",
  balance_eur: "Month-end balance",
  expected_eur: "What we'd expect",
  latest_month: "Latest month-end",
  since_month: "Off since",
  months_above_materiality: "Month-ends over the limit",
  lowest_gap_eur: "Smallest gap in that time",
  lowest_gap_month: "Month of the smallest gap",
  materiality_eur: "Materiality limit",
  unmatched_batches: "Accruals without a payment",
  batch_eur: "Accrual amount",
  batch_period: "Month of the accrual",
  batch_lines: "Lines in the accrual",
  accrual_date: "Accrual booked on",
  expected_by: "Payment expected by",
  lag_p90_days: "Usual payment delay (days)",
  grace_days: "Extra grace days",
  days_past_expected: "Days late",
  median_eur: "A normal month",
  multiple: "Times a normal month",
  posting_date: "Posted on",
  missing_period: "Missing month",
  typical_batch_eur: "A typical accrual",
  lookback_months: "Months checked",
  payment_eur: "Payment",
  diff_pct: "Difference (%)",
  label_period: "Text says",
  settles_period: "Actually pays",
  prompt: "Heads-up",
  amount_lc: "Amount (local currency)",
  currency_lc: "Local currency",
  median_abs_lc: "Usual amount on this account",
  outlier_multiple: "Flag at (times the usual)",
  posted_by: "Posted by",
  scope: "Check covers",
  currencies: "Currencies",
  lines: "Lines",
  currency_dc: "Document currency",
  amount_dc: "Amount (document currency)",
  min_amount: "Smallest amount checked",
  euro_since: "Replaced by the euro on",
  found: "Written as",
  suggestion: "Did you mean",
  edits: "Letters different",
  occurrences: "Times written this way",
  dictionary_count: "Times written the usual way",
  found_period: "Month on the line",
  expected_period: "Month of the document",
  pattern: "The repeated header text (names hidden)",
  fingerprint: "What counts as the same posting",
  doc_type: "Document type",
  months: "Months seen",
  entities: "Company codes",
  entity_list: "Company codes involved",
  miner_score: "Repeat strength (company codes × months)",
  first_month: "First seen",
  last_month: "Last seen",
  documents: "Documents",
  people: "People involved",
  total_abs_eur: "Total posted by hand",
  hint: "Our hypothesis",
  today_detection_basis: "Today's report would catch it via",
  lead_days: "Days earlier than today's report",
};

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** Rules.weekly_run_weekday (0 = Monday) as a day name, for "the weekly Monday run". */
export function weekdayName(day: number | null | undefined): string {
  return WEEKDAYS[day ?? 0] ?? WEEKDAYS[0];
}

export function factLabel(key: string): string {
  return FACT_LABEL[key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function isAmountFact(key: string): boolean {
  return key.endsWith("_eur") || key === "amount_lc" || key === "amount_dc" || key === "median_abs_lc";
}

/** Text of the "you may have made a mistake" prompt, when the finding has one. */
export function promptOf(record: ExceptionRecord): string | null {
  const prompt = record.facts.prompt;
  return typeof prompt === "string" ? prompt : null;
}

export function greeting(now = new Date()): string {
  const hour = now.getHours();
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}
