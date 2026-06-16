"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { AIInsight, InsightType } from "@/types/ai-insight";

const BASE = "/api/v1/ai/insights";

export function useAIInsights(params: {
  insight_type?: InsightType;
  include_dismissed?: boolean;
  page?: number;
} = {}) {
  const qs = new URLSearchParams();
  if (params.insight_type) qs.set("insight_type", params.insight_type);
  if (params.include_dismissed) qs.set("include_dismissed", "true");
  if (params.page) qs.set("page", String(params.page));

  return useQuery({
    queryKey: ["ai-insights", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: AIInsight[]; meta: { total: number } }>(
        `${BASE}?${qs}`
      );
      return data;
    },
  });
}

export function useGenerateInsight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      insight_type: InsightType;
      period_start: string;
      period_end: string;
      location_id?: string;
    }) => {
      const { data } = await apiClient.post(`${BASE}/generate`, body);
      return data;
    },
    onSuccess: () => {
      // Invalidate after short delay to allow Celery task to complete
      setTimeout(() => qc.invalidateQueries({ queryKey: ["ai-insights"] }), 3000);
    },
  });
}

export function useDismissInsight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (insightId: string) => {
      const { data } = await apiClient.post<{ data: AIInsight }>(
        `${BASE}/${insightId}/dismiss`,
        {}
      );
      return data.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-insights"] }),
  });
}

export function useInsightFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ insightId, isHelpful }: { insightId: string; isHelpful: boolean }) => {
      const { data } = await apiClient.post<{ data: AIInsight }>(
        `${BASE}/${insightId}/feedback`,
        { is_helpful: isHelpful }
      );
      return data.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-insights"] }),
  });
}
