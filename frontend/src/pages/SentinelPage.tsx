import { AlertTriangle, Coins, Repeat2, Sparkles, SpellCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { useExceptions } from "@/api/hooks";
import type { ExceptionRecord, ExceptionType } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import { Card, Chip, Empty, LeadBadge, NewTag, PageHeader, StatCard, StatusPill, TypeIcon, TypeLabel, stagger } from "@/components/okane";
import { Skeleton } from "@/components/ui/skeleton";
import { factLabel, isAmountFact, promptOf, toneOf } from "@/lib/labels";
import { PeriodPicker, inPeriod, useIsNew, usePeriod } from "@/lib/period";
import { cn, eur, monthLabel } from "@/lib/utils";

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
    <div className={cn("w-14 shrink-0 rounded-2xl py-3 text-center sm:w-16", toneOf(type).soft)}>
      <div className={cn("num text-2xl leading-none font-light sm:text-3xl", toneOf(type).ink)}>{d.getDate()}</div>
      <div className="eyebrow mt-1.5">{d.toLocaleDateString("en-GB", { month: "short" })}</div>
      <div className="num text-[11px] text-muted-foreground">{d.getFullYear()}</div>
    </div>
  );
}

function FeedItem({ record, index, onOpen }: { record: ExceptionRecord; index: number; onOpen: () => void }) {
  const posted = String(record.facts.posting_date ?? record.first_signal);
  const prompt = promptOf(record);
  const isNew = useIsNew();
  return (
    <button
      onClick={onOpen}
      data-tour={`finding-${record.id}`}
      className="rise group flex w-full gap-3 rounded-2xl bg-card p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-lg sm:gap-5 sm:p-5"
      style={stagger(index, 60)}
    >
      <DateBlock value={posted} type={record.type} />
      <div className="min-w-0 flex-1 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <TypeIcon type={record.type} size="sm" />
            <TypeLabel type={record.type} />
            <NewTag show={isNew(record)} />
          </div>
          <LeadBadge record={record} />
          <span className="sm:hidden">
            <StatusPill status={record.status} />
          </span>
        </div>
        <div className="text-base leading-snug sm:text-[17px]">{record.title}</div>
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
      <div className="hidden shrink-0 self-start sm:block">
        <StatusPill status={record.status} />
      </div>
    </button>
  );
}

/** Decided in #14 (A7): the card shows the top pattern by its repeat strength (company codes x
 *  months); ties go to more months, then more lines. */
function byRepeatStrength(a: ExceptionRecord, b: ExceptionRecord): number {
  const n = (r: ExceptionRecord, k: string) => Number(r.facts[k] ?? 0);
  return n(b, "miner_score") - n(a, "miner_score") || n(b, "months") - n(a, "months") || n(b, "lines") - n(a, "lines");
}

function MinerCard({ records, onOpen }: { records: ExceptionRecord[]; onOpen: (id: string) => void }) {
  const ranked = useMemo(() => [...records].sort(byRepeatStrength), [records]);
  const top = ranked[0];
  if (!top) return null;
  return (
    <section data-tour="sentinel-miner" className="rise space-y-4 overflow-hidden rounded-2xl bg-dock p-5 text-white sm:p-6" style={stagger(2, 80)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="eyebrow flex flex-wrap items-center gap-1.5 !text-white/60">
          <Repeat2 className="size-3.5 text-miner" /> Repeated manual posting
          <span className="rounded-full border border-white/30 px-2 py-0.5 text-[10px] normal-case tracking-normal text-white/70">
            hypothesis
          </span>
        </span>
        <span className="rounded-full bg-miner/20 px-2 py-0.5 text-[11px] text-miner">{records.length} patterns</span>
      </div>
      <div className="text-2xl leading-snug font-light">
        The same posting was typed by hand in <span className="text-signal">{String(top.facts.months)} months</span>
      </div>
      <div className="rounded-xl bg-dock-raised p-4 font-mono text-sm text-signal [overflow-wrap:anywhere]">“{String(top.facts.pattern)}”</div>
      <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        {(["months", "entities", "lines", "total_abs_eur"] as const).map((k) => (
          <div key={k}>
            <div className="text-[11px] tracking-wide text-white/50 uppercase">{factLabel(k)}</div>
            <div className="num text-xl font-light">
              {k === "total_abs_eur" ? eur(Number(top.facts[k])) : String(top.facts[k])}
            </div>
          </div>
        ))}
      </div>
      <MinerStory record={top} />
      <div className="flex flex-wrap gap-2">
        {ranked.slice(0, 6).map((r) => (
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

/** #31: the static Miner card, every figure read from the record's facts (A7). */
function MinerStory({ record: r }: { record: ExceptionRecord }) {
  const f = r.facts;
  const people = Number(f.people);
  const rows: [string, string][] = [
    [
      "What is corrected",
      `Document type ${String(f.doc_type || "–")} on account ${r.account}${r.account_name ? ` ${r.account_name}` : ""}`,
    ],
    [
      "How often",
      `${String(f.lines)} lines in ${String(f.documents)} documents, ${monthLabel(String(f.first_month))} to ${monthLabel(String(f.last_month))}`,
    ],
    ["Where", `Company code${Number(f.entities) === 1 ? "" : "s"} ${String(f.entity_list)}`],
    [
      "Who",
      people === 1 ? "One colleague, typed by hand each time" : `${people} colleagues, typed by hand each time`,
    ],
    [
      "If it is fixed at the source",
      `${String(f.lines)} manual lines over ${String(f.months)} months would no longer be needed`,
    ],
  ];
  return (
    <div className="space-y-3">
      <dl className="grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-white/50">{label}</dt>
            <dd className="text-white/85">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm text-white/70">
        <Sparkles className="mr-1 inline size-3.5 text-signal" />
        {String(f.hint)} <span className="text-white/50">This is a hypothesis for you to check, not a finding.</span>
      </p>
    </div>
  );
}

export function SentinelPage() {
  const all = useExceptions();
  const open = useOpenFinding();
  const [feed, setFeed] = useState<Feed>("all");
  const period = usePeriod();
  // The shared report period (linked with the Inbox): only findings posted or first seen in it.
  const scoped = useMemo(() => (all.data ?? []).filter((r) => inPeriod(r, period.range)), [all.data, period.range]);

  const items = useMemo(
    () =>
      scoped
        .filter((r) => FEED_TYPES[feed].includes(r.type))
        .sort((a, b) => String(b.facts.posting_date ?? b.first_signal).localeCompare(String(a.facts.posting_date ?? a.first_signal))),
    [scoped, feed],
  );
  const miner = useMemo(() => scoped.filter((r) => r.type === "miner_cluster"), [scoped]);
  const count = (f: Feed) => scoped.filter((r) => FEED_TYPES[f].includes(r.type)).length;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Sentinel"
        trail={["Posting-day checks"]}
        tour="sentinel-header"
        subtitle="Small slips caught on the day they're posted, instead of at the month-end review: odd amounts, currency mix-ups and typos."
      />

      <div data-tour="sentinel-period">
        <PeriodPicker className="rise" />
      </div>

      <div data-tour="sentinel-stats" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard index={0} label="Unusually large amounts" value={count("outliers")} note="far above what the account normally sees"
          icon={AlertTriangle} color="var(--sentinel)" soft="var(--sentinel-soft)" bars={count("outliers") * 6} />
        <StatCard index={1} label="Currency mix-ups" value={count("currencies")} note="mixed or unconverted currencies"
          icon={Coins} color="var(--miner)" soft="var(--miner-soft)" bars={count("currencies") * 8} />
        <StatCard index={2} label="Possible typos" value={count("mistakes")} note="misspelt words and wrong months"
          icon={SpellCheck} color="var(--mistake)" soft="var(--mistake-soft)" bars={count("mistakes") * 4} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_380px]">
        <div data-tour="sentinel-feed" className="space-y-4">
          <div data-tour="sentinel-chips" className="rise flex flex-wrap gap-2" style={stagger(3, 70)}>
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
            <Empty title="Nothing slipped through 🎉">
              {period.range ? `No posting-day finding ${period.grain === "day" ? "on" : "in"} ${period.range.label}.` : "No posting-day finding in this check."}
            </Empty>
          ) : (
            items.map((r, i) => <FeedItem key={r.id} record={r} index={i} onOpen={() => open(r.id)} />)
          )}
        </div>
        <div className="space-y-4">
          <MinerCard records={miner} onOpen={open} />
          <Card data-tour="sentinel-explainer" className="space-y-2 text-sm" style={stagger(3, 80)}>
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
