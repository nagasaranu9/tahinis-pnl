"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/integrations/pipeboard";

export interface PipeboardStatus {
  connected: boolean;
  account_id: string | null;
  is_active: boolean;
  last_sync_at: string | null;
  last_sync_error: string | null;
  pipeboard_account_id: string | null;
}

export interface SyncJob {
  id: string;
  job_type: string;
  status: string;
  pipeboard_platform: string | null;
  date_from: string | null;
  date_to: string | null;
  metrics_synced: number;
  campaigns_synced: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  triggered_by: string | null;
}

export function usePipeboardStatus() {
  return useQuery({
    queryKey: ["pipeboard-status"],
    queryFn: async () => {
      const { data } = await apiClient.get<PipeboardStatus>(`${BASE}/status`);
      return data;
    },
  });
}

export function usePipeboardConnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { api_token: string; platform?: string }) => {
      const { data } = await apiClient.post<{ success: boolean; account_id: string }>(
        `${BASE}/connect`,
        body
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeboard-status"] }),
  });
}

export function usePipeboardDisconnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiClient.post(`${BASE}/oauth/disconnect`, { confirm: true });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeboard-status"] }),
  });
}

export function usePipeboardManualSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      date_from?: string;
      date_to?: string;
      pipeboard_platform?: string;
    }) => {
      const { data } = await apiClient.post<{ success: boolean; job_id: string }>(
        `${BASE}/sync/manual`,
        body
      );
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeboard-sync-jobs"] }),
  });
}

export function usePipeboardSyncJobs(status?: string) {
  return useQuery({
    queryKey: ["pipeboard-sync-jobs", status],
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (status) qs.set("status", status);
      const { data } = await apiClient.get<SyncJob[]>(`${BASE}/sync-jobs?${qs}`);
      return data;
    },
  });
}

export function usePipeboardDeleteSyncJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string) => {
      await apiClient.delete(`${BASE}/sync-jobs/${jobId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeboard-sync-jobs"] }),
  });
}

export function usePipeboardAlerts() {
  return useQuery({
    queryKey: ["pipeboard-alerts"],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>(`${BASE}/alerts`);
      return data;
    },
  });
}
