"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/integrations/pushops";
const STAFFING_BASE = "/api/v1/staffing";

export interface PushSyncStatus {
  connected: boolean;
  company_name?: string;
  last_synced_at?: string | null;
  historical_import_complete?: boolean;
  historical_import_from?: string | null;
}

// PushOperations time-clock/labor sync — distinct from the CSV importer below.
// Runs on Celery beat (incremental) once a PushSyncConfig row is active for
// the tenant; this just surfaces that connection state on the Integrations page.
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

export interface PushOpsImportResult {
  rows_parsed: number;
  expenses_created: number;
  duplicates_skipped: number;
  total_amount: string;
  currency_code: string;
  pay_dates: string[];
}

export interface PushOpsImportInput {
  file: File;
  location_id?: string;
  /** Fallback pay date (YYYY-MM-DD) for exports without a date column. */
  pay_date?: string;
}

export function useImportPushOpsCsv() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: PushOpsImportInput) => {
      const form = new FormData();
      form.set("file", input.file);
      if (input.location_id) form.set("location_id", input.location_id);
      if (input.pay_date) form.set("pay_date", input.pay_date);
      const { data } = await apiClient.post<{ data: PushOpsImportResult }>(
        `${BASE}/import-csv`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      return data.data;
    },
    onSuccess: () => {
      // Labor cost feeds expenses + P&L; refresh both.
      qc.invalidateQueries({ queryKey: ["expenses"] });
      qc.invalidateQueries({ queryKey: ["pnl-report"] });
    },
  });
}
