"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export type StatusState = "active" | "down" | "disabled";

export interface SystemStatusItem {
  key: string;
  label: string;
  group: "core" | "platform" | "delivery";
  state: StatusState;
  detail: string;
}

export interface SystemStatus {
  generated_at: string;
  items: SystemStatusItem[];
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system-status"],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: SystemStatus }>("/api/v1/health/status");
      return data.data;
    },
  });
}
