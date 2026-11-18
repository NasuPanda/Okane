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
import { WEIGHT_LABEL } from "@/lib/labels";
import { cn, eur, shortEur, stamp } from "@/lib/utils";

type Scope = NonNullable<Rules["sentinel_s1_scope"]>;
const SCOPES: { value: Scope; label: string; hint: string }[] = [
  { value: "people_only", label: "People only", hint: "Lines posted by USER accounts" },
  { value: "exempt_bot_upload", label: "Skip upload robots", hint: "Everything except BOT_UPLOAD batches" },
  { value: "all", label: "All postings", hint: "Includes routine robot payroll batches" },
];

const FIELD_LABEL: Record<string, string> = {
  materiality_eur: "Materiality (EUR)",
  tolerance_pct: "Tolerance (share of batch)",
  tolerance_eur: "Tolerance floor (EUR)",
  grace_days: "Grace days",
  outlier_multiple: "Outlier multiple",
  sentinel_s1_scope: "Outlier check scope",
  close_review_days: "Close review (days after month end)",
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
}: {
  label: string;
  hint: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <label className="grid grid-cols-[1fr_140px] items-center gap-4 border-b border-dashed py-3">
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
          toast.success("Rules saved and logged", { description: "Every finding is being re-ranked." });
          setReason("");
        },
        onError: (e) => toast.error("Not saved", { description: e instanceof ApiError ? e.message : String(e) }),
      },
    );
  };

  return (
    <div className="space-y-8">
      <PageHeader title="Rules" trail={["Set by the controller", "Every change is logged"]} />

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        {!draft ? (
          <Skeleton className="h-[600px]" />
        ) : (
          <div className="space-y-6">
            <Card className="space-y-5 p-6">
              <div className="flex items-end justify-between gap-6">
                <div className="space-y-2">
                  <div className="eyebrow">Materiality</div>
                  <div className="num text-6xl leading-none font-light">{shortEur(draft.materiality_eur ?? 0)}</div>
                  <div className="text-xs text-muted-foreground">
                    An account or gap below this amount is not a real exposure.
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
              <div className="eyebrow mb-2">Matching and timing</div>
              <NumberField
                label="Tolerance (share of batch)"
                hint="A payment matches a batch within this share, e.g. 0.01 = 1%"
                step={0.005}
                value={draft.tolerance_pct ?? 0}
                onChange={(v) => set("tolerance_pct", v)}
              />
              <NumberField
                label="Tolerance floor (EUR)"
                hint="Smallest difference always accepted"
                step={100}
                value={draft.tolerance_eur ?? 0}
                onChange={(v) => set("tolerance_eur", v)}
              />
              <NumberField
                label="Grace days"
                hint="Added to the usual payment lag before a payment counts as missing"
                value={draft.grace_days ?? 0}
                onChange={(v) => set("grace_days", v)}
              />
              <NumberField
                label="Close review (days after month end)"
                hint="When today's process reviews a month; used for lead time"
                value={draft.close_review_days ?? 0}
                onChange={(v) => set("close_review_days", v)}
              />
            </Card>

            <Card className="space-y-4 p-6">
              <div className="eyebrow">Posting-day checks</div>
              <NumberField
                label="Outlier multiple"
                hint="Flag an amount at or above this many times the account's median"
                step={100}
                value={draft.outlier_multiple ?? 0}
                onChange={(v) => set("outlier_multiple", v)}
              />
              <div className="space-y-2">
                <div className="text-sm">Outlier check covers</div>
                <div className="grid grid-cols-3 gap-2">
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
                <p className="text-xs text-muted-foreground">Open decision for the team: see docs/ASSUMPTIONS.md (A1).</p>
              </div>
            </Card>

            <Card className="space-y-3 p-6">
              <div className="flex items-center justify-between">
                <div className="eyebrow">Risk weights</div>
                <span className={cn("num text-xs", weightSum === 100 ? "text-muted-foreground" : "text-warn")}>
                  total {weightSum} of 100
                </span>
              </div>
              {Object.entries(weights).map(([key, value]) => (
                <div key={key} className="grid grid-cols-[180px_1fr_72px] items-center gap-4">
                  <span className="text-sm">{WEIGHT_LABEL[key] ?? key}</span>
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

            <Card className="sticky bottom-28 space-y-3 border p-5 shadow-lg">
              <div className="flex items-center justify-between">
                <div className="text-sm">
                  {changes ? (
                    <>
                      <span className="num font-medium">{changes}</span> unsaved change{changes === 1 ? "" : "s"}
                    </>
                  ) : (
                    <span className="text-muted-foreground">No changes</span>
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
                placeholder="Reason for the change (required, kept in the change log)"
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

        <Card className="h-fit space-y-4 p-6">
          <div className="eyebrow flex items-center gap-1.5">
            <History className="size-3.5" /> Change log
          </div>
          {log.data?.length ? (
            <ol className="space-y-4">
              {log.data.map((entry) => {
                const before = JSON.parse(entry.old_value);
                const after = JSON.parse(entry.new_value);
                const show = (v: unknown) => (typeof v === "number" && v >= 1000 ? eur(v) : String(v));
                return (
                  <li key={entry.seq} className="space-y-1 border-b border-dashed pb-4 last:border-0">
                    <div className="text-sm font-medium">{fieldLabel(entry.field)}</div>
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
            <p className="text-sm text-muted-foreground">No change yet. The defaults come from the build brief.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
