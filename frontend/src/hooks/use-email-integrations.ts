"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { EmailSyncConfig, EmailSyncJob } from "@/types/email-sync";

const BASE = "/api/v1/integrations";

// ------------------------------------------------------------------
// Gmail
// ------------------------------------------------------------------

export function useGmailStatus() {
  return useQuery({
    queryKey: ["gmail-status"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: EmailSyncConfig[] }>(`${BASE}/gmail/status`);
      return data.data;
    },
  });
}

export function useGmailAuthUrl() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.get<{ data: { url: string } }>(`${BASE}/gmail/auth-url`);
      return data.data.url;
    },
    onSuccess: (url) => {
      window.location.href = url;
    },
  });
}

export function useGmailSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (configId: string) => {
      const { data } = await apiClient.post<{ data: EmailSyncJob }>(
        `${BASE}/gmail/sync?config_id=${configId}`
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["gmail-sync-jobs"] });
      // Sync runs async in a Celery worker; last_synced_at updates seconds later.
      // Re-poll status so the "Last sync" banner reflects the result without a manual reload.
      [2000, 6000, 12000].forEach((ms) =>
        setTimeout(() => {
          qc.invalidateQueries({ queryKey: ["gmail-status"] });
          qc.invalidateQueries({ queryKey: ["gmail-sync-jobs"] });
        }, ms)
      );
    },
  });
}

export function useGmailDisconnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (configId: string) => {
      await apiClient.delete(`${BASE}/gmail/disconnect?config_id=${configId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gmail-status"] }),
  });
}

export function useGmailSyncJobs(configId?: string) {
  return useQuery({
    queryKey: ["gmail-sync-jobs", configId],
    queryFn: async () => {
      const params = configId ? `?config_id=${configId}` : "";
      const { data } = await apiClient.get<{ data: EmailSyncJob[] }>(
        `${BASE}/gmail/sync-jobs${params}`
      );
      return data.data;
    },
    refetchInterval: (q) =>
      (q.state.data ?? []).some((j) => j.status === "pending" || j.status === "running")
        ? 3000
        : false,
  });
}

// ------------------------------------------------------------------
// Outlook
// ------------------------------------------------------------------

export function useOutlookStatus() {
  return useQuery({
    queryKey: ["outlook-status"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: EmailSyncConfig[] }>(`${BASE}/outlook/status`);
      return data.data;
    },
  });
}

export function useOutlookAuthUrl() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.get<{ data: { url: string } }>(`${BASE}/outlook/auth-url`);
      return data.data.url;
    },
    onSuccess: (url) => {
      window.location.href = url;
    },
  });
}

export function useOutlookSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (configId: string) => {
      const { data } = await apiClient.post<{ data: EmailSyncJob }>(
        `${BASE}/outlook/sync?config_id=${configId}`
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["outlook-sync-jobs"] });
      [2000, 6000, 12000].forEach((ms) =>
        setTimeout(() => {
          qc.invalidateQueries({ queryKey: ["outlook-status"] });
          qc.invalidateQueries({ queryKey: ["outlook-sync-jobs"] });
        }, ms)
      );
    },
  });
}

export function useOutlookDisconnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (configId: string) => {
      await apiClient.delete(`${BASE}/outlook/disconnect?config_id=${configId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["outlook-status"] }),
  });
}
