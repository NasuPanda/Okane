/**
 * One API surface, two sources, one switch: VITE_API_MODE.
 *
 * - "live" (default): the FastAPI backend under /api (Vite proxies it in dev).
 * - "fixtures": the synthetic JSON exported by `make fixtures` into ../fixtures. Decisions,
 *   comments and rule changes are kept in memory so every screen can be exercised offline.
 */
import type {
  Comment,
  DecisionUpdate,
  ExceptionDetail,
  ExceptionFilters,
  ExceptionRecord,
  ExposureResponse,
  Kpis,
  PulseTimeline,
  RuleChange,
  Rules,
  Run,
  RunEvent,
  UploadResult,
} from "./types";

export const API_MODE: "live" | "fixtures" = import.meta.env.VITE_API_MODE === "fixtures" ? "fixtures" : "live";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export interface Api {
  latestRun(): Promise<Run | null>;
  startRun(): Promise<Run>;
  /** Send this week's extract; the backend checks it, keeps a copy and starts a run (A38). */
  uploadExtract(file: File): Promise<UploadResult>;
  exceptions(filters?: ExceptionFilters): Promise<ExceptionRecord[]>;
  exception(id: string): Promise<ExceptionDetail>;
  decide(id: string, update: DecisionUpdate): Promise<ExceptionRecord>;
  comment(id: string, refresh?: boolean): Promise<Comment>;
  exposure(materiality?: number): Promise<ExposureResponse>;
  timeline(key: string): Promise<PulseTimeline>;
  rules(): Promise<Rules>;
  saveRules(rules: Rules, reason: string, changedBy?: string): Promise<Rules>;
  rulesLog(): Promise<RuleChange[]>;
  kpis(): Promise<Kpis>;
  subscribe(handler: (event: RunEvent) => void): () => void;
}

// ----- live ---------------------------------------------------------------------------------
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  return parse<T>(response);
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

const liveApi: Api = {
  latestRun: () => request("/api/runs/latest"),
  startRun: () => request("/api/runs", { method: "POST" }),
  uploadExtract: async (file) =>
    parse(
      await fetch(`/api/uploads${query({ filename: file.name })}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      }),
    ),
  exceptions: (filters = {}) => request(`/api/exceptions${query(filters)}`),
  exception: (id) => request(`/api/exceptions/${id}`),
  decide: (id, update) => request(`/api/exceptions/${id}`, { method: "PATCH", body: JSON.stringify(update) }),
  comment: (id, refresh = false) => request(`/api/exceptions/${id}/comment${query({ refresh })}`, { method: "POST" }),
  exposure: (materiality) => request(`/api/exposure/payroll${query({ materiality })}`),
  timeline: (key) => request(`/api/pulse/${key}/timeline`),
  rules: () => request("/api/rules"),
  saveRules: (rules, reason, changedBy) =>
    request("/api/rules", { method: "PUT", body: JSON.stringify({ rules, reason, changed_by: changedBy }) }),
  rulesLog: () => request("/api/rules/log"),
  kpis: () => request("/api/kpis"),
  subscribe(handler) {
    const source = new EventSource("/api/events");
    const forward = (name: RunEvent["event"]) => (message: MessageEvent<string>) =>
      handler({ event: name, data: JSON.parse(message.data) });
    source.addEventListener("run_started", forward("run_started"));
    source.addEventListener("run_finished", forward("run_finished"));
    return () => source.close();
  },
};

// ----- fixtures -----------------------------------------------------------------------------
type Wrapped<T> = { synthetic: true; data: T };

type Store = {
  run: Run;
  exceptions: ExceptionRecord[];
  details: Record<string, ExceptionDetail>;
  comments: Record<string, Comment>;
  exposure: ExposureResponse;
  timelines: Record<string, PulseTimeline>;
  rules: Rules;
  log: RuleChange[];
  kpis: Kpis;
};

let store: Promise<Store> | null = null;
const listeners = new Set<(event: RunEvent) => void>();

function loadStore(): Promise<Store> {
  store ??= (async () => {
    const [run, exceptions, details, comments, exposure, timelines, rules, log, kpis] = await Promise.all([
      import("@fixtures/run.json"),
      import("@fixtures/exceptions.json"),
      import("@fixtures/exception_details.json"),
      import("@fixtures/comments.json"),
      import("@fixtures/exposure.json"),
      import("@fixtures/timelines.json"),
      import("@fixtures/rules.json"),
      import("@fixtures/rules_log.json"),
      import("@fixtures/kpis.json"),
    ]);
    const data = <T,>(module: { default: unknown }) => structuredClone((module.default as Wrapped<T>).data);
    return {
      run: data<Run>(run),
      exceptions: data<ExceptionRecord[]>(exceptions),
      details: data<Record<string, ExceptionDetail>>(details),
      comments: data<Record<string, Comment>>(comments),
      exposure: data<ExposureResponse>(exposure),
      timelines: data<Record<string, PulseTimeline>>(timelines),
      rules: data<Rules>(rules),
      log: data<RuleChange[]>(log),
      kpis: data<Kpis>(kpis),
    };
  })();
  return store;
}

const later = <T,>(value: T, ms = 120) => new Promise<T>((resolve) => setTimeout(() => resolve(value), ms));

function emit(event: RunEvent) {
  listeners.forEach((listener) => listener(event));
}

const fixtureApi: Api = {
  async latestRun() {
    return later((await loadStore()).run);
  },
  async startRun() {
    const s = await loadStore();
    const run = { ...s.run, status: "running" as const, trigger: "manual" as const };
    emit({ event: "run_started", data: run });
    setTimeout(() => emit({ event: "run_finished", data: { ...s.run, status: "finished" } }), 1400);
    return run;
  },
  async uploadExtract(file) {
    if (!/\.(xlsx|xlsm|xls)$/i.test(file.name)) {
      throw new ApiError(422, `${file.name} is not an Excel workbook (.xlsx, .xlsm or .xls).`);
    }
    const s = await loadStore();
    const kind = /fixed|asset/i.test(file.name) ? ("Fixed assets" as const) : ("Payroll" as const);
    const run = { ...s.run, status: "running" as const, trigger: "upload" as const };
    emit({ event: "run_started", data: run });
    setTimeout(() => emit({ event: "run_finished", data: { ...s.run, status: "finished" } }), 1400);
    return later({ status: "accepted" as const, kind, file_name: file.name, message: `${kind} extract ${file.name} accepted. Checking it now.`, run });
  },
  async exceptions(filters = {}) {
    const s = await loadStore();
    return later(
      s.exceptions.filter(
        (r) =>
          (!filters.type || r.type === filters.type) &&
          (!filters.workgroup || r.workgroup === filters.workgroup) &&
          (!filters.entity || r.entity === filters.entity) &&
          (filters.min_exposure === undefined || Math.abs(r.exposure_eur) >= filters.min_exposure) &&
          (!filters.status || r.status === filters.status) &&
          (!filters.view || filters.view === "all" || r.inbox_view === filters.view),
      ),
    );
  },
  async exception(id) {
    const s = await loadStore();
    const detail = s.details[id];
    if (!detail) throw new ApiError(404, "Exception not found");
    const record = s.exceptions.find((r) => r.id === id) ?? detail.exception;
    return later({ ...detail, exception: record });
  },
  async decide(id, update) {
    const s = await loadStore();
    const record = s.exceptions.find((r) => r.id === id);
    if (!record) throw new ApiError(404, "Exception not found");
    const status = update.status ?? record.status;
    const reason = update.decision_reason ?? (update.status ? null : record.decision_reason);
    if (status !== "new" && !reason?.trim()) {
      throw new ApiError(422, "A reason is required to explain, dismiss or escalate an exception.");
    }
    Object.assign(record, {
      status,
      decision_reason: reason,
      decided_class: update.decided_class ?? record.decided_class,
      edited_comment: update.edited_comment ?? record.edited_comment,
    });
    s.details[id]?.decisions.push({
      exception_id: id,
      status,
      decision_reason: reason ?? null,
      decided_class: record.decided_class ?? null,
      edited_comment: record.edited_comment ?? null,
      decided_by: update.decided_by ?? "controller",
      decided_at: new Date().toISOString().slice(0, 19),
    });
    return later({ ...record });
  },
  async comment(id) {
    const s = await loadStore();
    const comment = s.comments[id];
    if (!comment) throw new ApiError(404, "Exception not found");
    const record = s.exceptions.find((r) => r.id === id);
    if (record) Object.assign(record, { ai_comment: comment.comment, verifier: comment.verifier });
    return later(comment, 500);
  },
  async exposure(materiality) {
    const s = await loadStore();
    const threshold = materiality ?? s.rules.materiality_eur ?? 500_000;
    const groups = s.exposure.groups.map((g) => ({ ...g, above_materiality: Math.abs(g.net_eur) >= threshold }));
    return later({
      ...s.exposure,
      materiality_eur: threshold,
      groups,
      groups_above: groups.filter((g) => g.above_materiality).length,
    });
  },
  async timeline(key) {
    const s = await loadStore();
    const timeline = s.timelines[key];
    if (!timeline) throw new ApiError(404, "No payment profile for this account");
    return later(timeline);
  },
  async rules() {
    return later((await loadStore()).rules);
  },
  async saveRules(rules, reason, changedBy = "controller") {
    const s = await loadStore();
    if (reason.trim().length < 3) throw new ApiError(422, "Give a reason for the change.");
    const before = s.rules as Record<string, unknown>;
    const after = rules as Record<string, unknown>;
    const now = new Date().toISOString().slice(0, 19);
    const changed = Object.keys(after).filter((k) => JSON.stringify(before[k]) !== JSON.stringify(after[k]));
    changed.forEach((field, i) =>
      s.log.unshift({
        seq: s.log.length + i + 1,
        changed_at: now,
        changed_by: changedBy,
        field,
        old_value: JSON.stringify(before[field]),
        new_value: JSON.stringify(after[field]),
        reason,
      }),
    );
    s.rules = structuredClone(rules);
    if (changed.length) void fixtureApi.startRun();
    return later(s.rules);
  },
  async rulesLog() {
    return later((await loadStore()).log);
  },
  async kpis() {
    const s = await loadStore();
    // Like /api/kpis: the inbox tab counts cover the findings still to review, so a decision
    // made here moves them too.
    const toReview = s.exceptions.filter((r) => r.status === "new" || r.status === "escalated");
    const views: Record<string, number> = { attention: 0, prompts: 0, repeats: 0, other: 0, all: toReview.length };
    for (const r of toReview) if (r.inbox_view) views[r.inbox_view] += 1;
    return later({ ...s.kpis, inbox_views: views });
  },
  subscribe(handler) {
    listeners.add(handler);
    return () => listeners.delete(handler);
  },
};

export const api: Api = API_MODE === "fixtures" ? fixtureApi : liveApi;
