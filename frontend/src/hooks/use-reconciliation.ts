"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { ReconciliationFlag, ReconciliationRun } from "@/types/reconciliation";

const BASE = "/api/v1/reconciliation";

export function useReconciliationRuns(params: { location_id?: string; page?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.location_id) qs.set("location_id", params.location_id);
  if (params.page) qs.set("page", String(params.page));

  return useQuery({
    queryKey: ["reconciliation-runs", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: ReconciliationRun[]; meta: { total: number } }>(
        `${BASE}/runs?${qs}`
      );
      return data;
    },
    refetchInterval: (q) =>
      (q.state.data?.data ?? []).some((r) => r.status === "pending" || r.status === "running")
        ? 4000
        : false,
  });
}

export function useReconciliationRun(runId: string) {
  return useQuery({
    queryKey: ["reconciliation-run", runId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: ReconciliationRun }>(`${BASE}/runs/${runId}`);
      return data.data;
    },
    refetchInterval: (q) =>
      q.state.data?.status === "pending" || q.state.data?.status === "running" ? 3000 : false,
  });
}

export function useTriggerReconciliation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      period_start: string;
      period_end: string;
      location_id?: string;
    }) => {
      const { data } = await apiClient.post<{ data: ReconciliationRun }>(`${BASE}/runs`, body);
      return data.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reconciliation-runs"] }),
  });
}

export function useReconciliationFlags(params: {
  run_id?: string;
  flag_type?: string;
  unresolved_only?: boolean;
  page?: number;
} = {}) {
  const qs = new URLSearchParams();
  if (params.run_id) qs.set("run_id", params.run_id);
  if (params.flag_type) qs.set("flag_type", params.flag_type);
  if (params.unresolved_only) qs.set("unresolved_only", "true");
  if (params.page) qs.set("page", String(params.page));

  return useQuery({
    queryKey: ["reconciliation-flags", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: ReconciliationFlag[]; meta: { total: number } }>(
        `${BASE}/flags?${qs}`
      );
      return data;
    },
  });
}

export function useResolveFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ flagId, note }: { flagId: string; note: string }) => {
      const { data } = await apiClient.post<{ data: ReconciliationFlag }>(
        `${BASE}/flags/${flagId}/resolve`,
        { resolution_note: note }
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reconciliation-flags"] });
      qc.invalidateQueries({ queryKey: ["reconciliation-runs"] });
    },
  });
}
