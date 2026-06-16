"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export interface JobRun {
  id: string;
  celery_task_id: string;
  task_name: string;
  status: "pending" | "running" | "success" | "failure" | "retry";
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: string | null;
  error_message: string | null;
  result_summary: Record<string, unknown> | null;
  created_at: string;
}

export interface JobSummary {
  total: number;
  running: number;
  success: number;
  failure: number;
  retry: number;
}

const BASE = "/api/v1/jobs";

export function useJobs(params: {
  status?: string;
  task_name?: string;
  page?: number;
  limit?: number;
} = {}) {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.task_name) qs.set("task_name", params.task_name);
  if (params.page) qs.set("page", String(params.page));
  if (params.limit) qs.set("limit", String(params.limit));

  return useQuery({
    queryKey: ["jobs", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        data: JobRun[];
        meta: { total: number; page: number; limit: number };
      }>(`${BASE}?${qs}`);
      return data;
    },
    refetchInterval: (q) => {
      const jobs = q.state.data?.data ?? [];
      return jobs.some((j) => j.status === "running" || j.status === "pending")
        ? 4000
        : 30_000;
    },
  });
}

export function useJobSummary() {
  return useQuery({
    queryKey: ["jobs-summary"],
    queryFn: async () => {
      const { data } = await apiClient.get<JobSummary>(`${BASE}/summary`);
      return data;
    },
    refetchInterval: 30_000,
  });
}
