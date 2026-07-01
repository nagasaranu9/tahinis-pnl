"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GoogleReview, GoogleReviewConfig, ReviewsSummary } from "@/types/google-reviews";

const BASE = "/api/v1/reviews";

export function useReviewsStatus() {
  return useQuery({
    queryKey: ["reviews-status"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: GoogleReviewConfig[] }>(`${BASE}/status`);
      return data.data;
    },
  });
}

export function useReviewsAuthUrl() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.get<{ data: { url: string } }>(`${BASE}/auth-url`);
      return data.data.url;
    },
    onSuccess: (url) => {
      window.location.href = url;
    },
  });
}

export function useReviewsSummary(locationId?: string, dateRange?: { from?: string; to?: string }) {
  return useQuery({
    queryKey: ["reviews-summary", locationId, dateRange],
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (locationId) qs.set("location_id", locationId);
      if (dateRange?.from) qs.set("date_from", dateRange.from);
      if (dateRange?.to) qs.set("date_to", dateRange.to);
      const query = qs.toString() ? `?${qs}` : "";
      const { data } = await apiClient.get<{ data: ReviewsSummary }>(`${BASE}/summary${query}`);
      return data.data;
    },
    staleTime: 60 * 60_000,
    refetchInterval: 60 * 60_000,
  });
}

export const useReviewsDetail = useReviewsSummary;

export function useReviewsList(
  locationId?: string,
  page = 1,
  limit = 20,
  dateRange?: { from?: string; to?: string }
) {
  return useQuery({
    queryKey: ["reviews-list", locationId, page, limit, dateRange],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), limit: String(limit) });
      if (locationId) params.set("location_id", locationId);
      if (dateRange?.from) params.set("date_from", dateRange.from);
      if (dateRange?.to) params.set("date_to", dateRange.to);
      const { data } = await apiClient.get<{ data: GoogleReview[]; meta: { total: number } }>(
        `${BASE}/list?${params}`
      );
      return data;
    },
    staleTime: 60 * 60_000,
    refetchInterval: 60 * 60_000,
  });
}

export function useReviewsSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (locationId?: string) => {
      const params = locationId ? `?location_id=${locationId}` : "";
      const { data } = await apiClient.post<{ data: { queued: number } }>(`${BASE}/sync${params}`);
      return data.data;
    },
    onSuccess: () => {
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["reviews-summary"] });
        qc.invalidateQueries({ queryKey: ["reviews-list"] });
        qc.invalidateQueries({ queryKey: ["reviews-status"] });
      }, 3000);
    },
  });
}

export function useSetReviewLocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      location_id: string;
      account_name: string;
      location_name: string;
    }) => {
      const { data } = await apiClient.patch<{ data: GoogleReviewConfig }>(
        `${BASE}/config/location`,
        body
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviews-status"] });
    },
  });
}

export function useDiscoverReviewLocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (locationId?: string) => {
      const params = locationId ? `?location_id=${locationId}` : "";
      const { data } = await apiClient.post<{
        data: {
          account_name?: string;
          location_name?: string;
          error?: string;
          candidates?: { account_name: string; location_name: string; title: string | null }[];
        };
      }>(`${BASE}/discover-location${params}`);
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviews-status"] });
    },
  });
}

export function usePlacesSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { locationId?: string; placeId?: string; query?: string }) => {
      const qs = new URLSearchParams();
      if (params.locationId) qs.set("location_id", params.locationId);
      if (params.placeId) qs.set("place_id", params.placeId);
      if (params.query) qs.set("query", params.query);
      const { data } = await apiClient.post<{
        data: {
          place_id?: string;
          rating?: number;
          total_review_count?: number;
          imported?: number;
          error?: string;
        };
      }>(`${BASE}/places-sync?${qs.toString()}`);
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviews-summary"] });
      qc.invalidateQueries({ queryKey: ["reviews-list"] });
      qc.invalidateQueries({ queryKey: ["reviews-status"] });
      qc.invalidateQueries({ queryKey: ["dashboard-reviews-detail"] });
      qc.invalidateQueries({ queryKey: ["dashboard-reviews-sentiment"] });
    },
  });
}

export function useReviewsDisconnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (configId: string) => {
      await apiClient.delete(`${BASE}/disconnect?config_id=${configId}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviews-status"] });
      qc.invalidateQueries({ queryKey: ["reviews-summary"] });
    },
  });
}
