// The tour script (docs/ASSUMPTIONS.md A39). Plain, very simple English. Example cards read their
// figures from the data on screen (never typed in here), and fall back to general words when
// there is no such finding. Nothing here changes data: the tour only highlights and explains.
import type { ExceptionRecord, ExposureGroup, ExposureResponse, Kpis, Rules, Run } from "@/api/types";
import { netMeaning } from "@/lib/labels";
import { eur, shortEur } from "@/lib/utils";
import type { Pose } from "@/tutorial/Kentaro";

export type TourPage = "/" | "/exposure" | "/sentinel" | "/rules";

export type TourCtx = {
  records: ExceptionRecord[];
  kpis?: Kpis;
  rules?: Rules;
  exposure?: ExposureResponse;
  run?: Run | null;
};

/** The tutorials a person can pick (A39): "Getting started" and one per page. */
export type ModuleId = "start" | "inbox" | "exposure" | "sentinel" | "rules";
export type Choice = "full" | ModuleId;

export type Step = {
  page: TourPage;
  /** Which tutorial the card belongs to; by default the one of its page. */
  module?: ModuleId;
  /** Only in the full tour (the closing card). */
  fullOnly?: boolean;
  title: string;
  body: (ctx: TourCtx) => React.ReactNode;
  /** `data-tour` keys to highlight; none = an intro card in the middle of the screen. */
  targets?: string[] | ((ctx: TourCtx) => string[]);
  /** Open this finding's details while the card shows (read-only). */
  finding?: (ctx: TourCtx) => string | undefined;
  pose?: Pose;
  example?: boolean;
};

export const MODULES: { id: ModuleId; name: string; page: TourPage; about: string }[] = [
  { id: "start", name: "Getting started", page: "/", about: "What Okane is for, and the buttons at the top" },
  { id: "inbox", name: "Inbox", page: "/", about: "Your list of findings, and how to work through one" },
  { id: "exposure", name: "Exposure", page: "/exposure", about: "How much is really still open" },
  { id: "sentinel", name: "Sentinel", page: "/sentinel", about: "Slips caught on the day they're posted" },
  { id: "rules", name: "Rules", page: "/rules", about: "Your settings, one by one, in order" },
];

const PAGE_MODULE: Record<TourPage, ModuleId> = { "/": "inbox", "/exposure": "exposure", "/sentinel": "sentinel", "/rules": "rules" };

export const moduleOf = (step: Step): ModuleId => step.module ?? PAGE_MODULE[step.page];

/** The page in view as a tutorial ("This page"). */
export function moduleOfPath(pathname: string): ModuleId {
  return (Object.entries(PAGE_MODULE).find(([page]) => page !== "/" && pathname.startsWith(page))?.[1] ?? "inbox") as ModuleId;
}

export const PAGE_NAME: Record<TourPage, string> = {
  "/": "Inbox",
  "/exposure": "Exposure",
  "/sentinel": "Sentinel",
  "/rules": "Rules",
};

// ----- what the examples point at --------------------------------------------------------------
export const topFinding = (c: TourCtx) => c.records.find((r) => r.inbox_view === "attention") ?? c.records[0];
const firstPrompt = (c: TourCtx) => c.records.find((r) => r.inbox_view === "prompts");
const bigOutlier = (c: TourCtx) => c.records.find((r) => r.type === "sentinel_outlier");
const topMiner = (c: TourCtx) =>
  [...c.records.filter((r) => r.type === "miner_cluster")].sort(
    (a, b) => Number(b.facts.miner_score ?? 0) - Number(a.facts.miner_score ?? 0),
  )[0];
const bigGroup = (c: TourCtx) => c.exposure?.groups.find((g) => g.above_materiality);
export const groupKey = (g: Pick<ExposureGroup, "erp" | "entity" | "account">) => `group-${g.erp}-${g.entity}-${g.account}`;
const limit = (c: TourCtx) => (c.rules ? shortEur(c.rules.materiality_eur) : "the limit");

const B = ({ children }: { children: React.ReactNode }) => <b className="font-semibold">{children}</b>;
const List = ({ items }: { items: React.ReactNode[] }) => (
  <ul className="mt-2 space-y-1.5">
    {items.map((item, i) => (
      <li key={i} className="flex gap-2">
        <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-current opacity-60" />
        <span>{item}</span>
      </li>
    ))}
  </ul>
);

// ----- the cards -------------------------------------------------------------------------------
export const STEPS: Step[] = [
  // Intro
  {
    page: "/",
    pose: "wave",
    title: "Konnichiwa! I'm Mr. Kentaro",
    module: "start",
    body: () => (
      <>
        Welcome to <B>Okane</B>. Okane reads your payroll and fixed asset books and shows you only the
        few things that really need you. I'll walk you through every page. Use the arrows to move, or the
        X to leave at any time. I only show and explain. I never change anything.
      </>
    ),
  },
  {
    page: "/",
    pose: "wave",
    title: "Why Okane exists",
    module: "start",
    body: () => (
      <>
        Today's report calls every line older than a year "overdue". That is too loud: most of those lines
        were already paid. It is also blind: it can't see a real gap or a typing slip until month end.
        Okane matches what was owed to what paid it, keeps only what is really open, and spots mistakes
        on the day they are posted.
      </>
    ),
  },

  // Top bar
  {
    page: "/",
    targets: ["tour-nav"],
    title: "Four pages",
    module: "start",
    body: () => (
      <List
        items={[
          <><B>Inbox</B>: what needs you, sorted by priority.</>,
          <><B>Exposure</B>: how much is really still open.</>,
          <><B>Sentinel</B>: slips caught on the day they are posted.</>,
          <><B>Rules</B>: your settings. You decide what counts.</>,
        ]}
      />
    ),
  },
  {
    page: "/",
    targets: ["tour-dock"],
    title: "Bring in this week's numbers",
    module: "start",
    body: () => (
      <>
        Each week, press <B>Upload extract</B> and pick the Payroll or Fixed assets workbook (or drop the file
        on the page). Okane checks it and runs every check. <B>Check now</B> runs the checks again on the
        latest file. Your file is never changed. (Not now, though: I'm only showing you.)
      </>
    ),
  },
  {
    page: "/",
    targets: ["tour-tutorial", "tour-theme"],
    title: "Help, light and dark",
    module: "start",
    body: () => (
      <>
        Press <B>Tutorial</B> any time to see me again. The sun and moon button switches between a light and
        a dark screen.
      </>
    ),
  },

  // Inbox
  {
    page: "/",
    targets: ["inbox-header"],
    title: "The Inbox in one sentence",
    body: (c) => (
      <>
        This line says it all: today's report calls{" "}
        <B>{c.kpis ? c.kpis.old_rule_lines.toLocaleString("en-GB") : "many"} lines</B> overdue, but after
        matching what was paid only <B>{c.kpis?.exposure_groups_above ?? "a few"} accounts</B> are really
        open. Start with the findings it counts.
      </>
    ),
  },
  {
    page: "/",
    targets: ["inbox-period"],
    title: "Pick a time range",
    body: () => (
      <>
        Choose <B>Daily</B>, <B>Weekly</B>, <B>Monthly</B>, <B>Yearly</B> or <B>Overall</B>. The arrows step back
        to earlier days, weeks or months. Your choice also applies on the Sentinel page. <B>Overall</B> shows
        everything.
      </>
    ),
  },
  {
    page: "/",
    targets: ["inbox-card-waiting", "inbox-card-earlier"],
    title: "Two numbers to watch",
    body: () => (
      <List
        items={[
          <><B>Waiting for you</B>: findings above the limit that you haven't looked at yet.</>,
          <><B>Spotted earlier by</B>: how many days sooner Okane finds things than today's month-end review (the middle value).</>,
        ]}
      />
    ),
  },
  {
    page: "/",
    targets: ["inbox-card-misses", "inbox-card-old"],
    title: "What the old report gets wrong",
    body: () => (
      <List
        items={[
          <><B>Today's report misses</B>: findings no current check would ever catch.</>,
          <><B>Old report says overdue</B>: the big, scary total from the old report. Most of it was already paid.</>,
        ]}
      />
    ),
  },
  {
    page: "/",
    targets: ["inbox-mix", "inbox-gauge"],
    title: "Where findings come from, and your progress",
    body: () => (
      <>
        The coloured bar shows what kind of findings you have: payments, posting checks, possible typos and
        repeated postings. The half-circle on the right fills up as you review findings.
      </>
    ),
  },
  {
    page: "/",
    targets: ["inbox-datasources"],
    title: "Where the numbers came from",
    body: () => (
      <>
        This box names each workbook, the day it was taken, how it arrived and how many lines it had. It
        warns you when this week's file is late.
      </>
    ),
  },
  {
    page: "/",
    targets: ["inbox-tabs", "inbox-filters"],
    title: "Tabs and filters",
    body: (c) => (
      <List
        items={[
          <><B>Above {limit(c)}</B> (the start): findings big enough to matter, plus missing payroll batches.</>,
          <><B>Mistake prompts</B>: possible typos and wrong months. <B>Repeated postings</B>: the same manual fix again and again.</>,
          <><B>Everything</B>: all findings. On the right, pick a book, and see what's to review or done.</>,
        ]}
      />
    ),
  },
  {
    page: "/",
    targets: ["inbox-table"],
    title: "The list",
    body: () => (
      <>
        Each row is one finding. <B>Priority</B> shows how urgent it is (out of 100, from your weights).{" "}
        <B>What we found</B> says it in words, <B>Amount</B> shows the money (scaled EUR), and <B>Spotted</B>{" "}
        shows how early Okane caught it. Click a row to see the proof.
      </>
    ),
  },
  {
    page: "/",
    pose: "think",
    example: true,
    targets: (c) => {
      const t = topFinding(c);
      return t ? [`finding-${t.id}`] : ["inbox-table"];
    },
    title: "Example: the top finding",
    body: (c) => {
      const t = topFinding(c);
      if (!t) return <>When there are findings, the one at the top is where to start.</>;
      return (
        <>
          The top row reads <B>"{t.title}"</B> on {t.entity} {t.account}. The amount is <B>{eur(t.exposure_eur)}</B>.
          {t.facts.lead_badge ? <> Its badge says: <B>{String(t.facts.lead_badge)}</B>.</> : null} Let's open it and
          see what's wrong.
        </>
      );
    },
  },
  {
    page: "/",
    pose: "point",
    example: true,
    finding: (c) => topFinding(c)?.id,
    targets: ["drawer-header", "drawer-stats"],
    title: "What's wrong, in one look",
    body: (c) => {
      const t = topFinding(c);
      return (
        <>
          The top tells you what was found and which rule found it. The four boxes show the amount, the day
          Okane spotted it, the day today's report would ({t?.today_detection ? "much later" : "never, for this one"}),
          and when a payment was expected.
        </>
      );
    },
  },
  {
    page: "/",
    pose: "point",
    example: true,
    finding: (c) => topFinding(c)?.id,
    targets: ["drawer-chart", "drawer-header"],
    title: "The money over time",
    body: () => (
      <>
        For payroll accounts, this chart shows the balance at each month end. When payments match the
        accruals, it comes back near zero. Coral bars are over your limit: money that wasn't settled. A long
        run of coral bars means something is really missing, not just late.
      </>
    ),
  },
  {
    page: "/",
    pose: "point",
    example: true,
    finding: (c) => topFinding(c)?.id,
    targets: ["drawer-slips", "drawer-note"],
    title: "Slips and a note for the file",
    body: () => (
      <>
        <B>Heads-up</B> lists small slips on the same account, like a payment with the wrong month on it. The{" "}
        <B>note for the file</B> is a short draft you can use. Every number in it is checked against the data,
        and you can edit it.
      </>
    ),
  },
  {
    page: "/",
    pose: "point",
    example: true,
    finding: (c) => topFinding(c)?.id,
    targets: ["drawer-why"],
    title: "Why it's high on your list",
    body: () => (
      <>
        These bars show where the priority comes from: how much money, how late, a sensitive account, the kind
        of problem, and repeats. The weights come from your Rules page. No AI decides the priority.
      </>
    ),
  },
  {
    page: "/",
    pose: "think",
    example: true,
    finding: (c) => topFinding(c)?.id,
    targets: ["drawer-call"],
    title: "How to solve it: your call",
    body: () => (
      <List
        items={[
          <>Check the proof: the chart and the documents list below it.</>,
          <>Pick a class: <B>List component</B> (fine, stays open), <B>Timing item</B> (fine, clears later) or <B>Required Adjustment Item</B> (wrong, needs a fix in SAP).</>,
          <>Write a short reason, then <B>Accept</B>, <B>Dismiss</B> or <B>Escalate</B>. Everything is logged. (I won't press anything.)</>,
        ]}
      />
    ),
  },
  {
    page: "/",
    pose: "think",
    example: true,
    targets: ["inbox-tabs"],
    title: "Example: a mistake prompt",
    body: (c) => {
      const p = firstPrompt(c);
      return (
        <>
          Under <B>Mistake prompts</B>
          {p ? (
            <>
              {" "}you'll find one like <B>"{p.title}"</B>.
            </>
          ) : (
            " you'll find possible typos and wrong months."
          )}{" "}
          It's a word that looks misspelt, or a month that doesn't match. To solve it: open it, look at the
          line, and if it's wrong, correct it in SAP. If the word is fine, add it to "Words that are never
          typos" on the Rules page.
        </>
      );
    },
  },

  // Exposure
  {
    page: "/exposure",
    targets: ["exposure-header"],
    title: "Exposure: what's really still open",
    body: () => (
      <>
        This page compares the old report with what is really open. The button at the top right switches
        between the two.
      </>
    ),
  },
  {
    page: "/exposure",
    targets: ["exposure-headline"],
    title: "Old report or real?",
    body: (c) => (
      <>
        On <B>Old report</B>, the big number is everything older than a year:{" "}
        <B>{c.exposure ? eur(c.exposure.old_rule_overdue_abs) : "a big total"}</B>. Switch to{" "}
        <B>What's really open</B> and matched lines fold away. Only{" "}
        <B>{c.exposure?.groups_above ?? "a few"} accounts</B> stay. The strip shows each account as a block.
      </>
    ),
  },
  {
    page: "/exposure",
    targets: ["exposure-materiality"],
    title: "How big is \"big\"?",
    body: () => (
      <>
        Slide this to try a different limit and see which accounts would stay. It's only for trying things
        out: nothing is saved. To change the real limit, use the Rules page, where every change is logged.
      </>
    ),
  },
  {
    page: "/exposure",
    targets: ["exposure-accounts"],
    title: "The accounts",
    body: () => (
      <>
        One row per payroll account: how many lines the old report flags, the old total, and what's{" "}
        <B>really open</B> after matching. Under each net it says what the net means: <B>owed</B> on a
        liability, <B>not yet used up</B> on an asset, or in red when the balance is on the{" "}
        <B>wrong side</B>. Click an account to open its finding.
      </>
    ),
  },
  {
    page: "/exposure",
    pose: "think",
    example: true,
    targets: (c) => {
      const g = bigGroup(c);
      return g ? [groupKey(g)] : ["exposure-accounts"];
    },
    title: "Example: the biggest open account",
    body: (c) => {
      const g = bigGroup(c);
      if (!g) return <>When an account is above the limit, it shows at the top of this list.</>;
      const meaning = netMeaning(g.normal_side, g.net_eur);
      return (
        <>
          <B>{g.entity} {g.account}</B>
          {g.account_name ? ` (${g.account_name})` : ""} still nets to <B>{eur(g.net_eur)}</B> after matching:{" "}
          <B>{meaning.text}</B>.{" "}
          {meaning.wrong
            ? "More went out than was booked, so look for a missing accrual or a posting that belongs elsewhere."
            : "That money was booked but never settled or used up."}{" "}
          To solve it: click the row and look at the documents behind the net.
        </>
      );
    },
  },

  {
    page: "/exposure",
    targets: ["exposure-fixed-assets"],
    title: "Fixed assets",
    body: () => (
      <>
        Fixed assets work the same way: almost every line cancels out with its exact opposite. What's left is
        this month's accruals (recent, still waiting for their partner) and older lines that never matched. EUR
        figures marked <B>estimated rate</B> use a rate that is not confirmed yet.
      </>
    ),
  },

  // Sentinel
  {
    page: "/sentinel",
    targets: ["sentinel-header", "sentinel-period"],
    title: "Sentinel: caught on posting day",
    body: () => (
      <>
        Sentinel looks at each line the day it is posted, instead of waiting for month end. The time range
        here is the same one you picked on the Inbox.
      </>
    ),
  },
  {
    page: "/sentinel",
    targets: ["sentinel-stats"],
    title: "Three kinds of slip",
    body: () => (
      <List
        items={[
          <><B>Unusually large amounts</B>: far bigger than the account normally sees.</>,
          <><B>Currency mix-ups</B>: the same amount in two currencies, or an old currency code.</>,
          <><B>Possible typos</B>: misspelt words and wrong months.</>,
        ]}
      />
    ),
  },
  {
    page: "/sentinel",
    targets: ["sentinel-chips", "sentinel-feed"],
    title: "The feed",
    body: () => (
      <>
        Newest first. Tap a chip to see one kind only. Each item has a badge like{" "}
        <B>"Caught N days before the close review"</B>: how much sooner Okane saw it than today's month-end
        check.
      </>
    ),
  },
  {
    page: "/sentinel",
    targets: ["sentinel-explainer"],
    title: "What \"caught earlier\" means",
    body: () => (
      <>
        Today, a slip is found at the month-end review, a few working days after month end. Okane finds it on
        the day it's posted. The difference is the head start you get.
      </>
    ),
  },
  {
    page: "/sentinel",
    pose: "think",
    example: true,
    targets: (c) => {
      const o = bigOutlier(c);
      return o ? [`finding-${o.id}`] : ["sentinel-feed"];
    },
    title: "Example: a very large amount",
    body: (c) => {
      const o = bigOutlier(c);
      return (
        <>
          {o ? (
            <>
              <B>"{o.title}"</B> on {o.entity} {o.account}.{" "}
            </>
          ) : (
            <>A line far bigger than usual. </>
          )}
          It could be a typing slip, like an extra zero. To solve it: open the document, ask the person who
          posted it, and correct it in SAP if it's wrong. (If you can't see it, set the time range to Overall.)
        </>
      );
    },
  },
  {
    page: "/sentinel",
    pose: "think",
    example: true,
    targets: ["sentinel-miner"],
    title: "Example: the same fix every month",
    body: (c) => {
      const m = topMiner(c);
      return (
        <>
          This card shows a posting typed by hand again and again
          {m ? (
            <>
              : <B>{String(m.facts.months)} months</B> on {m.entity} {m.account}
            </>
          ) : null}
          . It's a guess, not a mistake. To solve it: ask why it's needed every month. If the automatic posting
          or a mapping is fixed once, the manual work goes away.
        </>
      );
    },
  },

  // Rules, in on-screen order
  {
    page: "/rules",
    targets: ["rules-header"],
    title: "Rules: you set the limits",
    body: () => (
      <>
        Every number on this page is yours. Okane never guesses: it ranks findings with these settings, and
        every change is logged with who, when and why. Let's go through them in order. I won't change any.
      </>
    ),
  },
  {
    page: "/rules",
    targets: ["rules-materiality"],
    title: "1. How big is \"big\"?",
    body: (c) => (
      <>
        <B>Materiality</B> ({c.rules ? eur(c.rules.materiality_eur) : "the limit"} now). An account that nets to less
        than this is treated as small and folds away. Lower it to see more, raise it to see less.
      </>
    ),
  },
  {
    page: "/rules",
    targets: ["rules-tolerance", "rules-tolerance-floor", "rules-grace", "rules-missing-months"],
    title: "2. Matching payments to accruals",
    body: () => (
      <List
        items={[
          <><B>Tolerance (share)</B>: how close a payment must be to its accrual, e.g. 0.01 = within 1%.</>,
          <><B>Tolerance floor</B>: small differences up to this amount always count as a match.</>,
          <><B>Grace days</B>: extra days to wait before calling a payment missing.</>,
          <><B>Months checked</B>: how far back to look for missing payments.</>,
        ]}
      />
    ),
  },
  {
    page: "/rules",
    targets: ["rules-close-day", "rules-holidays", "rules-lead-view"],
    title: "3. The month-end review",
    body: () => (
      <List
        items={[
          <><B>Working day after month end</B>: the day today's review happens (used for "days earlier").</>,
          <><B>Holidays</B>: dates that don't count as working days.</>,
          <><B>Count from</B>: the weekly run (honest) or the first sign itself (as if Okane ran daily).</>,
        ]}
      />
    ),
  },
  {
    page: "/rules",
    targets: ["rules-outlier", "rules-s1-scope", "rules-s2-min"],
    title: "4. Posting-day checks",
    body: () => (
      <List
        items={[
          <><B>Unusually large means</B>: how many times bigger than usual counts as odd.</>,
          <><B>Posted by</B>: check lines typed by people, by systems, or both.</>,
          <><B>Same amount, two currencies</B>: smaller amounts than this aren't checked.</>,
        ]}
      />
    ),
  },
  {
    page: "/rules",
    targets: ["rules-typo-rare", "rules-typo-ratio", "rules-typo-edits", "rules-typo-length"],
    title: "5. Possible typos",
    body: () => (
      <List
        items={[
          <><B>Rare word</B>: a word used more often than this is never a typo.</>,
          <><B>Times as common</B>: the right spelling must be used this many times more.</>,
          <><B>Letters different</B>: how many letters may differ (1 is safest).</>,
          <><B>Shortest word</B>: shorter words are never checked.</>,
        ]}
      />
    ),
  },
  {
    page: "/rules",
    targets: ["rules-period-label", "rules-allow-list"],
    title: "6. Wrong months and safe words",
    body: () => (
      <List
        items={[
          <><B>Wrong month label</B>: a document needs at least this many lines naming a month before a different month stands out.</>,
          <><B>Words that are never typos</B>: abbreviations and foreign words to leave alone, separated by commas.</>,
        ]}
      />
    ),
  },
  {
    page: "/rules",
    targets: ["rules-miner"],
    title: "7. Repeated manual postings",
    body: () => (
      <List
        items={[
          <><B>Repeat strength</B>: company codes × months a posting must reach to be shown.</>,
          <><B>Fewest months</B>: it must appear in at least this many months.</>,
          <><B>Priority months</B>: findings on an account with a repeat this long get extra priority.</>,
          <><B>Same person or anyone</B>: count one colleague's repeats, or everyone's together.</>,
        ]}
      />
    ),
  },
  {
    page: "/rules",
    targets: ["rules-weights"],
    title: "8. What matters most to you",
    body: () => (
      <>
        Five sliders build the priority score: how much money, how late, a sensitive account, the kind of
        problem, and repeats. They should add up to 100. Move one up and those findings climb the list.
      </>
    ),
  },
  {
    page: "/rules",
    targets: ["rules-save"],
    title: "9. Save with a reason",
    body: () => (
      <>
        After changing something, write <B>why</B> here and press <B>Save and re-rank</B>. Okane re-checks
        everything with your new settings. <B>Discard</B> undoes changes you haven't saved.
      </>
    ),
  },
  {
    page: "/rules",
    targets: ["rules-log"],
    title: "10. Who changed what",
    body: () => (
      <>Every saved change appears here: the setting, old and new value, who changed it, when and why.</>
    ),
  },
  {
    page: "/rules",
    pose: "think",
    example: true,
    targets: ["rules-materiality", "rules-save", "rules-log"],
    title: "Example: lowering the limit",
    body: (c) => (
      <>
        Say the controller wants a closer look before quarter end. They would set materiality from{" "}
        <B>{c.rules ? eur(c.rules.materiality_eur) : "the current limit"}</B> to <B>100,000</B>, type a reason
        like "Quarter-end review", and press Save. More accounts would then count as really open, and the log
        would show the change. (This is only an example. Nothing was changed.)
      </>
    ),
  },

  // Outro
  {
    page: "/",
    pose: "wave",
    title: "You're ready!",
    fullOnly: true,
    body: () => (
      <>
        That's the whole app. Start with the first row of your Inbox, check the proof, and make your call. Press{" "}
        <B>Tutorial</B> at the top whenever you want me back. Ganbatte!
      </>
    ),
  },
];

/** The cards of a tutorial, as indexes into STEPS: every card for the full tour, or one module. */
export function sequence(choice: Choice): number[] {
  return STEPS.flatMap((step, i) => (choice === "full" || (!step.fullOnly && moduleOf(step) === choice) ? [i] : []));
}
