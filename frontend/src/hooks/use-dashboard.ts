"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/dashboard";

interface RangeParams {
  date_from: string;
  date_to: string;
  location_id?: string;
}

function rangeQS(p: RangeParams): URLSearchParams {
  const qs = new URLSearchParams({ date_from: p.date_from, date_to: p.date_to });
  if (p.location_id) qs.set("location_id", p.location_id);
  return qs;
}

export interface ChannelMix {
  total_revenue: number;
  channels: { channel: string; revenue: number; order_count: number; pct: number }[];
}

export function useChannelMix(p: RangeParams) {
  return useQuery({
    queryKey: ["dashboard-channel-mix", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: ChannelMix }>(
        `${BASE}/channel-mix?${rangeQS(p)}`
      );
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface Fulfillment {
  avg_seconds: number | null;
  target_seconds: number;
  fastest_seconds: number | null;
  slowest_seconds: number | null;
  sample_size: number;
  by_channel: { channel: string; avg_seconds: number | null; order_count: number }[];
}

export function useFulfillment(p: RangeParams) {
  return useQuery({
    queryKey: ["dashboard-fulfillment", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: Fulfillment }>(
        `${BASE}/fulfillment?${rangeQS(p)}`
      );
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface TopVendors {
  vendors: { vendor: string; total: number; count: number }[];
}

export function useTopVendors(p: RangeParams & { category?: string; limit?: number }) {
  const qs = rangeQS(p);
  if (p.category) qs.set("category", p.category);
  if (p.limit) qs.set("limit", String(p.limit));
  return useQuery({
    queryKey: ["dashboard-top-vendors", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: TopVendors }>(`${BASE}/top-vendors?${qs}`);
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface CashForecast {
  horizon_days: number;
  projected_net_flow: number;
  avg_daily_sales: number;
  avg_daily_expense: number;
  lookback_days: number;
  basis: string;
}

export function useCashForecast(location_id?: string) {
  const qs = new URLSearchParams();
  if (location_id) qs.set("location_id", location_id);
  return useQuery({
    queryKey: ["dashboard-cash-forecast", location_id],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: CashForecast }>(
        `${BASE}/cash-forecast?${qs}`
      );
      return data.data;
    },
    staleTime: 5 * 60_000,
  });
}
