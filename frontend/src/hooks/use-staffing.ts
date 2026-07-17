"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

const BASE = "/api/v1/staffing";
const DASH_BASE = "/api/v1/dashboard";

interface RangeParams {
  date_from: string;
  date_to: string;
  location_id?: string;
}

function rangeQS(p: RangeParams): URLSearchParams {
  const qs = new URLSearchParams({ date_from: p.date_from, date_to: p.date_to });
  if (p.location_id) qs.set("location_id", p.location_id);
  return qs;
}

export interface LaborSummary {
  connected: boolean;
  labor_cost_today?: number;
  labor_hours_today?: number;
  headcount_today?: number;
  avg_wage?: number | null;
  labor_pct_of_sales_today?: number | null;
  last_synced_at?: string | null;
}

/** Dashboard "Labor Cost" tile — today's live snapshot. */
export function useLaborSummary(location_id?: string) {
  return useQuery({
    queryKey: ["dashboard-labor-summary", location_id],
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (location_id) qs.set("location_id", location_id);
      const { data } = await apiClient.get<{ data: LaborSummary }>(
        `${DASH_BASE}/labor-summary?${qs}`
      );
      return data.data;
    },
    staleTime: 60_000,
    refetchInterval: 5 * 60_000, // labor moves slowly enough that 5min polling is plenty
  });
}

export interface StaffingSummary {
  connected: boolean;
  labor_cost?: number;
  labor_hours?: number;
  avg_wage?: number | null;
  net_revenue?: number | null;
  labor_pct_of_sales?: number | null;
  last_synced_at?: string | null;
  historical_import_complete?: boolean;
}

export function useStaffingSummary(p: RangeParams) {
  return useQuery({
    queryKey: ["staffing-summary", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: StaffingSummary }>(
        `${BASE}/summary?${rangeQS(p)}`
      );
      return data.data;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface DailyTrendPoint {
  date: string;
  cost: number;
  hours: number;
}

export function useStaffingDailyTrend(p: RangeParams) {
  return useQuery({
    queryKey: ["staffing-daily-trend", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: { series: DailyTrendPoint[] } }>(
        `${BASE}/daily-trend?${rangeQS(p)}`
      );
      return data.data.series;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface PositionBreakdown {
  position: string;
  cost: number;
  hours: number;
  pct_of_total: number | null;
}

export function useStaffingByPosition(p: RangeParams) {
  return useQuery({
    queryKey: ["staffing-by-position", p],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: { positions: PositionBreakdown[] } }>(
        `${BASE}/by-position?${rangeQS(p)}`
      );
      return data.data.positions;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface TopEmployee {
  employee_id: number;
  employee_name: string | null;
  position: string;
  cost: number;
  hours: number;
  overtime_hours: number;
}

export function useStaffingTopEmployees(p: RangeParams & { limit?: number }) {
  return useQuery({
    queryKey: ["staffing-top-employees", p],
    queryFn: async () => {
      const qs = rangeQS(p);
      if (p.limit) qs.set("limit", String(p.limit));
      const { data } = await apiClient.get<{ data: { employees: TopEmployee[] } }>(
        `${BASE}/top-employees?${qs}`
      );
      return data.data.employees;
    },
    enabled: Boolean(p.date_from && p.date_to),
    staleTime: 60_000,
  });
}

export interface TeamMember {
  employee_id: number;
  employee_name: string | null;
  position: string;
  clock_in: string | null;
  clock_out: string | null;
  is_clocked_in: boolean;
}

export function useStaffingTodayTeam() {
  return useQuery({
    queryKey: ["staffing-today-team"],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        data: { connected: boolean; business_date?: string; team: TeamMember[] };
      }>(`${BASE}/today-team`);
      return data.data;
    },
    staleTime: 30_000,
    refetchInterval: 2 * 60_000, // clock-ins change through the day; keep this fresher than the rest
  });
}

export interface StaffingSyncStatus {
  connected: boolean;
  company_name?: string | null;
  last_synced_at?: string | null;
  historical_import_complete?: boolean;
  historical_import_from?: string | null;
}

export function useStaffingSyncStatus() {
  return useQuery({
    queryKey: ["staffing-sync-status"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: StaffingSyncStatus }>(`${BASE}/sync-status`);
      return data.data;
    },
    staleTime: 30_000,
  });
}

export function useStaffingSyncNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<{ data: { status: string; rows_upserted: number } }>(
        `${BASE}/sync-now`
      );
      return data.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staffing-summary"] });
      qc.invalidateQueries({ queryKey: ["staffing-daily-trend"] });
      qc.invalidateQueries({ queryKey: ["staffing-by-position"] });
      qc.invalidateQueries({ queryKey: ["staffing-top-employees"] });
      qc.invalidateQueries({ queryKey: ["staffing-sync-status"] });
      qc.invalidateQueries({ queryKey: ["dashboard-labor-summary"] });
    },
  });
}
