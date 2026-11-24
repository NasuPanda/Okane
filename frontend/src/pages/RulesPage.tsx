import { History, Loader2, Save, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useRules, useRulesLog, useSaveRules } from "@/api/hooks";
import type { Rules } from "@/api/types";
import { Card, PageHeader } from "@/components/okane";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { WEIGHT_LABEL, weekdayName } from "@/lib/labels";
import { cn, eur, shortEur, stamp } from "@/lib/utils";

type Scope = NonNullable<Rules["sentinel_s1_scope"]>;
const SCOPES: { value: Scope; label: string; hint: string }[] = [
  { value: "people_only", label: "People only", hint: "Entries typed in by a colleague" },
  { value: "exempt_bot_upload", label: "People + some robots", hint: "Skips the routine monthly upload robot" },
  { value: "all", label: "Everyone", hint: "Includes routine robot batches (noisier)" },
];

const WEIGHT_COLOR: Record<string, string> = {
  exposure: "var(--forest)",
  days_past_expected: "var(--hot)",
  penalty_account: "var(--sentinel)",
  error_type: "var(--mistake)",
  repeats: "var(--miner)",
};

const FIELD_LABEL: Record<string, string> = {
  materiality_eur: "Materiality limit (EUR)",
  tolerance_pct: "Tolerance (share of batch)",
  tolerance_eur: "Tolerance floor (EUR)",
  grace_days: "Grace days",
  missing_payment_lookback_months: "Missing payments: months checked",
  outlier_multiple: "Unusually large means",
  sentinel_s1_scope: "Large amounts checked for",
  sentinel_s2_min_amount: "Same amount, two currencies: smallest amount",
  close_review_working_day: "Close review: working day after month end",
  close_review_holidays: "Close review: holidays",
  lead_time_view: "Days earlier: counted from",
  miner_min_score: "Repeated postings: smallest repeat strength",
  miner_min_repeats: "Repeated postings: fewest months",
  miner_by_user: "Repeated postings: same person only",
  repeats_min_months: "Priority: months of repeated posting",
  typo_allow_list: "Words that are never typos",
  typo_max_rare_count: "Typos: rare word seen at most",
  typo_common_ratio: "Typos: usual spelling at least … times as common",
  typo_max_edits: "Typos: letters different",
  typo_min_word_length: "Typos: shortest word checked",
  period_label_min_lines: "Wrong month label: smallest document",
  missing_payment_balance_check: "Missing payments: check the account balance first",
  account_normal_side: "Each account's normal side",
  fa_recent_days: "Fixed assets: days that count as this month",
  unconfirmed_rate_currencies: "Currencies with an estimated rate",
  miner_max_paired_share: "Repeated postings: drop when this share of lines is reversed with the same text",
  label_mismatch_min_share: "Wrong month label: payment's smallest share of the batch",
  sentinel_s1_skip_no_overdue_accounts: "Large amounts: skip No Overdue accounts",
  new_since_days: "New this week: days counted",
};

function fieldLabel(field: string) {
  if (field.startsWith("weights.")) return `Weight: ${WEIGHT_LABEL[field.slice(8)] ?? field.slice(8)}`;
  return FIELD_LABEL[field] ?? field.replace(/_/g, " ");
}

function NumberField({
  label,
  hint,
  value,
  onChange,
  step = 1,
  tour,
}: {
  label: string;
  hint: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  /** A key the tutorial (A39) highlights. */
  tour?: string;
}) {
  return (
    <label data-tour={tour} className="grid grid-cols-1 items-center gap-2 border-b border-dashed py-3 sm:grid-cols-[1fr_140px] sm:gap-4">
      <span>
        <span className="block text-sm">{label}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
      <Input
        type="number"
        step={step}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => onChange(e.target.valueAsNumber)}
        className="num text-right"
      />
    </label>
  );
}

function parseWords(text: string): string[] {
  return text
    .split(",")
    .map((w) => w.trim().toLowerCase())
    .filter((w, i, all) => w && all.indexOf(w) === i);
}

function WordListField({
  label,
  hint,
  value,
  onChange,
  tour,
}: {
  label: string;
  hint: string;
  value: string[];
  onChange: (v: string[]) => void;
  tour?: string;
}) {
  const joined = value.join(", ");
  const [text, setText] = useState(joined);
  // keep the typed text (with a trailing comma) unless the list changed elsewhere, e.g. Undo
  useEffect(() => {
    setText((current) => (parseWords(current).join(", ") === joined ? current : joined));
  }, [joined]);
  return (
    <label data-tour={tour} className="grid gap-2 border-b border-dashed py-3">
      <span>
        <span className="block text-sm">{label}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
      <Input
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChange(parseWords(e.target.value));
        }}
      />
    </label>
  );
}

function diffCount(a: Rules, b: Rules): number {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof Rules>;
  let n = 0;
  keys.forEach((k) => {
    if (k === "weights") {
      Object.keys({ ...a.weights, ...b.weights }).forEach((w) => (n += a.weights?.[w] !== b.weights?.[w] ? 1 : 0));
    } else if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) n += 1;
  });
  return n;
}

export function RulesPage() {
  const rules = useRules();
  const log = useRulesLog();
  const save = useSaveRules();
  const [draft, setDraft] = useState<Rules | null>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (rules.data) setDraft(structuredClone(rules.data));
  }, [rules.data]);

  const changes = useMemo(() => (draft && rules.data ? diffCount(rules.data, draft) : 0), [draft, rules.data]);
  const set = <K extends keyof Rules>(key: K, value: Rules[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const weights = draft?.weights ?? {};
  const weightSum = Object.values(weights).reduce((s, v) => s + v, 0);

  const submit = () => {
    if (!draft) return;
    save.mutate(
      { rules: draft, reason },
      {
        onSuccess: () => {
          toast.success("Saved and logged ✓", { description: "Re-ranking every finding with your new settings…" });
          setReason("");
        },
        onError: (e) => toast.error("Not saved", { description: e instanceof ApiError ? e.message : String(e) }),
      },
    );
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Rules"
        trail={["Your settings", "Every change is logged"]}
        tour="rules-header"
        subtitle="You decide what counts as important. Okane never guesses: every finding is ranked with the numbers on this page, and every change is written to the log with your reason."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_420px]">
        {!draft ? (
          <Skeleton className="h-[600px]" />
        ) : (
          <div className="space-y-6">
            <Card data-tour="rules-materiality" className="space-y-5 p-6">
              <div className="flex flex-wrap items-end justify-between gap-4 sm:gap-6">
                <div className="space-y-2">
                  <div className="eyebrow">How big is "big"? · materiality</div>
                  <div className="num text-6xl leading-none font-light">{shortEur(draft.materiality_eur ?? 0)}</div>
                  <div className="text-xs text-muted-foreground">
                    Anything that nets to less than this is treated as small and folds away.
                  </div>
                </div>
                <Input
                  type="number"
                  step={25_000}
                  value={draft.materiality_eur ?? 0}
                  onChange={(e) => set("materiality_eur", e.target.valueAsNumber)}
                  className="num w-40 text-right"
                  aria-label="Materiality in EUR"
                />
              </div>
              <Slider
                min={50_000}
                max={2_000_000}
                step={25_000}
                value={[draft.materiality_eur ?? 0]}
                onValueChange={([v]) => set("materiality_eur", v)}
              />
            </Card>

            <Card className="p-6">
              <div className="eyebrow mb-2">Matching payments to accruals</div>
              <NumberField
                label="Tolerance (share of batch)"
                tour="rules-tolerance"
                hint="How close a payment must be to its accrual, e.g. 0.01 = within 1%"
                step={0.005}
                value={draft.tolerance_pct ?? 0}
                onChange={(v) => set("tolerance_pct", v)}
              />
              <NumberField
                label="Tolerance floor (EUR)"
                tour="rules-tolerance-floor"
                hint="Small differences up to this amount always count as a match"
                step={100}
                value={draft.tolerance_eur ?? 0}
                onChange={(v) => set("tolerance_eur", v)}
              />
              <NumberField
                label="Grace days"
                tour="rules-grace"
                hint="Extra days we wait after the usual payment date before calling it missing"
                value={draft.grace_days ?? 0}
                onChange={(v) => set("grace_days", v)}
              />
              <NumberField
                label="Missing payments: months checked"
                tour="rules-missing-months"
                hint="Accruals whose payment was due longer ago are not raised (the gap alert still lists them)"
                value={draft.missing_payment_lookback_months ?? 12}
                onChange={(v) => set("missing_payment_lookback_months", v)}
              />
              <NumberField
                label="Close review: working day after month end"
                tour="rules-close-day"
                hint="Today's close review falls on this working day (Mon-Fri); used for 'days earlier'"
                value={draft.close_review_working_day ?? 5}
                onChange={(v) => set("close_review_working_day", v)}
              />
              <label data-tour="rules-holidays" className="grid grid-cols-1 items-center gap-2 border-b border-dashed py-3 sm:grid-cols-[1fr_220px] sm:gap-4">
                <span>
                  <span className="block text-sm">Close review: holidays</span>
                  <span className="block text-xs text-muted-foreground">
                    Dates that are not working days, e.g. 2026-12-24, 2026-12-25
                  </span>
                </span>
                <Input
                  key={(draft.close_review_holidays ?? []).join(",")}
                  defaultValue={(draft.close_review_holidays ?? []).join(", ")}
                  onBlur={(e) =>
                    set(
                      "close_review_holidays",
                      e.target.value
                        .split(/[,\s]+/)
                        .map((d) => d.trim())
                        .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d)),
                    )
                  }
                  placeholder="none"
                  className="num"
                />
              </label>
              <div data-tour="rules-lead-view" className="space-y-2 py-3">
                <div className="text-sm">Count "days earlier" from</div>
                <div className="grid grid-cols-2 gap-2">
                  {([
                    ["weekly", `The weekly ${weekdayName(draft.weekly_run_weekday)} run`, "Honest for a weekly run"],
                    ["daily", "The first sign itself", "As if Okane ran every day"],
                  ] as const).map(([value, label, hint]) => (
                    <button
                      key={value}
                      onClick={() => set("lead_time_view", value)}
                      className={cn(
                        "rounded-xl border p-3 text-left transition",
                        (draft.lead_time_view ?? "weekly") === value ? "border-foreground bg-secondary" : "hover:bg-secondary/60",
                      )}
                    >
                      <div className="text-sm font-medium">{label}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
                    </button>
                  ))}
                </div>
              </div>
            </Card>

            <Card className="space-y-4 p-6">
              <div className="eyebrow">Posting-day checks</div>
              <NumberField
                label="Unusually large means"
                tour="rules-outlier"
                hint="Times bigger than the account's usual amount"
                step={100}
                value={draft.outlier_multiple ?? 0}
                onChange={(v) => set("outlier_multiple", v)}
              />
              <div data-tour="rules-s1-scope" className="space-y-2">
                <div className="text-sm">Check large amounts posted by</div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {SCOPES.map((s) => (
                    <button
                      key={s.value}
                      onClick={() => set("sentinel_s1_scope", s.value)}
                      className={cn(
                        "rounded-xl border p-3 text-left transition",
                        draft.sentinel_s1_scope === s.value ? "border-foreground bg-secondary" : "hover:bg-secondary/60",
                      )}
                    >
                      <div className="text-sm font-medium">{s.label}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{s.hint}</div>
                    </button>
                  ))}
                </div>
              </div>
              <NumberField
                label="Same amount, two currencies: smallest amount"
                tour="rules-s2-min"
                hint="Amounts below this, as typed in the document currency, are not checked"
                step={100}
                value={draft.sentinel_s2_min_amount ?? 0}
                onChange={(v) => set("sentinel_s2_min_amount", v)}
              />
              <div className="pt-2 text-sm font-medium">Possible typos</div>
              <NumberField
                label="Rare word: seen at most"
                tour="rules-typo-rare"
                hint="Times in the run; a word used more often than this is never flagged"
                value={draft.typo_max_rare_count ?? 0}
                onChange={(v) => set("typo_max_rare_count", v)}
              />
              <NumberField
                label="Usual spelling: at least … times as common"
                tour="rules-typo-ratio"
                hint="The word it looks like must be used this many times more often"
                value={draft.typo_common_ratio ?? 0}
                onChange={(v) => set("typo_common_ratio", v)}
              />
              <NumberField
                label="Letters different"
                tour="rules-typo-edits"
                hint="One letter added, removed or replaced counts as one (1 to 3)"
                value={draft.typo_max_edits ?? 0}
                onChange={(v) => set("typo_max_edits", v)}
              />
              <NumberField
                label="Shortest word checked"
                tour="rules-typo-length"
                hint="Letters; shorter words are never flagged"
                value={draft.typo_min_word_length ?? 0}
                onChange={(v) => set("typo_min_word_length", v)}
              />
              <NumberField
                label="Wrong month label: smallest document"
                tour="rules-period-label"
                hint="Lines naming a month; a line naming another month than most of them is flagged"
                value={draft.period_label_min_lines ?? 0}
                onChange={(v) => set("period_label_min_lines", v)}
              />
              <NumberField
                label="Wrong month label: payment's smallest share of the batch"
                hint="A payment naming another month is flagged only if it pays at least this share of the batch, e.g. 0.1 = 10%"
                step={0.05}
                value={draft.label_mismatch_min_share ?? 0}
                onChange={(v) => set("label_mismatch_min_share", v)}
              />
              <WordListField
                label="Words that are never typos"
                tour="rules-allow-list"
                hint="Abbreviations and foreign words, separated by commas; no typo prompt is raised for them"
                value={draft.typo_allow_list ?? []}
                onChange={(v) => set("typo_allow_list", v)}
              />
            </Card>

            <Card data-tour="rules-miner" className="space-y-4 p-6">
              <div className="eyebrow">Repeated manual postings</div>
              <NumberField
                label="Smallest repeat strength"
                hint="Company codes × months the same header text must reach before it is listed"
                value={draft.miner_min_score ?? 0}
                onChange={(v) => set("miner_min_score", v)}
              />
              <NumberField
                label="Fewest months"
                hint="The same posting must appear in at least this many different months"
                value={draft.miner_min_repeats ?? 0}
                onChange={(v) => set("miner_min_repeats", v)}
              />
              <NumberField
                label="Priority: months of repeated posting"
                hint="A finding on an account with a repeated posting at least this many months long gets the full 'Repeated manual posting' points"
                value={draft.repeats_min_months ?? 0}
                onChange={(v) => set("repeats_min_months", v)}
              />
              <div className="grid grid-cols-2 gap-2">
                {([
                  [true, "Same person only", "One colleague repeats the posting"],
                  [false, "Anyone", "Joins the same posting by different colleagues"],
                ] as const).map(([value, label, hint]) => (
                  <button
                    key={label}
                    onClick={() => set("miner_by_user", value)}
                    className={cn(
                      "rounded-xl border p-3 text-left transition",
                      (draft.miner_by_user ?? true) === value ? "border-foreground bg-secondary" : "hover:bg-secondary/60",
                    )}
                  >
                    <div className="text-sm font-medium">{label}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
                  </button>
                ))}
              </div>
            </Card>

            <Card data-tour="rules-weights" className="space-y-3 p-6">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="eyebrow">What matters most to you · priority weights</div>
                <span className={cn("num text-xs", weightSum === 100 ? "text-muted-foreground" : "text-warn")}>
                  total {weightSum} of 100
                </span>
              </div>
              <div className="flex h-2.5 gap-1">
                {Object.entries(weights).map(([key, value]) => (
                  <div
                    key={key}
                    className="rounded-full transition-all duration-500"
                    style={{ width: `${(value / Math.max(weightSum, 1)) * 100}%`, background: WEIGHT_COLOR[key] }}
                  />
                ))}
              </div>
              {Object.entries(weights).map(([key, value]) => (
                <div key={key} className="grid grid-cols-[1fr_48px] items-center gap-x-4 gap-y-2 sm:grid-cols-[180px_1fr_72px] sm:gap-4">
                  <span className="col-span-2 flex items-center gap-2 text-sm sm:col-span-1">
                    <span className="size-2.5 rounded-full" style={{ background: WEIGHT_COLOR[key] ?? "var(--chart-3)" }} />
                    {WEIGHT_LABEL[key] ?? key}
                  </span>
                  <Slider
                    min={0}
                    max={60}
                    step={5}
                    value={[value]}
                    onValueChange={([v]) => set("weights", { ...weights, [key]: v })}
                  />
                  <span className="num text-right text-sm">{value}</span>
                </div>
              ))}
            </Card>

            <Card
              data-tour="rules-save"
              className={cn(
                "space-y-3 border p-5 transition-shadow",
                changes > 0 && "sticky bottom-40 z-10 border-signal shadow-xl sm:bottom-28",
              )}
            >
              <div className="flex items-center justify-between">
                <div className="text-sm">
                  {changes ? (
                    <>
                      <span className="num font-medium">{changes}</span> unsaved change{changes === 1 ? "" : "s"}
                    </>
                  ) : (
                    <span className="text-muted-foreground">Nothing changed yet</span>
                  )}
                </div>
                {changes > 0 && (
                  <Button variant="ghost" size="sm" onClick={() => rules.data && setDraft(structuredClone(rules.data))}>
                    <Undo2 /> Discard
                  </Button>
                )}
              </div>
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why are you changing this? (required, saved in the log)"
                className="min-h-14"
              />
              <div className="flex justify-end">
                <Button disabled={!changes || reason.trim().length < 3 || save.isPending} onClick={submit}>
                  {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save and re-rank
                </Button>
              </div>
            </Card>
          </div>
        )}

        <Card data-tour="rules-log" className="h-fit space-y-4 p-6">
          <div className="eyebrow flex items-center gap-1.5">
            <History className="size-3.5" /> Who changed what
          </div>
          {log.data?.length ? (
            <ol className="space-y-4">
              {log.data.map((entry) => {
                const before = JSON.parse(entry.old_value);
                const after = JSON.parse(entry.new_value);
                const show = (v: unknown) => (typeof v === "number" && v >= 1000 ? eur(v) : String(v));
                return (
                  <li key={entry.seq} className="space-y-1 border-b border-dashed pb-4 last:border-0">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <span className="size-2 rounded-full bg-signal" />
                      {fieldLabel(entry.field)}
                    </div>
                    <div className="num text-sm">
                      <span className="text-muted-foreground line-through">{show(before)}</span>
                      <span className="mx-2 text-muted-foreground">→</span>
                      {show(after)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {entry.changed_by} · {stamp(entry.changed_at)}
                    </div>
                    <div className="text-xs">“{entry.reason}”</div>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">Nothing changed yet. You're using the starting values from the brief.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
