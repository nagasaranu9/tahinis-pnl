"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/ai-marketing";

export interface CompetitorRow {
  place_id: string;
  name: string | null;
  address: string | null;
  rating: number | null;
  review_count: number;
  price_level: string | null;
  website: string | null;
  primary_type: string | null;
  distance_m: number | null;
  threat_score: number;
  opportunity_score: number;
}

export interface CompetitorIntel {
  available: boolean;
  reason?: string;
  location_name: string | null;
  own_rating: number | null;
  own_review_count: number;
  radius_km: number;
  competitor_count: number;
  threat_score: number;
  opportunity_score: number;
  competitors: CompetitorRow[];
  advertising_summary: string;
  promotion_summary: string;
  suggested_campaign: string;
  suggested_headlines: string[];
  estimated_monthly_opportunity: string;
  ai_confidence: number;
  ai_explanation: string;
  ai_available: boolean;
}

export function useCompetitorIntel(locationId?: string, radiusKm = 5) {
  return useQuery({
    queryKey: ["ai-marketing-competitor-intel", locationId, radiusKm],
    queryFn: async () => {
      const qs = new URLSearchParams({ radius_km: String(radiusKm) });
      if (locationId) qs.set("location_id", locationId);
      const { data } = await apiClient.get<{ data: CompetitorIntel }>(
        `${BASE}/competitor-intel?${qs}`
      );
      return data.data;
    },
    // Places + Claude calls are expensive; cache aggressively, no auto-refetch.
    staleTime: 6 * 60 * 60_000,
    refetchOnWindowFocus: false,
  });
}
