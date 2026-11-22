// Aliases over the types generated from the backend's OpenAPI schema (`make types`).
import type { components } from "./schema";

type S = components["schemas"];

export type ExceptionRecord = S["ExceptionRecord"];
export type ExceptionDetail = S["ExceptionDetail"];
export type ExceptionType = ExceptionRecord["type"];
export type ExceptionClass = NonNullable<ExceptionRecord["suggested_class"]>;
export type Status = ExceptionRecord["status"];
export type InboxView = NonNullable<ExceptionRecord["inbox_view"]>;
export type DecisionUpdate = S["DecisionUpdate"];
export type DecisionEntry = S["DecisionEntry"];
export type EvidenceLine = S["EvidenceLine"];
export type Comment = S["Comment"];
export type ExposureResponse = S["ExposureResponse"];
export type ExposureGroup = S["ExposureGroup"];
export type PulseTimeline = S["PulseTimeline"];
export type TimelinePoint = S["TimelinePoint"];
export type Rules = S["Rules"];
export type RuleChange = S["RuleChange"];
export type Run = S["Run"];
export type ExtractSource = S["ExtractSource"];
export type UploadResult = S["UploadResult"];
export type Kpis = S["Kpis"];
export type Health = S["Health"];

export type ExceptionFilters = {
  type?: ExceptionType;
  workgroup?: ExceptionRecord["workgroup"];
  entity?: string;
  min_exposure?: number;
  status?: Status;
  view?: InboxView | "all";
};

export type RunEvent = { event: "run_started" | "run_finished"; data: Partial<Run> & { run_id: string } };
