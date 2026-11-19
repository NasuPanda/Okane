import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { DecisionUpdate, ExceptionFilters, Rules } from "./types";

export const keys = {
  run: ["run"] as const,
  kpis: ["kpis"] as const,
  exceptions: (filters: ExceptionFilters = {}) => ["exceptions", filters] as const,
  exception: (id: string) => ["exception", id] as const,
  exposure: (materiality?: number) => ["exposure", materiality ?? "rule"] as const,
  timeline: (key: string) => ["timeline", key] as const,
  rules: ["rules"] as const,
  rulesLog: ["rules-log"] as const,
};

export const useLatestRun = () => useQuery({ queryKey: keys.run, queryFn: api.latestRun });
export const useKpis = () => useQuery({ queryKey: keys.kpis, queryFn: api.kpis });
export const useExceptions = (filters: ExceptionFilters = {}) =>
  useQuery({ queryKey: keys.exceptions(filters), queryFn: () => api.exceptions(filters) });
export const useException = (id: string | null) =>
  useQuery({ queryKey: keys.exception(id ?? ""), queryFn: () => api.exception(id!), enabled: !!id });
export const useExposure = (materiality?: number) =>
  useQuery({
    queryKey: keys.exposure(materiality),
    queryFn: () => api.exposure(materiality),
    placeholderData: keepPreviousData,
  });
export const useTimeline = (key: string | null) =>
  useQuery({ queryKey: keys.timeline(key ?? ""), queryFn: () => api.timeline(key!), enabled: !!key });
export const useRules = () => useQuery({ queryKey: keys.rules, queryFn: api.rules });
export const useRulesLog = () => useQuery({ queryKey: keys.rulesLog, queryFn: api.rulesLog });

export function useDecide(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (update: DecisionUpdate) => api.decide(id, update),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["exceptions"] });
      void client.invalidateQueries({ queryKey: keys.exception(id) });
      void client.invalidateQueries({ queryKey: keys.kpis });
    },
  });
}

export function useComment(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (refresh: boolean) => api.comment(id, refresh),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.exception(id) }),
  });
}

export function useSaveRules() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ rules, reason }: { rules: Rules; reason: string }) => api.saveRules(rules, reason),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.rules });
      void client.invalidateQueries({ queryKey: keys.rulesLog });
    },
  });
}

export function useStartRun() {
  return useMutation({ mutationFn: api.startRun });
}

export function useUploadExtract() {
  return useMutation({ mutationFn: api.uploadExtract });
}
