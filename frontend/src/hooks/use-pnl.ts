"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { DiscountBreakdown, PnLReport, PnLSnapshot, PnLTrend } from "@/types/pnl";

const BASE = "/api/v1/pnl";

export function useDiscountBreakdown(params: {
  period_start: string;
  period_end: string;
  location_id?: string;
}) {
  const { period_start, period_end, location_id } = params;
  const qs = new URLSearchParams({ period_start, period_end });
  if (location_id) qs.set("location_id", location_id);

  return useQuery({
    queryKey: ["pnl-discount-breakdown", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: DiscountBreakdown }>(
        `${BASE}/discount-breakdown?${qs}`
      );
      return data.data;
    },
    enabled: Boolean(period_start && period_end),
  });
}

// Trend recomputes the P&L for each month server-side, so it's slower than the
// other queries — cache it longer and don't poll it on the report's interval.
export function usePnLTrend(params: { months?: number; location_id?: string } = {}) {
  const { months = 6, location_id } = params;
  const qs = new URLSearchParams({ months: String(months) });
  if (location_id) qs.set("location_id", location_id);

  return useQuery({
    queryKey: ["pnl-trend", months, location_id],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: PnLTrend }>(`${BASE}/trend?${qs}`);
      return data.data;
    },
    staleTime: 5 * 60_000,
  });
}

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
    staleTime: 0,
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
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
    staleTime: 0,
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
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
