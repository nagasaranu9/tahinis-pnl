"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type {
  GoogleAdsSummary,
  GoogleReviewSnapshot,
} from "@/types/external-platform";

const BASE = "/api/v1/external";

interface AdConnectorStatus {
  connected: boolean;
  account_id: string | null;
}

function useAdConnectorStatus(provider: "google-ads" | "meta-ads") {
  return useQuery({
    queryKey: ["ad-connector-status", provider],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: AdConnectorStatus }>(`${BASE}/${provider}/status`);
      return data.data;
    },
  });
}

export function useGoogleAdsStatus() {
  return useAdConnectorStatus("google-ads");
}

export function useMetaAdsStatus() {
  return useAdConnectorStatus("meta-ads");
}

export function useGoogleAdsConnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { customer_id: string; developer_token: string; refresh_token: string }) => {
      const { data } = await apiClient.post<{ data: AdConnectorStatus }>(`${BASE}/google-ads/connect`, body);
      return data.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ad-connector-status", "google-ads"] }),
  });
}

export function useMetaAdsConnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { ad_account_id: string; access_token: string }) => {
      const { data } = await apiClient.post<{ data: AdConnectorStatus }>(`${BASE}/meta-ads/connect`, body);
      return data.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ad-connector-status", "meta-ads"] }),
  });
}

export function useGoogleAdsDisconnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiClient.delete(`${BASE}/google-ads/disconnect`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ad-connector-status", "google-ads"] }),
  });
}

export function useMetaAdsDisconnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiClient.delete(`${BASE}/meta-ads/disconnect`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ad-connector-status", "meta-ads"] }),
  });
}

export function useReviewSnapshots(params: {
  start_date?: string;
  end_date?: string;
  location_id?: string;
  page?: number;
} = {}) {
  const qs = new URLSearchParams();
  if (params.start_date) qs.set("start_date", params.start_date);
  if (params.end_date) qs.set("end_date", params.end_date);
  if (params.location_id) qs.set("location_id", params.location_id);
  if (params.page) qs.set("page", String(params.page));

  return useQuery({
    queryKey: ["review-snapshots", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        data: GoogleReviewSnapshot[];
        meta: { total: number };
      }>(`${BASE}/reviews/snapshots?${qs}`);
      return data;
    },
  });
}

export function useAdsSummary(params: {
  start_date: string;
  end_date: string;
  location_id?: string;
}) {
  const qs = new URLSearchParams({
    start_date: params.start_date,
    end_date: params.end_date,
  });
  if (params.location_id) qs.set("location_id", params.location_id);

  return useQuery({
    queryKey: ["ads-summary", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: GoogleAdsSummary }>(
        `${BASE}/ads/summary?${qs}`
      );
      return data.data;
    },
    enabled: Boolean(params.start_date && params.end_date),
  });
}
