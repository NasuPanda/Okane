import type { ExceptionClass, ExceptionRecord, ExceptionType, Status } from "@/api/types";

/** Plain accountant language for every finding type. */
export const TYPE_LABEL: Record<ExceptionType, string> = {
  pulse_gap: "Liability gap",
  pulse_missing_payment: "Missing payment",
  pulse_spike: "Unusual batch size",
  pulse_missing_batch: "Missing accrual batch",
  label_mismatch: "Payment label",
  sentinel_outlier: "Outlier amount",
  sentinel_two_currencies: "Two currencies",
  sentinel_currency_code: "Currency code",
  sentinel_reversal: "Reversal mismatch",
  typo: "Possible mistake",
  miner_cluster: "Recurring correction",
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
  pulse: "Liability Pulse",
  sentinel: "Posting-day checks",
  mistakes: "Mistake prompts",
  miner: "Recurring corrections",
};

export const STATUS_LABEL: Record<Status, string> = {
  new: "Open",
  explained: "Accepted",
  dismissed: "Dismissed",
  escalated: "Escalated",
};

export const CLASSES: { value: ExceptionClass; hint: string }[] = [
  { value: "List component", hint: "Valid long-term item" },
  { value: "Timing item", hint: "Valid, clears in a known future period" },
  { value: "Required Adjustment Item", hint: "Wrong, needs a correcting entry in SAP" },
];

export const WEIGHT_LABEL: Record<string, string> = {
  exposure: "Exposure",
  days_past_expected: "Days past expected",
  penalty_account: "Penalty account",
  error_type: "Error type",
  repeats: "Repeats",
};

const FACT_LABEL: Record<string, string> = {
  rule: "Rule that fired",
  gap_eur: "Gap",
  balance_eur: "Month-end balance",
  expected_eur: "Expected balance",
  latest_month: "Latest month-end",
  since_month: "Above materiality since",
  months_above_materiality: "Month-ends above materiality",
  lowest_gap_eur: "Lowest gap in that period",
  lowest_gap_month: "Lowest gap month",
  materiality_eur: "Materiality",
  unmatched_batches: "Unmatched batches",
  batch_eur: "Batch amount",
  batch_period: "Batch period",
  batch_lines: "Batch lines",
  accrual_date: "Accrual date",
  expected_by: "Expected by",
  lag_p90_days: "Usual payment lag (90th percentile)",
  grace_days: "Grace days",
  days_past_expected: "Days past expected",
  median_eur: "Usual batch (median)",
  multiple: "Times the usual size",
  posting_date: "Posting date",
  missing_period: "Missing period",
  typical_batch_eur: "Typical batch",
  lookback_months: "Look-back (months)",
  payment_eur: "Payment",
  diff_pct: "Difference (%)",
  label_period: "Label says",
  settles_period: "Settles batch",
  prompt: "Prompt",
  amount_lc: "Amount (local currency)",
  currency_lc: "Local currency",
  median_abs_lc: "Account median (local currency)",
  outlier_multiple: "Outlier threshold (x median)",
  posted_by: "Posted by",
  scope: "Check scope",
  currencies: "Currencies",
  lines: "Lines",
  currency_dc: "Document currency",
  amount_dc: "Amount (document currency)",
  found: "Found",
  suggestion: "Did you mean",
  similarity_pct: "Similarity (%)",
  occurrences: "Times used",
  dictionary_count: "Times the usual spelling is used",
  found_period: "Period on the line",
  expected_period: "Period of the document",
  pattern: "Correction text (names masked)",
  doc_type: "Document type",
  months: "Months repeated",
  first_month: "First month",
  last_month: "Last month",
  documents: "Documents",
  people: "People involved",
  total_abs_eur: "Total amount corrected",
  hint: "Where to look",
  today_detection_basis: "Today's process would flag it by",
  lead_days: "Days earlier than today's process",
};

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
