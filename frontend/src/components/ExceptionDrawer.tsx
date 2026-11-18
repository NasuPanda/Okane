import { ArrowUpRight, Check, Loader2, MessageSquareWarning, ShieldQuestion } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useDecide, useException, useExceptions, useRules } from "@/api/hooks";
import type { ExceptionClass, ExceptionRecord, Status } from "@/api/types";
import { CommentPanel } from "@/components/CommentPanel";
import { GapChart } from "@/components/GapChart";
import { LeadBadge, StatusPill, TypeLabel } from "@/components/okane";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { CLASSES, factLabel, isAmountFact, promptOf, STATUS_LABEL, WEIGHT_LABEL } from "@/lib/labels";
import { cn, day, eur, stamp } from "@/lib/utils";

const HIDDEN_FACTS = new Set(["prompt", "rule", "hint", "today_detection_basis", "lead_days"]);

function factValue(key: string, value: number | string): string {
  if (typeof value === "string") return /^\d{4}-\d{2}-\d{2}$/.test(value) ? day(value) : value;
  if (isAmountFact(key)) return eur(value, Math.abs(value) < 1000);
  if (key.endsWith("_pct")) return `${value}%`;
  return value.toLocaleString("en-GB");
}

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t py-5">
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
    <Section title="You may have made a mistake">
      <div className="space-y-2">
        {all.slice(0, 4).map((r) => (
          <div key={r.id} className="flex gap-3 rounded-xl bg-warn-soft p-3 text-sm">
            <MessageSquareWarning className="mt-0.5 size-4 shrink-0 text-warn" />
            <div className="space-y-1">
              <div>{promptOf(r)}</div>
              <div className="text-xs text-muted-foreground">
                {r.evidence.slice(0, 3).join(", ")} · posted {day(String(r.facts.posting_date ?? r.first_signal))}
              </div>
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
      toast.error("Add a reason first", { description: "Every decision is logged with who, when and why." });
      return;
    }
    decide.mutate(
      { status, decision_reason: reason, decided_class: klass ?? undefined },
      {
        onSuccess: () => toast.success(`${STATUS_LABEL[status]}`, { description: record.title }),
        onError: (e) => toast.error("Not saved", { description: e instanceof ApiError ? e.message : String(e) }),
      },
    );
  };

  return (
    <Section title="Your decision" aside={<StatusPill status={record.status} />}>
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
              <div className="mt-2 text-[10px] tracking-wide text-muted-foreground uppercase">Suggested by the rule</div>
            )}
          </button>
        ))}
      </div>
      <Textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason (required): what you checked and why"
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
          <Check /> Accept
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
          <div className="px-8 pt-7 pb-10">
            <header className="space-y-3 pr-12">
              <div className="flex flex-wrap items-center gap-3">
                <TypeLabel type={record.type} />
                <span className="text-xs text-muted-foreground">
                  {record.workgroup} · {record.erp} · {record.entity} · {record.account} {record.account_name}
                </span>
              </div>
              <SheetTitle className="text-[1.75rem] leading-tight font-light">{record.title}</SheetTitle>
              <SheetDescription className="flex items-center gap-1.5">
                <ShieldQuestion className="size-3.5" />
                {String(record.facts.rule ?? "")}
              </SheetDescription>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <LeadBadge record={record} size="lg" />
                <StatusPill status={record.status} />
                {record.suggested_class && <Badge variant="outline">Suggested: {record.suggested_class}</Badge>}
              </div>
            </header>

            <div className="mt-6 grid grid-cols-2 gap-5 rounded-2xl bg-card p-5 sm:grid-cols-4">
              <Stat label="Exposure · scaled EUR" className="col-span-2 sm:col-span-1">
                <span className="text-2xl">{eur(record.exposure_eur)}</span>
              </Stat>
              <Stat label="Okane flags it">{day(record.first_signal)}</Stat>
              <Stat label="Today's process">{record.today_detection ? day(record.today_detection) : "Never"}</Stat>
              <Stat label="Expected by">{record.expected_by ? day(record.expected_by) : "–"}</Stat>
            </div>

            {detail.data?.timeline && (
              <Section
                title="Month-end balance against expected · scaled EUR"
                aside={<span className="text-xs text-muted-foreground">dashed lines: ± materiality {eur(materiality)}</span>}
              >
                <GapChart points={detail.data.timeline} materiality={materiality} />
              </Section>
            )}

            <MistakePrompts record={record} />

            <Section title="Comment">
              <CommentPanel record={record} />
            </Section>

            {typeof record.facts.hint === "string" && (
              <Section title="Where to look">
                <p className="text-sm">{record.facts.hint}</p>
              </Section>
            )}

            <Section title="Facts computed by Okane">
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

            <Section title={`Why it ranks here · ${record.score.toFixed(1)} of 100`}>
              <div className="space-y-2">
                {Object.entries(record.score_breakdown).map(([k, v]) => {
                  const weight = rules.data?.weights?.[k] ?? 0;
                  return (
                    <div key={k} className="grid grid-cols-[150px_1fr_70px] items-center gap-3 text-sm">
                      <span className="text-muted-foreground">{WEIGHT_LABEL[k] ?? k}</span>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className="h-full bg-foreground" style={{ width: weight ? `${(v / weight) * 100}%` : 0 }} />
                      </div>
                      <span className="num text-right">
                        {v.toFixed(1)} <span className="text-muted-foreground">/ {weight}</span>
                      </span>
                    </div>
                  );
                })}
                <p className="pt-1 text-xs text-muted-foreground">
                  Weights are set by the controller in Rules. No model sets a score.
                </p>
              </div>
            </Section>

            <Section
              title={`Evidence · ${record.evidence.length} document${record.evidence.length === 1 ? "" : "s"}`}
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
                    No line to show: this finding is about something missing.
                  </p>
                )}
              </div>
            </Section>

            <Decision record={record} />

            {detail.data!.decisions.length > 0 && (
              <Section title="Audit trail">
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
