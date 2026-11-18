import { AlertTriangle, Coins, Repeat2, Sparkles, SpellCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { useExceptions } from "@/api/hooks";
import type { ExceptionRecord, ExceptionType } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import { Card, Chip, Empty, LeadBadge, PageHeader, StatCard, StatusPill, TypeIcon, TypeLabel, stagger } from "@/components/okane";
import { Skeleton } from "@/components/ui/skeleton";
import { factLabel, isAmountFact, promptOf, toneOf } from "@/lib/labels";
import { cn, eur } from "@/lib/utils";

type Feed = "all" | "outliers" | "currencies" | "mistakes";
const FEED_TYPES: Record<Feed, ExceptionType[]> = {
  all: ["sentinel_outlier", "sentinel_two_currencies", "sentinel_currency_code", "sentinel_reversal", "typo", "label_mismatch"],
  outliers: ["sentinel_outlier"],
  currencies: ["sentinel_two_currencies", "sentinel_currency_code"],
  mistakes: ["typo", "label_mismatch"],
};
const SUMMARY_FACTS = ["amount_lc", "multiple", "posted_by", "currencies", "payment_eur", "diff_pct"];

function DateBlock({ value, type }: { value: string; type: ExceptionType }) {
  const d = new Date(`${value}T00:00:00`);
  return (
    <div className={cn("w-16 shrink-0 rounded-2xl py-3 text-center", toneOf(type).soft)}>
      <div className={cn("num text-3xl leading-none font-light", toneOf(type).ink)}>{d.getDate()}</div>
      <div className="eyebrow mt-1.5">{d.toLocaleDateString("en-GB", { month: "short" })}</div>
      <div className="num text-[11px] text-muted-foreground">{d.getFullYear()}</div>
    </div>
  );
}

function FeedItem({ record, index, onOpen }: { record: ExceptionRecord; index: number; onOpen: () => void }) {
  const posted = String(record.facts.posting_date ?? record.first_signal);
  const prompt = promptOf(record);
  return (
    <button
      onClick={onOpen}
      className="rise group flex w-full gap-5 rounded-2xl bg-card p-5 text-left transition-all hover:-translate-y-0.5 hover:shadow-lg"
      style={stagger(index, 60)}
    >
      <DateBlock value={posted} type={record.type} />
      <div className="min-w-0 flex-1 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <TypeIcon type={record.type} size="sm" />
            <TypeLabel type={record.type} />
          </div>
          <LeadBadge record={record} />
        </div>
        <div className="text-[17px] leading-snug">{record.title}</div>
        {prompt && (
          <div className="rounded-xl bg-mistake-soft px-3 py-2 text-sm text-mistake">💡 {prompt}</div>
        )}
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
          <span>
            {record.workgroup} · {record.entity} {record.account}
          </span>
          {SUMMARY_FACTS.filter((k) => k in record.facts).map((k) => {
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
    <section className="rise space-y-4 overflow-hidden rounded-2xl bg-dock p-6 text-white" style={stagger(2, 80)}>
      <div className="flex items-center justify-between">
        <span className="eyebrow flex items-center gap-1.5 !text-white/60">
          <Repeat2 className="size-3.5 text-miner" /> Same fix, every month
        </span>
        <span className="rounded-full bg-miner/20 px-2 py-0.5 text-[11px] text-miner">{records.length} patterns</span>
      </div>
      <div className="text-2xl leading-snug font-light">
        Someone fixes this by hand <span className="text-signal">{String(top.facts.months)} months</span> in a row
      </div>
      <div className="rounded-xl bg-dock-raised p-4 font-mono text-sm text-signal">“{String(top.facts.pattern)}”</div>
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
      <p className="text-sm text-white/70">
        <Sparkles className="mr-1 inline size-3.5 text-signal" />
        {String(top.facts.hint)}
      </p>
      <div className="flex flex-wrap gap-2">
        {records.slice(0, 6).map((r) => (
          <button
            key={r.id}
            onClick={() => onOpen(r.id)}
            className="rounded-full bg-dock-raised px-3 py-1 text-xs text-white/80 transition hover:bg-miner hover:text-white"
          >
            {r.entity} {r.account} · {String(r.facts.months)} months
          </button>
        ))}
      </div>
    </section>
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

  return (
    <div className="space-y-8">
      <PageHeader
        title="Sentinel"
        trail={["Posting-day checks"]}
        subtitle="Small slips caught on the day they're posted, instead of at the month-end review: odd amounts, currency mix-ups and typos."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard index={0} label="Unusually large amounts" value={count("outliers")} note="far above what the account normally sees"
          icon={AlertTriangle} color="var(--sentinel)" soft="var(--sentinel-soft)" bars={count("outliers") * 6} />
        <StatCard index={1} label="Currency mix-ups" value={count("currencies")} note="mixed or unconverted currencies"
          icon={Coins} color="var(--miner)" soft="var(--miner-soft)" bars={count("currencies") * 8} />
        <StatCard index={2} label="Possible typos" value={count("mistakes")} note="misspelt words and wrong months"
          icon={SpellCheck} color="var(--mistake)" soft="var(--mistake-soft)" bars={count("mistakes") * 4} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <div className="rise flex flex-wrap gap-2" style={stagger(3, 70)}>
            <Chip active={feed === "all"} onClick={() => setFeed("all")} count={count("all")}>
              Everything
            </Chip>
            <Chip active={feed === "outliers"} onClick={() => setFeed("outliers")} count={count("outliers")} dot="var(--sentinel)">
              Large amounts
            </Chip>
            <Chip active={feed === "currencies"} onClick={() => setFeed("currencies")} count={count("currencies")} dot="var(--miner)">
              Currencies
            </Chip>
            <Chip active={feed === "mistakes"} onClick={() => setFeed("mistakes")} count={count("mistakes")} dot="var(--mistake)">
              Typos
            </Chip>
          </div>
          {all.isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
          ) : items.length === 0 ? (
            <Empty title="Nothing slipped through 🎉">No posting-day finding in this check.</Empty>
          ) : (
            items.map((r, i) => <FeedItem key={r.id} record={r} index={i} onOpen={() => open(r.id)} />)
          )}
        </div>
        <div className="space-y-4">
          <MinerCard records={miner} onOpen={open} />
          <Card className="space-y-2 text-sm" style={stagger(3, 80)}>
            <div className="eyebrow">What "caught earlier" means</div>
            <p className="text-muted-foreground">
              Okane flags a slip on the day it's posted. Today it would only surface at the month-end review (a few
              days after month end, set in Rules). The badge shows the difference.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
