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
  peak_hour: number | null;
  peak_hour_seconds: number | null;
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

export interface ProductMix {
  items: { name: string; quantity: number; unit_price: number; share: number }[];
  total_revenue: number;
}

export function useProductMix(p: RangeParams & { limit?: number }) {
  return useQuery({
    queryKey: ["dashboard-product-mix", p],
    queryFn: async () => {
      const qs = rangeQS(p);
      if (p.limit) qs.set("limit", String(p.limit));
      const { data } = await apiClient.get<{ data: ProductMix }>(
        `${BASE}/product-mix?${qs}`
      );
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface TopVendors {
  vendors: { vendor: string; total: number; count: number; pct: number }[];
  grand_total?: number;
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

export interface DiscountsVoids {
  discounts: number;
  voids: number;
  total_loss: number;
  pct_of_sales: number;
}

export function useDiscountsVoids(p: RangeParams) {
  return useQuery({
    queryKey: ["dashboard-discounts-voids", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: DiscountsVoids }>(
        `${BASE}/discounts-voids?${rangeQS(p)}`
      );
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface InvoiceStatus {
  imported: number;
  matched: number;
  pending: number;
  unmatched: number;
  duplicate: number;
  coverage_pct: number | null;
}

export function useInvoiceStatus(p: RangeParams) {
  return useQuery({
    queryKey: ["dashboard-invoice-status", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: InvoiceStatus }>(
        `${BASE}/invoice-status?${rangeQS(p)}`
      );
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface AdsDetail {
  platform: string;
  spend: number;
  impressions: number;
  clicks: number;
  conversions: number;
  ctr: number;
  cpc: number;
  cost_per_conversion: number | null;
  roas: number | null;
  daily_spend: { date: string; spend: number }[];
}

export function useAdsDetail(p: RangeParams & { platform?: string }) {
  const qs = new URLSearchParams({ date_from: p.date_from, date_to: p.date_to });
  qs.set("platform", p.platform ?? "google_ads");
  return useQuery({
    queryKey: ["dashboard-ads-detail", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: AdsDetail }>(`${BASE}/ads-detail?${qs}`);
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 5 * 60_000,
  });
}

export interface AdsCampaign {
  campaign_id: string;
  name: string;
  status: string;
  type: string | null;
  daily_budget: number | null;
  spend: number;
  impressions: number;
  clicks: number;
  conversions: number;
  conversion_value: number;
  ctr: number;
  cpc: number;
  roas: number | null;
}

export interface AdsCampaigns {
  platform: string;
  totals: {
    spend: number;
    impressions: number;
    clicks: number;
    conversions: number;
    ctr: number;
    cpc: number;
    roas: number | null;
  };
  campaigns: AdsCampaign[];
}

export function useAdsCampaigns(p: RangeParams & { platform?: string; enabled?: boolean }) {
  const qs = new URLSearchParams({ date_from: p.date_from, date_to: p.date_to });
  qs.set("platform", p.platform ?? "google_ads");
  return useQuery({
    queryKey: ["dashboard-ads-campaigns", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: AdsCampaigns }>(`${BASE}/ads-campaigns?${qs}`);
      return data.data;
    },
    enabled: (p.enabled ?? true) && Boolean(p.date_from && p.date_to),
    staleTime: 5 * 60_000,
  });
}

export interface ReviewsDetail {
  average_rating: number | null;
  total_reviews: number;
  stars: Record<string, number>;
  new_this_month: number;
  month_avg_rating: number | null;
  response_rate_pct: number | null;
  unanswered: number;
}

export function useReviewsDetail(location_id?: string) {
  const qs = new URLSearchParams();
  if (location_id) qs.set("location_id", location_id);
  return useQuery({
    queryKey: ["dashboard-reviews-detail", location_id],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: ReviewsDetail }>(
        `${BASE}/reviews-detail?${qs}`
      );
      return data.data;
    },
    staleTime: 60 * 60_000,
    refetchInterval: 60 * 60_000,
  });
}

export interface ReviewsSentiment {
  available: boolean;
  positive_pct?: number;
  top_complaint?: string;
  top_complaint_count?: number;
  top_praise?: string;
  top_praise_count?: number;
  sample_size?: number;
}

export interface TopLineItems {
  vendor: string;
  grand_total: number;
  items: { description: string; total: number; quantity: number; count: number; pct: number }[];
}

export function useTopLineItems(p: RangeParams & { vendor?: string; limit?: number }) {
  return useQuery({
    queryKey: ["dashboard-top-line-items", p],
    queryFn: async () => {
      const qs = rangeQS(p);
      if (p.vendor) qs.set("vendor", p.vendor);
      if (p.limit) qs.set("limit", String(p.limit));
      const { data } = await apiClient.get<{ data: TopLineItems }>(
        `${BASE}/top-line-items?${qs}`
      );
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface HourPoint {
  hour: number;
  net_revenue: number;
  orders: number;
}

export function useSalesByHour(p: RangeParams) {
  return useQuery({
    queryKey: ["dashboard-sales-by-hour", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        data: { points: HourPoint[]; total_revenue: number };
      }>(`${BASE}/sales-by-hour?${rangeQS(p)}`);
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
  });
}

export interface ProfitSuggestion {
  title: string;
  detail: string;
  impact_monthly: number;
  priority: "high" | "medium" | "low";
}

export interface ProfitSuggestions {
  available: boolean;
  reason?: string;
  headline?: string;
  suggestions?: ProfitSuggestion[];
  metrics?: Record<string, number>;
}

// Server-side daily cache makes this cheap to auto-load: the first request for a
// period generates + caches; later loads serve the cached row. Pass refresh=true
// for the Regenerate button to force a new Claude pass.
export function useProfitSuggestions(p: RangeParams, enabled: boolean, refresh = false) {
  return useQuery({
    queryKey: ["dashboard-profit-suggestions", p, refresh],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: ProfitSuggestions }>(
        `${BASE}/profit-suggestions?${rangeQS(p)}${refresh ? "&refresh=true" : ""}`
      );
      return data.data;
    },
    enabled: enabled && Boolean(p.date_from && p.date_to),
    staleTime: 30 * 60_000,
  });
}

export interface ProfitSuggestionsExtra extends ProfitSuggestions {
  cached?: boolean;
}

export function useReviewsSentiment(location_id?: string) {
  const qs = new URLSearchParams();
  if (location_id) qs.set("location_id", location_id);
  return useQuery({
    queryKey: ["dashboard-reviews-sentiment", location_id],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: ReviewsSentiment }>(
        `${BASE}/reviews-sentiment?${qs}`
      );
      return data.data;
    },
    staleTime: 60 * 60_000,
    refetchInterval: 60 * 60_000,
  });
}
