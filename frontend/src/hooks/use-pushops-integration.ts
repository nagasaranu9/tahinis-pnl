"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/integrations/pushops";

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
