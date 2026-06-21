"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { ToastSyncConfig, ToastSyncJob } from "@/types/toast";

const BASE = "/api/v1/integrations/toast";

export function useToastStatus(locationId: string | undefined) {
  return useQuery({
    queryKey: ["toast-status", locationId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: ToastSyncConfig }>(
        `${BASE}/status?location_id=${locationId}`
      );
      return data.data;
    },
    enabled: !!locationId,
    retry: false,
    // Poll fast while a historical import is in flight so the progress banner
    // updates live; otherwise refetch once a minute to keep "last synced" fresh.
    refetchInterval: (query) => {
      const s = query.state.data?.historical_status;
      return s === "pending" || s === "running" ? 5_000 : 60_000;
    },
  });
}

export function useConnectToast() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      location_id: string;
      client_id: string;
      client_secret: string;
      toast_restaurant_guid: string;
      historical_import_from?: string;
    }) => {
      const { data } = await apiClient.post<{ data: ToastSyncConfig }>(
        `${BASE}/connect`,
        body
      );
      return data.data;
    },
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["toast-status", vars.location_id] });
      qc.invalidateQueries({ queryKey: ["toast-sync-jobs"] });
    },
  });
}

export function useTriggerSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      location_id: string;
      sync_type?: "incremental" | "historical";
    }) => {
      const { data } = await apiClient.post<{ data: ToastSyncJob }>(
        `${BASE}/sync`,
        body
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["toast-sync-jobs"] });
    },
  });
}

export function useBackfillChannels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (locationId: string) => {
      const { data } = await apiClient.post<{
        data: {
          scanned: number;
          updated: number;
          fulfillment_updated: number;
          dining_options: number;
        };
      }>(`${BASE}/backfill-channels?location_id=${locationId}`);
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard-channel-mix"] });
      qc.invalidateQueries({ queryKey: ["dashboard-fulfillment"] });
    },
  });
}

export function useDisconnectToast() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (locationId: string) => {
      await apiClient.delete(`${BASE}/disconnect?location_id=${locationId}`);
    },
    onSuccess: (_, locationId) => {
      qc.invalidateQueries({ queryKey: ["toast-status", locationId] });
    },
  });
}

export function useSyncJobs(locationId?: string) {
  return useQuery({
    queryKey: ["toast-sync-jobs", locationId],
    queryFn: async () => {
      const params = locationId ? `?location_id=${locationId}&limit=20` : "?limit=20";
      const { data } = await apiClient.get<{ data: ToastSyncJob[]; meta: { total: number } }>(
        `${BASE}/sync-jobs${params}`
      );
      return data;
    },
    refetchInterval: (query) => {
      // Poll while any job is running
      const jobs = query.state.data?.data ?? [];
      return jobs.some((j) => j.status === "pending" || j.status === "running") ? 3000 : false;
    },
  });
}
