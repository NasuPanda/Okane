import { Repeat2 } from "lucide-react";
import { useMemo, useState } from "react";

import { useExceptions } from "@/api/hooks";
import type { ExceptionRecord, ExceptionType } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import { Card, Chip, Empty, Kpi, LeadBadge, PageHeader, StatusPill, TypeLabel } from "@/components/okane";
import { Skeleton } from "@/components/ui/skeleton";
import { factLabel, isAmountFact, promptOf } from "@/lib/labels";
import { eur } from "@/lib/utils";

type Feed = "all" | "outliers" | "currencies" | "mistakes";
const FEED_TYPES: Record<Feed, ExceptionType[]> = {
  all: ["sentinel_outlier", "sentinel_two_currencies", "sentinel_currency_code", "sentinel_reversal", "typo", "label_mismatch"],
  outliers: ["sentinel_outlier"],
  currencies: ["sentinel_two_currencies", "sentinel_currency_code"],
  mistakes: ["typo", "label_mismatch"],
};
const SUMMARY_FACTS = ["amount_lc", "multiple", "posted_by", "currencies", "found", "suggestion", "payment_eur", "diff_pct"];

function DateBlock({ value }: { value: string }) {
  const d = new Date(`${value}T00:00:00`);
  return (
    <div className="w-16 shrink-0 text-center">
      <div className="num text-3xl leading-none font-light">{d.getDate()}</div>
      <div className="eyebrow mt-1.5">{d.toLocaleDateString("en-GB", { month: "short" })}</div>
      <div className="num text-[11px] text-muted-foreground">{d.getFullYear()}</div>
    </div>
  );
}

function FeedItem({ record, onOpen }: { record: ExceptionRecord; onOpen: () => void }) {
  const posted = String(record.facts.posting_date ?? record.first_signal);
  const prompt = promptOf(record);
  return (
    <button onClick={onOpen} className="flex w-full gap-5 rounded-2xl bg-card p-5 text-left transition hover:bg-secondary">
      <DateBlock value={posted} />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TypeLabel type={record.type} />
          <LeadBadge record={record} />
        </div>
        <div className="text-[17px] leading-snug">{record.title}</div>
        {prompt && <div className="text-sm text-warn">{prompt}</div>}
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
          <span>
            {record.workgroup} · {record.erp} · {record.entity} {record.account}
          </span>
          {SUMMARY_FACTS.filter((k) => k in record.facts && !(prompt && (k === "found" || k === "suggestion"))).map((k) => {
            const v = record.facts[k];
            return (
              <span key={k}>
                {factLabel(k)}:{" "}
                <span className="num text-foreground">
                  {typeof v === "number" ? (isAmountFact(k) ? eur(v) : v.toLocaleString("en-GB")) : v}
                </span>
              </span>
            );
          })}
          <span className="num">{record.evidence.slice(0, 2).join(", ")}</span>
        </div>
      </div>
      <div className="shrink-0 self-start">
        <StatusPill status={record.status} />
      </div>
    </button>
  );
}

function MinerCard({ records, onOpen }: { records: ExceptionRecord[]; onOpen: (id: string) => void }) {
  const top = records[0];
  if (!top) return null;
  return (
    <Card className="space-y-4 bg-dock p-6 text-white">
      <div className="flex items-center justify-between">
        <span className="eyebrow flex items-center gap-1.5 !text-white/60">
          <Repeat2 className="size-3.5" /> Recurring-correction miner · CC06
        </span>
        <span className="text-xs text-white/50">{records.length} patterns found</span>
      </div>
      <div className="text-2xl leading-snug font-light">{top.title}</div>
      <div className="rounded-xl bg-dock-raised p-4 font-mono text-sm text-signal">{String(top.facts.pattern)}</div>
      <div className="grid grid-cols-3 gap-4 text-sm">
        {(["months", "documents", "total_abs_eur"] as const).map((k) => (
          <div key={k}>
            <div className="text-[11px] tracking-wide text-white/50 uppercase">{factLabel(k)}</div>
            <div className="num text-xl font-light">
              {k === "total_abs_eur" ? eur(Number(top.facts[k])) : String(top.facts[k])}
            </div>
          </div>
        ))}
      </div>
      <p className="text-sm text-white/70">{String(top.facts.hint)}</p>
      <div className="flex flex-wrap gap-2">
        {records.slice(0, 6).map((r) => (
          <button
            key={r.id}
            onClick={() => onOpen(r.id)}
            className="rounded-full bg-dock-raised px-3 py-1 text-xs text-white/80 hover:text-white"
          >
            {r.entity} {r.account} · {String(r.facts.months)} months
          </button>
        ))}
      </div>
    </Card>
  );
}

export function SentinelPage() {
  const all = useExceptions();
  const open = useOpenFinding();
  const [feed, setFeed] = useState<Feed>("all");

  const items = useMemo(
    () =>
      (all.data ?? [])
        .filter((r) => FEED_TYPES[feed].includes(r.type))
        .sort((a, b) => String(b.facts.posting_date ?? b.first_signal).localeCompare(String(a.facts.posting_date ?? a.first_signal))),
    [all.data, feed],
  );
  const miner = useMemo(() => (all.data ?? []).filter((r) => r.type === "miner_cluster"), [all.data]);
  const count = (f: Feed) => (all.data ?? []).filter((r) => FEED_TYPES[f].includes(r.type)).length;
  const leads = items.map((r) => r.lead_days).filter((d): d is number => d !== null && d !== undefined);
  const median = leads.length ? [...leads].sort((a, b) => a - b)[Math.floor(leads.length / 2)] : null;

  return (
    <div className="space-y-8">
      <PageHeader title="Sentinel" trail={["Posting-day checks", "Known error types, caught on the day they are posted"]} />

      <div className="grid grid-cols-2 divide-x border-y py-6 md:grid-cols-4">
        <Kpi label="Outlier amounts" value={count("outliers")} note="S1 · scope set in Rules" />
        <Kpi label="Currency problems" value={count("currencies")} note="S2 and S3" />
        <Kpi label="Mistake prompts" value={count("mistakes")} note="spelling and period labels" />
        <Kpi label="Flagged earlier by" value={median ?? "–"} unit="days" note="median, before the close review" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Chip active={feed === "all"} onClick={() => setFeed("all")} count={count("all")}>
              All
            </Chip>
            <Chip active={feed === "outliers"} onClick={() => setFeed("outliers")} count={count("outliers")}>
              Outliers
            </Chip>
            <Chip active={feed === "currencies"} onClick={() => setFeed("currencies")} count={count("currencies")}>
              Currencies
            </Chip>
            <Chip active={feed === "mistakes"} onClick={() => setFeed("mistakes")} count={count("mistakes")}>
              Mistake prompts
            </Chip>
          </div>
          {all.isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
          ) : items.length === 0 ? (
            <Empty title="No posting-day findings">Nothing in this run matches the selected checks.</Empty>
          ) : (
            items.map((r) => <FeedItem key={r.id} record={r} onOpen={() => open(r.id)} />)
          )}
        </div>
        <div className="space-y-4">
          <MinerCard records={miner} onOpen={open} />
          <Card className="space-y-2 text-sm">
            <div className="eyebrow">How the badge is computed</div>
            <p className="text-muted-foreground">
              Okane flags a posting error on its posting date. Today it would surface at the month-end close review
              (month end plus the review days set in Rules). The badge is the difference in days.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
