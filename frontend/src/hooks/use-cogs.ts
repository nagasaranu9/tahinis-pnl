"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { CogsWeekDetail, CogsWeekSummary } from "@/types/cogs";

const BASE = "/api/v1/inventory/cogs";

export function useCogsWeeks(locationId?: string) {
  const qs = locationId ? `?location_id=${locationId}` : "";
  return useQuery({
    queryKey: ["cogs-weeks", locationId ?? null],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: CogsWeekSummary[] }>(`${BASE}${qs}`);
      return data.data;
    },
  });
}

export function useCogsWeek(id: string | null) {
  return useQuery({
    queryKey: ["cogs-week", id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: CogsWeekDetail }>(`${BASE}/${id}`);
      return data.data;
    },
  });
}

export function useUploadCogs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: {
      file: File; weekEnding: string; locationId?: string;
      purchases?: string; netSales?: string;
    }) => {
      const form = new FormData();
      form.append("file", args.file);
      form.append("week_ending", args.weekEnding);
      if (args.locationId) form.append("location_id", args.locationId);
      if (args.purchases) form.append("purchases", args.purchases);
      if (args.netSales) form.append("net_sales", args.netSales);
      const { data } = await apiClient.post<{ data: CogsWeekDetail }>(
        `${BASE}/upload`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cogs-weeks"] });
    },
  });
}

export function usePatchCogs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: { id: string; purchases?: string | null; net_sales?: string | null }) => {
      const body: Record<string, string | null> = {};
      if (args.purchases !== undefined) body.purchases = args.purchases;
      if (args.net_sales !== undefined) body.net_sales = args.net_sales;
      const { data } = await apiClient.patch<{ data: CogsWeekDetail }>(
        `${BASE}/${args.id}`, body
      );
      return data.data;
    },
    onSuccess: (_d, args) => {
      qc.invalidateQueries({ queryKey: ["cogs-weeks"] });
      qc.invalidateQueries({ queryKey: ["cogs-week", args.id] });
    },
  });
}

export function useDeleteCogs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`${BASE}/${id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cogs-weeks"] });
    },
  });
}
