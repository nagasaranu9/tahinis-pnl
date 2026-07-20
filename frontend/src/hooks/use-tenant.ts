"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/tenants";

export type OcrProvider = "auto" | "google" | "claude";

export interface Tenant {
  id: string;
  slug: string;
  name: string;
  timezone: string;
  currency_code: string;
  plan: string;
  is_active: boolean;
  ocr_preferred_provider: OcrProvider;
}

export function useTenant() {
  return useQuery({
    queryKey: ["tenant-me"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: Tenant }>(`${BASE}/me`);
      return data.data;
    },
  });
}

export function useUpdateOcrProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ocr_preferred_provider: OcrProvider) => {
      const { data } = await apiClient.patch<{ data: Tenant }>(`${BASE}/me`, {
        ocr_preferred_provider,
      });
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenant-me"] });
    },
  });
}
