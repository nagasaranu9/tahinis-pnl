"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { Document } from "@/types/document";

interface ListParams {
  page?: number;
  limit?: number;
  status?: string;
  document_type?: string;
}

export function useDocuments(params: ListParams = {}) {
  return useQuery({
    queryKey: ["documents", params],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        data: Document[];
        meta: { page: number; limit: number; total: number };
      }>("/api/v1/documents", { params });
      return data;
    },
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: ["document", id],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: Document }>(`/api/v1/documents/${id}`);
      return data.data;
    },
    enabled: !!id,
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await apiClient.post<{ data: Document }>(
        "/api/v1/documents/upload",
        form,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/api/v1/documents/${id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDeleteAllDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.delete<{ data: { deleted: number } }>("/api/v1/documents");
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useCorrectLineItem(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      lineItemId,
      description,
      quantity,
      unit_price,
      amount,
    }: {
      lineItemId: string;
      description?: string;
      quantity?: string | null;
      unit_price?: string | null;
      amount?: string;
    }) => {
      const body: Record<string, unknown> = {};
      if (description !== undefined) body.description = description;
      if (quantity !== undefined) body.quantity = quantity;
      if (unit_price !== undefined) body.unit_price = unit_price;
      if (amount !== undefined) body.amount = amount;
      const { data } = await apiClient.patch(
        `/api/v1/documents/${documentId}/line-items/${lineItemId}`,
        body
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document-line-items", documentId] });
    },
  });
}

export function useReprocessDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await apiClient.post<{ data: Document }>(
        `/api/v1/documents/${id}/reprocess`
      );
      return data.data;
    },
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["document", id] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
