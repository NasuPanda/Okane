import { ArrowUpRight, Check, Loader2, MessageSquareWarning, ShieldQuestion, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useDecide, useException, useExceptions, useRules, useSaveRules } from "@/api/hooks";
import type { ExceptionClass, ExceptionRecord, Status } from "@/api/types";
import { CommentPanel } from "@/components/CommentPanel";
import { GapChart } from "@/components/GapChart";
import { LeadBadge, StatusPill, TypeIcon, TypeLabel, priorityTone, stagger } from "@/components/okane";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { CLASSES, factLabel, isAmountFact, promptOf, STATUS_LABEL, TYPE_HINT, WEIGHT_LABEL, toneOf } from "@/lib/labels";
import { cn, day, eur, stamp } from "@/lib/utils";

const WEIGHT_COLOR: Record<string, string> = {
  exposure: "var(--forest)",
  days_past_expected: "var(--hot)",
  penalty_account: "var(--sentinel)",
  error_type: "var(--mistake)",
  repeats: "var(--miner)",
};

const HIDDEN_FACTS = new Set([
  "prompt", "rule", "hint", "today_detection_basis", "lead_days", "lead_days_daily",
  "lead_days_weekly", "okane_run_date", "lead_view", "lead_badge",
]);

function factValue(key: string, value: number | string): string {
  if (typeof value === "string") return /^\d{4}-\d{2}-\d{2}$/.test(value) ? day(value) : value;
  if (isAmountFact(key)) return eur(value, Math.abs(value) < 1000);
  if (key.endsWith("_pct")) return `${value}%`;
  return value.toLocaleString("en-GB");
}

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="rise space-y-3 border-t py-5">
      <div className="flex items-center justify-between">
        <h3 className="eyebrow">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Stat({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="eyebrow">{label}</div>
      <div className="num text-lg font-light">{children}</div>
    </div>
  );
}

/** The assistant's reading of a spelling prompt (#30). Advisory: the person decides. */
function AssistantTypoCheck({ record }: { record: ExceptionRecord }) {
  const rules = useRules();
  const save = useSaveRules();
  const check = record.ai_check;
  if (!check) return null;
  const found = String(record.facts.found ?? "");
  if (check.verdict === "typo") {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Sparkles className="size-3 text-sentinel" />
        The assistant also reads this as a typo{check.suggestion ? ` of '${check.suggestion}'` : ""}.
      </div>
    );
  }
  const current = rules.data;
  const allowed = (current?.typo_allow_list ?? []).some((w) => w.toLowerCase() === found.toLowerCase());
  const allow = () => {
    if (!current) return;
    save.mutate(
      {
        rules: { ...current, typo_allow_list: [...(current.typo_allow_list ?? []), found.toLowerCase()] },
        reason: `'${found}' is a real word, not a typo (the assistant's reading, confirmed in the drawer)`,
      },
      {
        onSuccess: () =>
          toast.success(`'${found}' is now on the allow-list ✓`, { description: "Logged; re-checking every finding…" }),
        onError: (e) => toast.error("Not saved", { description: e instanceof ApiError ? e.message : String(e) }),
      },
    );
  };
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Sparkles className="size-3 text-sentinel" />
      <span>The assistant reads '{found}' as a real word, not a typo. You decide.</span>
      <Button size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={allow}
        disabled={!current || allowed || save.isPending}>
        {save.isPending ? <Loader2 className="animate-spin" /> : allowed ? <Check /> : null}
        {allowed ? "On the allow-list" : `Add '${found}' to the allow-list`}
      </Button>
    </div>
  );
}

/** Mistake prompts and label mismatches on the same account ("you may have made a mistake"). */
function MistakePrompts({ record }: { record: ExceptionRecord }) {
  const related = useExceptions({ entity: record.entity });
  const prompts = (related.data ?? []).filter(
    (r) => r.account === record.account && r.id !== record.id && promptOf(r),
  );
  const own = promptOf(record);
  const all = own ? [record, ...prompts] : prompts;
  if (!all.length) return null;
  return (
    <Section title="Heads-up: possible slips on this account">
      <div className="space-y-2">
        {all.slice(0, 4).map((r) => (
          <div key={r.id} className="flex gap-3 rounded-xl bg-mistake-soft p-3 text-sm">
            <MessageSquareWarning className="mt-0.5 size-4 shrink-0 text-mistake" />
            <div className="space-y-1">
              <div>{promptOf(r)}</div>
              <div className="text-xs text-muted-foreground">
                {r.evidence.slice(0, 3).join(", ")} · posted {day(String(r.facts.posting_date ?? r.first_signal))}
              </div>
              <AssistantTypoCheck record={r} />
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Decision({ record }: { record: ExceptionRecord }) {
  const decide = useDecide(record.id);
  const [klass, setKlass] = useState<ExceptionClass | null>(record.decided_class ?? record.suggested_class ?? null);
  const [reason, setReason] = useState(record.decision_reason ?? "");

  useEffect(() => {
    setKlass(record.decided_class ?? record.suggested_class ?? null);
    setReason(record.decision_reason ?? "");
  }, [record.id, record.decided_class, record.suggested_class, record.decision_reason]);

  const submit = (status: Status) => {
    if (!reason.trim()) {
      toast.error("Just one more thing", { description: "Add a short reason. Every decision is logged with who, when and why." });
      return;
    }
    decide.mutate(
      { status, decision_reason: reason, decided_class: klass ?? undefined },
      {
        onSuccess: () =>
          toast.success(
            status === "explained" ? "Nice, that's one off your list ✓" : `Marked as ${STATUS_LABEL[status].toLowerCase()}`,
            { description: record.title },
          ),
        onError: (e) => toast.error("Not saved", { description: e instanceof ApiError ? e.message : String(e) }),
      },
    );
  };

  return (
    <Section title="Your call" aside={<StatusPill status={record.status} />}>
      <div className="grid grid-cols-3 gap-2">
        {CLASSES.map((c) => (
          <button
            key={c.value}
            onClick={() => setKlass(c.value)}
            className={cn(
              "rounded-xl border p-3 text-left transition",
              klass === c.value ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/60",
            )}
          >
            <div className="flex items-center justify-between gap-2 text-sm font-medium">
              {c.value}
              {klass === c.value && <Check className="size-4" />}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">{c.hint}</div>
            {record.suggested_class === c.value && (
              <div className="mt-2 inline-flex rounded-full bg-signal-soft px-2 py-0.5 text-[10px] tracking-wide text-signal-ink uppercase">Okane suggests</div>
            )}
          </button>
        ))}
      </div>
      <Textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="What did you check, and why? (required)"
      />
      <div className="flex flex-wrap items-center justify-end gap-2">
        {decide.isPending && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
        <Button variant="outline" onClick={() => submit("dismissed")}>
          Dismiss
        </Button>
        <Button variant="outline" onClick={() => submit("escalated")}>
          Escalate
        </Button>
        <Button onClick={() => submit("explained")}>
          <Check /> Looks right, accept
        </Button>
      </div>
    </Section>
  );
}

export function ExceptionDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const detail = useException(id);
  const rules = useRules();
  const record = detail.data?.exception;
  const materiality = Number(record?.facts.materiality_eur ?? rules.data?.materiality_eur ?? 500_000);

  return (
    <Sheet open={!!id} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="overflow-y-auto">
        {!record ? (
          <div className="space-y-4 p-8">
            <SheetTitle className="sr-only">Loading finding</SheetTitle>
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-9 w-3/4" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : (
          <div className="relative px-8 pt-7 pb-10">
            <div
              aria-hidden
              className={cn("pointer-events-none absolute inset-x-0 top-0 h-44", toneOf(record.type).soft)}
              style={{ maskImage: "linear-gradient(to bottom, black, transparent)" }}
            />
            <header className="rise relative space-y-3 pr-12">
              <div className="flex flex-wrap items-center gap-3">
                <TypeIcon type={record.type} size="lg" />
                <TypeLabel type={record.type} />
                <span className="text-xs text-muted-foreground">
                  {record.workgroup} · {record.erp} · {record.entity} · {record.account} {record.account_name}
                </span>
              </div>
              <SheetTitle className="text-[1.75rem] leading-tight font-light">{record.title}</SheetTitle>
              <SheetDescription asChild>
                <div className="space-y-1">
                  <span className="block text-[15px] text-foreground/80">{TYPE_HINT[record.type]}</span>
                  <span className="flex items-center gap-1.5 text-xs">
                    <ShieldQuestion className="size-3.5" />
                    Rule: {String(record.facts.rule ?? "")}
                  </span>
                </div>
              </SheetDescription>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <LeadBadge record={record} size="lg" />
                <StatusPill status={record.status} />
                {record.suggested_class && <Badge variant="outline">Suggested: {record.suggested_class}</Badge>}
              </div>
            </header>

            <div className="rise relative mt-6 grid grid-cols-2 gap-5 rounded-2xl bg-card p-5 shadow-sm sm:grid-cols-4" style={stagger(1, 80)}>
              <Stat label="Amount · scaled EUR" className="col-span-2 sm:col-span-1">
                <span className={cn("text-2xl", priorityTone(record.score).text)}>{eur(record.exposure_eur)}</span>
              </Stat>
              <Stat label="Okane spotted it">{day(record.first_signal)}</Stat>
              <Stat label="Today's report would">{record.today_detection ? day(record.today_detection) : "Never"}</Stat>
              <Stat label="Payment expected by">{record.expected_by ? day(record.expected_by) : "–"}</Stat>
            </div>

            {detail.data?.timeline && (
              <Section
                title="The money over time · scaled EUR"
                aside={<span className="text-xs text-muted-foreground">coral bars are over the {eur(materiality)} limit</span>}
              >
                <GapChart points={detail.data.timeline} materiality={materiality} />
              </Section>
            )}

            <MistakePrompts record={record} />

            <Section title="A note for the file">
              <CommentPanel record={record} />
            </Section>

            {typeof record.facts.hint === "string" && (
              <Section title="Where to look">
                <p className="text-sm">{record.facts.hint}</p>
              </Section>
            )}

            <Section title="How Okane worked it out">
              <dl className="grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
                {Object.entries(record.facts)
                  .filter(([k]) => !HIDDEN_FACTS.has(k))
                  .map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-4 border-b border-dashed py-1.5">
                      <dt className="text-muted-foreground">{factLabel(k)}</dt>
                      <dd className="num text-right">{factValue(k, v)}</dd>
                    </div>
                  ))}
              </dl>
            </Section>

            <Section title={`Why it's this high on your list · ${record.score.toFixed(0)} of 100`}>
              <div className="space-y-2">
                {Object.entries(record.score_breakdown).map(([k, v]) => {
                  const weight = rules.data?.weights?.[k] ?? 0;
                  return (
                    <div key={k} className="grid grid-cols-[150px_1fr_70px] items-center gap-3 text-sm">
                      <span className="text-muted-foreground">{WEIGHT_LABEL[k] ?? k}</span>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className="grow-x h-full rounded-full"
                          style={{ width: weight ? `${(v / weight) * 100}%` : 0, background: WEIGHT_COLOR[k] ?? "var(--foreground)" }}
                        />
                      </div>
                      <span className="num text-right">
                        {v.toFixed(1)} <span className="text-muted-foreground">/ {weight}</span>
                      </span>
                    </div>
                  );
                })}
                <p className="pt-1 text-xs text-muted-foreground">
                  These weights come from your Rules page. No AI decides the priority.
                </p>
              </div>
            </Section>

            <Section
              title={`The documents behind it · ${record.evidence.length}`}
              aside={<ArrowUpRight className="size-4 text-muted-foreground" />}
            >
              <div className="max-h-72 overflow-auto rounded-xl bg-card">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card">
                    <tr className="text-left">
                      {["Document", "Posted", "Type", "Posted by", "Text", "EUR"].map((h) => (
                        <th key={h} className={cn("eyebrow px-3 py-2.5", h === "EUR" && "text-right")}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.data!.evidence_lines.slice(0, 120).map((line, i) => (
                      <tr key={`${line.document}-${i}`} className="border-t">
                        <td className="num px-3 py-2 whitespace-nowrap">{line.document}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{day(line.posting_date)}</td>
                        <td className="px-3 py-2">{line.doc_type}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{line.user_name}</td>
                        <td className="max-w-56 truncate px-3 py-2" title={line.text ?? ""}>
                          {line.text}
                        </td>
                        <td className="num px-3 py-2 text-right">{eur(line.amount_eur, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {detail.data!.evidence_lines.length === 0 && (
                  <p className="p-4 text-sm text-muted-foreground">
                    Nothing to list here: this finding is about something that's missing.
                  </p>
                )}
              </div>
            </Section>

            <Decision record={record} />

            {detail.data!.decisions.length > 0 && (
              <Section title="History">
                <ol className="space-y-2 text-sm">
                  {[...detail.data!.decisions].reverse().map((d, i) => (
                    <li key={i} className="flex gap-3">
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-foreground" />
                      <div>
                        <span className="font-medium">{d.decided_by}</span> set{" "}
                        <span className="font-medium">{STATUS_LABEL[d.status]}</span>
                        {d.decided_class && <> as {d.decided_class}</>} · {stamp(d.decided_at)}
                        {d.decision_reason && <div className="text-muted-foreground">“{d.decision_reason}”</div>}
                      </div>
                    </li>
                  ))}
                </ol>
              </Section>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
