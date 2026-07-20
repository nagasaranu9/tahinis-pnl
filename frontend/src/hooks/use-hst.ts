"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/expenses";

export interface HstPeriod {
  period_label: string;
  year: number;
  quarter: number;
  month?: number;
  hst_total: string;
  expense_total: string;
  expense_count: number;
  missing_tax_count: number;
}

export interface HstSummary {
  months: HstPeriod[];
  quarters: HstPeriod[];
  total_hst: string;
  total_missing_tax_count: number;
}

export function useHstSummary(params: {
  period_start: string;
  period_end: string;
  location_id?: string;
}) {
  const { period_start, period_end, location_id } = params;
  const qs = new URLSearchParams({ period_start, period_end });
  if (location_id) qs.set("location_id", location_id);

  return useQuery({
    queryKey: ["hst-summary", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: HstSummary }>(`${BASE}/hst-summary?${qs}`);
      return data.data;
    },
    enabled: Boolean(period_start && period_end),
  });
}

export function useHstBackfill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<{ data: { task_id: string; status: string } }>(
        `${BASE}/hst-backfill`
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["hst-summary"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
