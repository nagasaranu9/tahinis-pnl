"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const STAFFING_BASE = "/api/v1/staffing";

export interface PushSyncStatus {
  connected: boolean;
  company_name?: string;
  last_synced_at?: string | null;
  historical_import_complete?: boolean;
  historical_import_from?: string | null;
}

// PushOperations time-clock/labor sync. Runs on Celery beat (incremental) once
// a PushSyncConfig row is active for the tenant; this surfaces that connection
// state on the Integrations page. The one-off CSV importer
// (POST /integrations/pushops/import-csv) stays on the backend as a manual
// correction/backfill tool but no longer has a UI entry point.
export function usePushSyncStatus() {
  return useQuery({
    queryKey: ["push-sync-status"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: PushSyncStatus }>(`${STAFFING_BASE}/sync-status`);
      return data.data;
    },
  });
}

export function usePushSyncNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<{ data: { status: string; rows_upserted: number } }>(
        `${STAFFING_BASE}/sync-now`
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["push-sync-status"] });
      qc.invalidateQueries({ queryKey: ["staffing"] });
      qc.invalidateQueries({ queryKey: ["pnl-report"] });
    },
  });
}
