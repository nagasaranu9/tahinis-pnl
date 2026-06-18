"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { PnLReport, PnLSnapshot } from "@/types/pnl";

const BASE = "/api/v1/pnl";

export function usePnLReport(params: {
  period_start: string;
  period_end: string;
  location_id?: string;
}) {
  const { period_start, period_end, location_id } = params;
  const qs = new URLSearchParams({ period_start, period_end });
  if (location_id) qs.set("location_id", location_id);

  return useQuery({
    queryKey: ["pnl-report", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: PnLReport }>(`${BASE}/report?${qs}`);
      return data.data;
    },
    enabled: Boolean(period_start && period_end),
    staleTime: 60_000,
    // Backend syncs Toast every minute; auto-refetch so figures stay current.
    refetchInterval: 60_000,
  });
}

export interface DailyRevenuePoint {
  date: string;
  gross_revenue: string;
  net_revenue: string;
  void_amount: string;
  order_count: number;
}

export function useDailyBreakdown(params: {
  period_start: string;
  period_end: string;
  location_id?: string;
}) {
  const { period_start, period_end, location_id } = params;
  const qs = new URLSearchParams({ period_start, period_end });
  if (location_id) qs.set("location_id", location_id);

  return useQuery({
    queryKey: ["pnl-daily", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        data: { period_start: string; period_end: string; points: DailyRevenuePoint[] };
      }>(`${BASE}/daily-breakdown?${qs}`);
      return data.data;
    },
    enabled: Boolean(period_start && period_end),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}

export function usePnLSnapshots(params: { location_id?: string; page?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.location_id) qs.set("location_id", params.location_id);
  if (params.page) qs.set("page", String(params.page));

  return useQuery({
    queryKey: ["pnl-snapshots", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: PnLSnapshot[]; meta: { total: number } }>(
        `${BASE}/snapshots?${qs}`
      );
      return data;
    },
  });
}
