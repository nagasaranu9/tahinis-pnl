"use client";

import { useMemo, useState } from "react";
import { Users, RefreshCw, Clock, TrendingUp, AlertTriangle } from "lucide-react";
import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { useLocationStore } from "@/lib/location-store";
import {
  useStaffingSummary,
  useStaffingDailyTrend,
  useStaffingByPosition,
  useStaffingTopEmployees,
  useStaffingSyncStatus,
  useStaffingSyncNow,
} from "@/hooks/use-staffing";

// ─── Date presets (same shape as the P&L page) ─────────────────────────────

type PresetKey = "today" | "yesterday" | "last7" | "last30" | "thisMonth" | "lastMonth" | "quarter" | "ytd" | "custom";

function toISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function getPreset(key: PresetKey): { start: string; end: string; label: string } {
  const now = new Date();
  const today = toISO(now);
  switch (key) {
    case "today": {
      return { start: today, end: today, label: "Today" };
    }
    case "yesterday": {
      const s = new Date(now);
      s.setDate(s.getDate() - 1);
      return { start: toISO(s), end: toISO(s), label: "Yesterday" };
    }
    case "last7": {
      const s = new Date(now);
      s.setDate(s.getDate() - 6);
      return { start: toISO(s), end: today, label: "Last 7 Days" };
    }
    case "last30": {
      const s = new Date(now);
      s.setDate(s.getDate() - 29);
      return { start: toISO(s), end: today, label: "Last 30 Days" };
    }
    case "thisMonth": {
      const s = new Date(now.getFullYear(), now.getMonth(), 1);
      return { start: toISO(s), end: today, label: "This Month" };
    }
    case "lastMonth": {
      const s = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const e = new Date(now.getFullYear(), now.getMonth(), 0);
      return { start: toISO(s), end: toISO(e), label: "Last Month" };
    }
    case "quarter": {
      const qStart = Math.floor(now.getMonth() / 3) * 3;
      const s = new Date(now.getFullYear(), qStart, 1);
      return { start: toISO(s), end: today, label: `Q${Math.floor(now.getMonth() / 3) + 1} ${now.getFullYear()}` };
    }
    case "ytd": {
      const s = new Date(now.getFullYear(), 0, 1);
      return { start: toISO(s), end: today, label: `YTD ${now.getFullYear()}` };
    }
    case "custom": {
      // Caller overrides start/end for custom — this is just a safe fallback.
      return { start: today, end: today, label: "Custom" };
    }
  }
}

const PRESETS: { key: PresetKey; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "last7", label: "7D" },
  { key: "last30", label: "30D" },
  { key: "thisMonth", label: "This Month" },
  { key: "lastMonth", label: "Last Month" },
  { key: "quarter", label: "Quarter" },
  { key: "ytd", label: "YTD" },
  { key: "custom", label: "Custom" },
];

function fmtCAD(val: number | null | undefined): string {
  if (val == null) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", minimumFractionDigits: 2 }).format(val);
}

function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "Never synced";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function KpiCard({
  label,
  value,
  sub,
  icon: Icon,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="rounded-2xl p-5 bg-card border border-border/60 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</p>
        <Icon className="h-3.5 w-3.5 text-primary" />
      </div>
      <p className="text-2xl font-bold tabular-nums tracking-tight">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
    </div>
  );
}

export default function StaffingPage() {
  const [activePreset, setActivePreset] = useState<PresetKey>("thisMonth");
  const [customStart, setCustomStart] = useState(toISO(new Date()));
  const [customEnd, setCustomEnd] = useState(toISO(new Date()));
  const locationId = useLocationStore((s) => s.selectedLocationId);
  const period = useMemo(() => {
    if (activePreset === "custom") {
      return { start: customStart, end: customEnd, label: `${customStart} → ${customEnd}` };
    }
    return getPreset(activePreset);
  }, [activePreset, customStart, customEnd]);

  const rangeParams = { date_from: period.start, date_to: period.end, location_id: locationId ?? undefined };

  const { data: summary, isLoading: summaryLoading } = useStaffingSummary(rangeParams);
  const { data: trend } = useStaffingDailyTrend(rangeParams);
  const { data: positions } = useStaffingByPosition(rangeParams);
  const { data: topEmployees } = useStaffingTopEmployees({ ...rangeParams, limit: 10 });
  const { data: syncStatus } = useStaffingSyncStatus();
  const syncNow = useStaffingSyncNow();

  const chartData = useMemo(
    () => (trend ?? []).map((p) => ({ date: p.date.slice(5), cost: p.cost })),
    [trend]
  );

  if (!summaryLoading && summary && !summary.connected) {
    return (
      <div className="p-6 max-w-2xl">
        <h1 className="text-2xl font-bold mb-2">Staffing</h1>
        <p className="text-muted-foreground">
          PushOperations isn&apos;t connected yet.{" "}
          <a href="/integrations" className="text-primary hover:underline">
            Connect it in Integrations →
          </a>
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Users className="h-5 w-5" /> Staffing
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Live labor cost from PushOperations · synced {fmtRelative(syncStatus?.last_synced_at)}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex rounded-lg border border-border overflow-hidden">
            {PRESETS.map((p) => (
              <button
                key={p.key}
                onClick={() => setActivePreset(p.key)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  activePreset === p.key ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {activePreset === "custom" && (
            <div className="flex items-center gap-1.5">
              <input
                type="date"
                value={customStart}
                max={customEnd}
                onChange={(e) => setCustomStart(e.target.value)}
                className="px-2 py-1 text-xs rounded-lg border border-border bg-background"
              />
              <span className="text-xs text-muted-foreground">→</span>
              <input
                type="date"
                value={customEnd}
                min={customStart}
                max={toISO(new Date())}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="px-2 py-1 text-xs rounded-lg border border-border bg-background"
              />
            </div>
          )}
          <button
            onClick={() => syncNow.mutate()}
            disabled={syncNow.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${syncNow.isPending ? "animate-spin" : ""}`} />
            {syncNow.isPending ? "Syncing…" : "Sync now"}
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Labor Cost" value={fmtCAD(summary?.labor_cost)} sub={period.label} icon={Users} />
        <KpiCard
          label="Labor Hours"
          value={summary?.labor_hours != null ? `${summary.labor_hours.toFixed(1)}h` : "—"}
          sub={summary?.avg_wage != null ? `avg $${summary.avg_wage.toFixed(2)}/hr` : undefined}
          icon={Clock}
        />
        <KpiCard
          label="Labor % of Sales"
          value={summary?.labor_pct_of_sales != null ? `${summary.labor_pct_of_sales}%` : "—"}
          sub={summary?.net_revenue != null ? `on ${fmtCAD(summary.net_revenue)} net revenue` : undefined}
          icon={TrendingUp}
        />
        <KpiCard
          label="Data Coverage"
          value={syncStatus?.historical_import_complete ? "Complete" : "Backfilling…"}
          sub={syncStatus?.historical_import_from ? `since ${syncStatus.historical_import_from}` : undefined}
          icon={AlertTriangle}
        />
      </div>

      {/* Trend chart */}
      <div className="rounded-2xl p-5 bg-card border border-border/60 shadow-sm">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Daily Labor Cost
        </p>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="laborGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.2} />
              <XAxis dataKey="date" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} />
              <Tooltip formatter={(v: number) => fmtCAD(v)} />
              <Area type="monotone" dataKey="cost" stroke="var(--primary)" fill="url(#laborGradient)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* By position */}
        <div className="rounded-2xl p-5 bg-card border border-border/60 shadow-sm">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
            By Position
          </p>
          <p className="text-[10px] text-muted-foreground mb-2">
            Department breakdown unavailable — grouped by position instead (Push token scope limitation).
          </p>
          <table className="w-full text-sm">
            <tbody>
              {(positions ?? []).map((p) => (
                <tr key={p.position}>
                  <td className="py-1 truncate max-w-[160px]">{p.position}</td>
                  <td className="py-1 text-right font-mono">{fmtCAD(p.cost)}</td>
                  <td className="py-1 text-right text-muted-foreground w-16">{p.hours.toFixed(0)}h</td>
                  <td className="py-1 text-right text-muted-foreground w-12">
                    {p.pct_of_total != null ? `${p.pct_of_total}%` : "—"}
                  </td>
                </tr>
              ))}
              {(!positions || positions.length === 0) && (
                <tr>
                  <td colSpan={4} className="py-4 text-center text-muted-foreground text-xs">
                    No data for this period.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Top employees */}
        <div className="rounded-2xl p-5 bg-card border border-border/60 shadow-sm">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
            Top Employees by Cost
          </p>
          <table className="w-full text-sm">
            <tbody>
              {(topEmployees ?? []).map((e, i) => (
                <tr key={e.employee_id}>
                  <td className="py-1 truncate max-w-[140px]">
                    {i + 1}. {e.employee_name ?? "Unknown"}
                  </td>
                  <td className="py-1 text-muted-foreground text-xs">{e.position}</td>
                  <td className="py-1 text-right font-mono">{fmtCAD(e.cost)}</td>
                  <td className="py-1 text-right text-muted-foreground w-14">
                    {e.overtime_hours > 0 ? (
                      <span className="text-amber-500">{e.overtime_hours.toFixed(1)}h OT</span>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
              {(!topEmployees || topEmployees.length === 0) && (
                <tr>
                  <td colSpan={4} className="py-4 text-center text-muted-foreground text-xs">
                    No data for this period.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
