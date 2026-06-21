"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { Expense, ExpenseListResponse } from "@/types/expense";

const BASE = "/api/v1/expenses";

interface ListParams {
  location_id?: string;
  category?: string;
  vendor_name?: string;
  uncategorized_only?: boolean;
  page?: number;
  limit?: number;
}

export function useExpenses(params: ListParams = {}) {
  const qs = new URLSearchParams();
  if (params.location_id) qs.set("location_id", params.location_id);
  if (params.category) qs.set("category", params.category);
  if (params.vendor_name) qs.set("vendor_name", params.vendor_name);
  if (params.uncategorized_only) qs.set("uncategorized_only", "true");
  if (params.page) qs.set("page", String(params.page));
  if (params.limit) qs.set("limit", String(params.limit));

  const url = `${BASE}?${qs.toString()}`;

  return useQuery({
    queryKey: ["expenses", params],
    queryFn: async () => {
      const { data } = await apiClient.get<ExpenseListResponse>(url);
      return data;
    },
  });
}

export function useExpense(expenseId: string) {
  return useQuery({
    queryKey: ["expense", expenseId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: Expense }>(`${BASE}/${expenseId}`);
      return data.data;
    },
    enabled: !!expenseId,
  });
}

export function useOverrideCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ expenseId, category }: { expenseId: string; category: string }) => {
      const { data } = await apiClient.patch<{ data: Expense }>(`${BASE}/${expenseId}/category`, {
        category,
      });
      return data.data;
    },
    onSuccess: (expense) => {
      qc.invalidateQueries({ queryKey: ["expenses"] });
      qc.setQueryData(["expense", expense.id], expense);
    },
  });
}

export function useRecategorize() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (expenseId: string) => {
      const { data } = await apiClient.post<{ data: object }>(`${BASE}/${expenseId}/recategorize`);
      return data.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

export interface CreateManualExpenseInput {
  expense_date: string;
  description: string;
  amount: string;
  category?: string;
  location_id?: string;
  receipt?: File | null;
}

export function useCreateManualExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateManualExpenseInput) => {
      const form = new FormData();
      form.set("expense_date", input.expense_date);
      form.set("description", input.description);
      form.set("amount", input.amount);
      if (input.category) form.set("category", input.category);
      if (input.location_id) form.set("location_id", input.location_id);
      if (input.receipt) form.set("receipt", input.receipt);
      const { data } = await apiClient.post<{ data: Expense }>(BASE, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

export function useDeleteExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (expenseId: string) => {
      await apiClient.delete(`${BASE}/${expenseId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

export function usePurgeExpenseRange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: {
      start: string;
      end: string;
      locationId?: string;
      includeOverridden?: boolean;
    }) => {
      const qs = new URLSearchParams({ start: params.start, end: params.end });
      if (params.locationId) qs.set("location_id", params.locationId);
      if (params.includeOverridden) qs.set("include_overridden", "true");
      const { data } = await apiClient.post<{ data: { deleted: number } }>(
        `${BASE}/purge-range?${qs.toString()}`
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["expenses"] });
      qc.invalidateQueries({ queryKey: ["pnl"] });
    },
  });
}
