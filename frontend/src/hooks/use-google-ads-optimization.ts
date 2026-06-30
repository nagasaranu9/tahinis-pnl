"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/google-ads/optimization";

export interface OptimizationRecommendation {
  id: string;
  campaign_id: string;
  recommendation_date: string;
  recommendation_type: string;
  status: string;
  entity_type: string;
  entity_id: string;
  entity_name: string | null;
  recommendation_data: Record<string, unknown>;
  metric_data: Record<string, unknown>;
  confidence_score: number | null;
  reasoning: string | null;
  executed_at: string | null;
  created_at: string;
}

export interface OptimizationAction {
  id: string;
  campaign_id: string;
  recommendation_id: string | null;
  action_type: string;
  entity_type: string;
  entity_id: string;
  status: string;
  error_message: string | null;
  request_data: Record<string, unknown>;
  response_data: Record<string, unknown> | null;
  action_date: string;
  executed_at: string | null;
  created_at: string;
}

export interface OptimizationSummary {
  total_recommendations: number;
  total_actions: number;
  actions_succeeded: number;
  actions_failed: number;
  last_run_at: string | null;
  status: "healthy" | "watch" | "alert";
}

export interface OptimizationRun {
  tenant_id: string;
  timestamp: string;
  campaigns_synced: number;
  recommendations_generated: number;
  actions_executed: number;
  errors: string[];
}

export function useOptimizationSummary() {
  return useQuery({
    queryKey: ["ga-optimization-summary"],
    queryFn: async () => {
      const { data } = await apiClient.get<OptimizationSummary>(`${BASE}/summary`);
      return data;
    },
  });
}

export function useOptimizationRecommendations(date?: string) {
  return useQuery({
    queryKey: ["ga-optimization-recommendations", date ?? "today"],
    queryFn: async () => {
      const { data } = await apiClient.get<OptimizationRecommendation[]>(
        `${BASE}/recommendations`,
        { params: date ? { date } : undefined }
      );
      return data;
    },
  });
}

export function useOptimizationActions(date?: string) {
  return useQuery({
    queryKey: ["ga-optimization-actions", date ?? "today"],
    queryFn: async () => {
      const { data } = await apiClient.get<OptimizationAction[]>(`${BASE}/actions`, {
        params: date ? { date } : undefined,
      });
      return data;
    },
  });
}

export function useRunOptimization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<OptimizationRun>(`${BASE}/run`, {});
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ga-optimization-summary"] });
      qc.invalidateQueries({ queryKey: ["ga-optimization-recommendations"] });
      qc.invalidateQueries({ queryKey: ["ga-optimization-actions"] });
    },
  });
}
