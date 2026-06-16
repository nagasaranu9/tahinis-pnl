"use client";

import { useMemo, useState, useCallback } from "react";
import Link from "next/link";
import {
  TrendingUp,
  DollarSign,
  GitMerge,
  Bot,
  AlertTriangle,
  ArrowRight,
  Loader2,
  RefreshCw,
  ShoppingCart,
  Users,
  Calendar,
  ChevronDown,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { usePnLReport, useDailyBreakdown } from "@/hooks/use-pnl";
import { useReconciliationFlags } from "@/hooks/use-reconciliation";
import { useAIInsights } from "@/hooks/use-ai-insights";
import { useLocationStore } from "@/lib/location-store";
import { useQueryClient } from "@tanstack/react-query";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtCAD(val: string | number | null | undefined): string {
  if (val == null) return "—";
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 0,
  }).format(n);
}

function fmtPct(val: string | number | null | undefined): string {
  if (val == null) return "—";
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return "—";
  return `${n.toFixed(1)}%`;
}

function pctColor(val: string | null | undefined, thresholds: { warn: number; bad: number }): string {
  if (val == null) return "text-muted-foreground";
  const n = parseFloat(val);
  if (isNaN(n)) return "text-muted-foreground";
  if (n >= thresholds.bad) return "text-red-500";
  if (n >= thresholds.warn) return "text-yellow-500";
  return "text-green-500";
}

function profitColor(val: string | null | undefined): string {
  if (val == null) return "text-muted-foreground";
  const n = parseFloat(val);
  if (isNaN(n)) return "text-muted-foreground";
  if (n < 0) return "text-red-500";
  if (n < 5) return "text-yellow-500";
  return "text-green-500";
}

// ─── Period-over-period delta ─────────────────────────────────────────────────

interface Delta {
  pct: number;
  dir: "up" | "down" | "flat";
}

function calcDelta(
  current: string | number | null | undefined,
  prev: string | number | null | undefined
): Delta | null {
  if (current == null || prev == null) return null;
  const c = typeof current === "string" ? parseFloat(current) : current;
  const p = typeof prev === "string" ? parseFloat(prev) : prev;
  if (isNaN(c) || isNaN(p) || p === 0) return null;
  const pct = ((c - p) / Math.abs(p)) * 100;
  return { pct, dir: pct > 0.5 ? "up" : pct < -0.5 ? "down" : "flat" };
}

function DeltaBadge({ delta, invert = false }: { delta: Delta | null; invert?: boolean }) {
  if (!delta || delta.dir === "flat") return null;
  const isGood = invert ? delta.dir === "down" : delta.dir === "up";
  const color = isGood ? "text-green-500" : "text-red-500";
  const arrow = delta.dir === "up" ? "▲" : "▼";
  return (
    <span className={`text-xs font-semibold ${color} tabular-nums`}>
      {arrow} {Math.abs(delta.pct).toFixed(1)}%
    </span>
  );
}

// ─── Date Range ───────────────────────────────────────────────────────────────

type PresetKey =
  | "today"
  | "yesterday"
  | "last7"
  | "last30"
  | "thisMonth"
  | "lastMonth"
  | "quarter"
  | "ytd"
  | "custom";

interface DateRange {
  start: string;
  end: string;
  label: string;
}

function toISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function businessDate(d: Date): string {
  if (d.getHours() < 4) {
    const prev = new Date(d);
    prev.setDate(prev.getDate() - 1);
    return toISO(prev);
  }
  return toISO(d);
}

/**
 * Returns the immediately preceding period of the same duration.
 * Uses 3-arg Date constructor throughout to avoid UTC parse bugs.
 */
function getPrevPeriod(start: string, end: string): { start: string; end: string } {
  const [sy, sm, sd] = start.split("-").map(Number);
  const [ey, em, ed] = end.split("-").map(Number);
  const startDate = new Date(sy, sm - 1, sd);
  const endDate = new Date(ey, em - 1, ed);
  const days = Math.round((endDate.getTime() - startDate.getTime()) / 86400000) + 1;
  // prevEnd = day before current start; prevStart = prevEnd minus (days-1)
  const prevEnd = new Date(sy, sm - 1, sd - 1);
  const prevStart = new Date(sy, sm - 1, sd - days);
  return { start: toISO(prevStart), end: toISO(prevEnd) };
}

function getPreset(key: PresetKey): DateRange {
  const now = new Date();
  const today = businessDate(now);

  switch (key) {
    case "today":
      return { start: today, end: today, label: "Today" };
    case "yesterday": {
      const [ty, tm, td] = today.split("-").map(Number);
      const todayBiz = new Date(ty, tm - 1, td);
      todayBiz.setDate(todayBiz.getDate() - 1);
      const d = toISO(todayBiz);
      return { start: d, end: d, label: "Yesterday" };
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
      return {
        start: toISO(s),
        end: today,
        label: `${now.toLocaleString("en-CA", { month: "long" })} ${now.getFullYear()}`,
      };
    }
    case "lastMonth": {
      const s = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const e = new Date(now.getFullYear(), now.getMonth(), 0);
      return {
        start: toISO(s),
        end: toISO(e),
        label: `${s.toLocaleString("en-CA", { month: "long" })} ${s.getFullYear()}`,
      };
    }
    case "quarter": {
      const qStart = Math.floor(now.getMonth() / 3) * 3;
      const s = new Date(now.getFullYear(), qStart, 1);
      return {
        start: toISO(s),
        end: today,
        label: `Q${Math.floor(now.getMonth() / 3) + 1} ${now.getFullYear()}`,
      };
    }
    case "ytd": {
      const s = new Date(now.getFullYear(), 0, 1);
      return { start: toISO(s), end: today, label: `YTD ${now.getFullYear()}` };
    }
    default:
      return { start: today, end: today, label: "Custom" };
  }
}

const PRESETS: { key: PresetKey; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "last7", label: "Last 7 Days" },
  { key: "last30", label: "Last 30 Days" },
  { key: "thisMonth", label: "This Month" },
  { key: "lastMonth", label: "Last Month" },
  { key: "quarter", label: "This Quarter" },
  { key: "ytd", label: "Year to Date" },
  { key: "custom", label: "Custom Range" },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function HeroStatCard({
  title,
  value,
  delta,
  sub,
  icon: Icon,
  href,
  loading,
  valueClass = "text-foreground",
  accentColor = "border-t-primary",
  invertDelta = false,
}: {
  title: string;
  value: string;
  delta?: Delta | null;
  sub?: string;
  icon: React.ComponentType<{ className?: string }>;
  href?: string;
  loading?: boolean;
  valueClass?: string;
  accentColor?: string;
  invertDelta?: boolean;
}) {
  const inner = (
    <div
      className={`border border-border border-t-2 ${accentColor} rounded-lg p-5 bg-card hover:border-primary/30 transition-colors group`}
    >
      <div className="flex items-start justify-between mb-4">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
        <div className="h-8 w-8 rounded-md bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
          <Icon className="h-4 w-4 text-primary" />
        </div>
      </div>
      {loading ? (
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      ) : (
        <>
          <p className={`text-3xl font-bold tabular-nums ${valueClass}`}>{value}</p>
          <div className="flex items-center gap-2 mt-1.5">
            {delta && <DeltaBadge delta={delta} invert={invertDelta} />}
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
        </>
      )}
    </div>
  );
  return href ? (
    <Link href={href} className="block cursor-pointer">
      {inner}
    </Link>
  ) : (
    inner
  );
}

function CompactStatCard({
  title,
  value,
  delta,
  sub,
  icon: Icon,
  href,
  loading,
  valueClass = "text-foreground",
  invertDelta = false,
}: {
  title: string;
  value: string;
  delta?: Delta | null;
  sub?: string;
  icon: React.ComponentType<{ className?: string }>;
  href?: string;
  loading?: boolean;
  valueClass?: string;
  invertDelta?: boolean;
}) {
  const inner = (
    <div className="border border-border rounded-lg p-4 bg-card hover:border-primary/30 transition-colors group">
      <div className="flex items-start justify-between mb-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
        <div className="h-6 w-6 rounded-md bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
          <Icon className="h-3 w-3 text-primary" />
        </div>
      </div>
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      ) : (
        <>
          <p className={`text-xl font-bold tabular-nums ${valueClass}`}>{value}</p>
          <div className="flex items-center gap-2 mt-1">
            {delta && <DeltaBadge delta={delta} invert={invertDelta} />}
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
        </>
      )}
    </div>
  );
  return href ? (
    <Link href={href} className="block cursor-pointer">
      {inner}
    </Link>
  ) : (
    inner
  );
}

function SectionCard({
  title,
  href,
  linkLabel,
  children,
  loading,
}: {
  title: string;
  href?: string;
  linkLabel?: string;
  children: React.ReactNode;
  loading?: boolean;
}) {
  return (
    <div className="border border-border rounded-lg bg-card overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold">{title}</h2>
        {href && linkLabel && (
          <Link href={href} className="text-xs text-primary flex items-center gap-1 hover:underline cursor-pointer">
            {linkLabel} <ArrowRight className="h-3 w-3" />
          </Link>
        )}
      </div>
      <div className="p-5">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { selectedLocationId } = useLocationStore();
  const qc = useQueryClient();

  const [activePreset, setActivePreset] = useState<PresetKey>("today");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [showDateMenu, setShowDateMenu] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [showNetSeries, setShowNetSeries] = useState(true);

  const dateRange = useMemo<DateRange>(() => {
    if (activePreset === "custom" && customStart && customEnd) {
      return { start: customStart, end: customEnd, label: `${customStart} → ${customEnd}` };
    }
    if (activePreset === "custom") return getPreset("thisMonth");
    return getPreset(activePreset);
  }, [activePreset, customStart, customEnd]);

  const prevPeriod = useMemo(
    () => getPrevPeriod(dateRange.start, dateRange.end),
    [dateRange.start, dateRange.end]
  );

  const locationParam = selectedLocationId ?? undefined;

  const { data: pnl, isLoading: pnlLoading } = usePnLReport({
    period_start: dateRange.start,
    period_end: dateRange.end,
    location_id: locationParam,
  });

  // Previous period — parallel fetch for PoP deltas
  const { data: prevPnl } = usePnLReport({
    period_start: prevPeriod.start,
    period_end: prevPeriod.end,
    location_id: locationParam,
  });

  const { data: daily, isLoading: dailyLoading } = useDailyBreakdown({
    period_start: dateRange.start,
    period_end: dateRange.end,
    location_id: locationParam,
  });

  const { data: flags, isLoading: flagsLoading } = useReconciliationFlags({ unresolved_only: true });
  const { data: allFlags } = useReconciliationFlags({ unresolved_only: false });
  const { data: insights, isLoading: insightsLoading } = useAIInsights({ include_dismissed: false });

  const li = pnl?.line_items;
  const prevLi = prevPnl?.line_items;

  const totalImported = allFlags?.meta?.total ?? 0;
  const unresolved = flags?.meta?.total ?? 0;
  const matched = totalImported - unresolved;

  const totalVoids = useMemo(
    () => (daily?.points ?? []).reduce((s, p) => s + parseFloat(p.void_amount ?? "0"), 0),
    [daily]
  );

  const orderCount = pnl?.order_count ?? 0;
  const avgCheck =
    orderCount > 0 && li?.gross_revenue ? parseFloat(li.gross_revenue) / orderCount : null;

  const prevOrderCount = prevPnl?.order_count ?? 0;
  const prevAvgCheck =
    prevOrderCount > 0 && prevLi?.gross_revenue
      ? parseFloat(prevLi.gross_revenue) / prevOrderCount
      : null;

  // PoP deltas — suppressed for "Today" (partial day vs full day = misleading)
  const suppressDelta = activePreset === "today";
  const grossDelta = suppressDelta ? null : calcDelta(li?.gross_revenue, prevLi?.gross_revenue);
  const netDelta = suppressDelta ? null : calcDelta(li?.net_revenue, prevLi?.net_revenue);
  const profitDelta = suppressDelta ? null : calcDelta(li?.net_profit, prevLi?.net_profit);
  const cogsDelta = suppressDelta ? null : calcDelta(li?.cogs_pct, prevLi?.cogs_pct);
  const laborDelta = suppressDelta ? null : calcDelta(li?.labor_pct, prevLi?.labor_pct);
  const primeDelta = suppressDelta ? null : calcDelta(li?.prime_cost_pct, prevLi?.prime_cost_pct);
  const avgCheckDelta = suppressDelta ? null : calcDelta(avgCheck, prevAvgCheck);

  const handleRefresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["pnl-report"] });
    qc.invalidateQueries({ queryKey: ["pnl-daily"] });
    qc.invalidateQueries({ queryKey: ["reconciliation-flags"] });
    qc.invalidateQueries({ queryKey: ["ai-insights"] });
  }, [qc]);

  const chartData = useMemo(() => {
    if (!daily?.points?.length) return [];
    return daily.points.map((p) => ({
      date: p.date.slice(5), // MM-DD
      gross: parseFloat(p.gross_revenue),
      net: parseFloat(p.net_revenue),
      orders: p.order_count,
    }));
  }, [daily]);

  // Bar chart for ≤3 data points (1–3 day ranges); area chart for ≥4
  const useBarChart = chartData.length <= 3;

  return (
    <div className="space-y-5 max-w-7xl">
      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Financial overview — {dateRange.label}
            <span className="ml-2 text-xs opacity-50">vs prior period</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Date Range Picker — styled as primary control */}
          <div className="relative">
            <button
              onClick={() => {
                setShowDateMenu(!showDateMenu);
                setShowCustom(false);
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-md bg-primary/10 border border-primary/25 text-sm font-semibold text-primary hover:bg-primary/15 transition-colors cursor-pointer"
            >
              <Calendar className="h-3.5 w-3.5" />
              {dateRange.label}
              <ChevronDown className="h-3.5 w-3.5 opacity-70" />
            </button>
            {showDateMenu && (
              <div className="absolute right-0 top-full mt-1 w-52 rounded-md border border-border bg-card shadow-lg z-50 py-1">
                {PRESETS.map((p) => (
                  <button
                    key={p.key}
                    onClick={() => {
                      if (p.key === "custom") {
                        setShowCustom(true);
                      } else {
                        setActivePreset(p.key);
                        setShowDateMenu(false);
                        setShowCustom(false);
                      }
                    }}
                    className={`w-full text-left px-4 py-2 text-sm hover:bg-accent transition-colors cursor-pointer ${
                      activePreset === p.key ? "text-primary font-medium" : "text-foreground"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
                {showCustom && (
                  <div className="px-4 py-3 border-t border-border space-y-2">
                    <input
                      type="date"
                      value={customStart}
                      onChange={(e) => setCustomStart(e.target.value)}
                      className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                    />
                    <input
                      type="date"
                      value={customEnd}
                      onChange={(e) => setCustomEnd(e.target.value)}
                      className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                    />
                    <button
                      onClick={() => {
                        if (customStart && customEnd) {
                          setActivePreset("custom");
                          setShowDateMenu(false);
                          setShowCustom(false);
                        }
                      }}
                      className="w-full rounded bg-primary text-primary-foreground text-xs py-1.5 font-medium hover:opacity-90 transition-opacity cursor-pointer"
                    >
                      Apply
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Refresh — icon-only */}
          <button
            onClick={handleRefresh}
            className="p-2 rounded-md border border-border bg-card text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors cursor-pointer"
            title="Refresh data"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* ── Row 1: Hero KPIs (3 primary metrics) ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <HeroStatCard
          title="Gross Revenue"
          value={fmtCAD(li?.gross_revenue)}
          delta={grossDelta}
          sub={dateRange.label}
          icon={TrendingUp}
          href="/pnl"
          loading={pnlLoading}
          valueClass="text-primary"
          accentColor="border-t-primary"
        />
        <HeroStatCard
          title="Net Revenue"
          value={fmtCAD(li?.net_revenue)}
          delta={netDelta}
          sub={li?.total_discounts ? `Disc. ${fmtCAD(li.total_discounts)}` : undefined}
          icon={DollarSign}
          href="/pnl"
          loading={pnlLoading}
          accentColor="border-t-purple-500"
        />
        <HeroStatCard
          title="Net Profit"
          value={fmtCAD(li?.net_profit)}
          delta={profitDelta}
          sub={li?.net_profit_pct ? `${fmtPct(li.net_profit_pct)} margin` : undefined}
          icon={TrendingUp}
          href="/pnl"
          loading={pnlLoading}
          valueClass={profitColor(li?.net_profit_pct)}
          accentColor="border-t-green-500"
        />
      </div>

      {/* ── Row 2: Secondary KPIs (operational metrics) ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <CompactStatCard
          title="Food Cost %"
          value={fmtPct(li?.cogs_pct)}
          delta={cogsDelta}
          sub={li?.cogs ? fmtCAD(li.cogs) : undefined}
          icon={ShoppingCart}
          href="/expenses"
          loading={pnlLoading}
          valueClass={pctColor(li?.cogs_pct, { warn: 30, bad: 38 })}
          invertDelta
        />
        <CompactStatCard
          title="Labor %"
          value={fmtPct(li?.labor_pct)}
          delta={laborDelta}
          sub={li?.labor_cost ? fmtCAD(li.labor_cost) : undefined}
          icon={Users}
          href="/expenses"
          loading={pnlLoading}
          valueClass={pctColor(li?.labor_pct, { warn: 30, bad: 35 })}
          invertDelta
        />
        <CompactStatCard
          title="Prime Cost %"
          value={fmtPct(li?.prime_cost_pct)}
          delta={primeDelta}
          sub="Target < 60%"
          icon={GitMerge}
          href="/pnl"
          loading={pnlLoading}
          valueClass={pctColor(li?.prime_cost_pct, { warn: 60, bad: 68 })}
          invertDelta
        />
        <CompactStatCard
          title="Avg Check"
          value={fmtCAD(avgCheck)}
          delta={avgCheckDelta}
          sub={orderCount > 0 ? `${orderCount.toLocaleString("en-CA")} orders` : undefined}
          icon={DollarSign}
          loading={pnlLoading}
        />
      </div>

      {/* ── Row 3: Chart (2/3) + Action Required (1/3) ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Revenue Chart */}
        <div className="border border-border rounded-lg bg-card overflow-hidden lg:col-span-2">
          <div className="px-5 py-3.5 border-b border-border flex items-center justify-between flex-wrap gap-2">
            <h2 className="text-sm font-semibold">Daily Revenue — {dateRange.label}</h2>
            <div className="flex items-center gap-4">
              {/* Net Revenue toggle */}
              <button
                onClick={() => setShowNetSeries(!showNetSeries)}
                className={`flex items-center gap-1.5 text-xs font-medium transition-colors cursor-pointer ${
                  showNetSeries ? "text-purple-400" : "text-muted-foreground"
                }`}
              >
                <span
                  className={`inline-block w-4 h-0.5 rounded ${
                    showNetSeries ? "bg-purple-400" : "bg-muted-foreground/40"
                  }`}
                  style={showNetSeries ? { borderTop: "1px dashed #a855f7", background: "none" } : {}}
                />
                Net Revenue
              </button>
              {dailyLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
            </div>
          </div>
          <div className="p-5">
            {chartData.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 gap-2 text-sm text-muted-foreground">
                <TrendingUp className="h-8 w-8 opacity-20" />
                <p>No sales data for this period.</p>
                <Link href="/integrations/toast" className="text-xs text-primary hover:underline cursor-pointer">
                  Connect Toast POS to see daily revenue →
                </Link>
              </div>
            ) : useBarChart ? (
              // Bar chart for 1–3 day ranges (area with 1 dot is meaningless)
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => v >= 1000 ? `$${(v / 1000).toFixed(0)}k` : `$${v}`}
                    width={48}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "6px",
                      fontSize: "12px",
                    }}
                    formatter={(value: number, name: string) => [
                      fmtCAD(value),
                      name === "gross" ? "Gross Revenue" : "Net Revenue",
                    ]}
                    labelStyle={{ color: "hsl(var(--foreground))", fontWeight: 600 }}
                  />
                  <Bar dataKey="gross" radius={[4, 4, 0, 0]} maxBarSize={80}>
                    {chartData.map((_, i) => (
                      <Cell key={i} fill="hsl(var(--primary))" fillOpacity={0.85} />
                    ))}
                  </Bar>
                  {showNetSeries && (
                    <Bar dataKey="net" radius={[4, 4, 0, 0]} maxBarSize={80}>
                      {chartData.map((_, i) => (
                        <Cell key={i} fill="#a855f7" fillOpacity={0.6} />
                      ))}
                    </Bar>
                  )}
                </BarChart>
              </ResponsiveContainer>
            ) : (
              // Area chart for ≥4 day ranges
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="grossGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="netGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#a855f7" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) =>
                      v >= 1000 ? `$${(v / 1000).toFixed(0)}k` : `$${v}`
                    }
                    width={48}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "6px",
                      fontSize: "12px",
                    }}
                    formatter={(value: number, name: string) => [
                      fmtCAD(value),
                      name === "gross" ? "Gross Revenue" : "Net Revenue",
                    ]}
                    labelStyle={{ color: "hsl(var(--foreground))", fontWeight: 600 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="gross"
                    stroke="hsl(var(--primary))"
                    strokeWidth={2}
                    fill="url(#grossGrad)"
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                  {showNetSeries && (
                    <Area
                      type="monotone"
                      dataKey="net"
                      stroke="#a855f7"
                      strokeWidth={1.5}
                      strokeDasharray="4 2"
                      fill="url(#netGrad)"
                      dot={false}
                      activeDot={{ r: 3 }}
                    />
                  )}
                </AreaChart>
              </ResponsiveContainer>
            )}
            {chartData.length > 0 && (
              <div className="flex items-center gap-5 mt-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-4 h-0.5 bg-primary rounded" />
                  Gross
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-4 border-t-[1.5px] border-dashed border-purple-400" />
                  Net
                </span>
                <span className="ml-auto opacity-50">gap = discounts + voids</span>
              </div>
            )}
          </div>
        </div>

        {/* Action Required Panel */}
        <div className="border border-border rounded-lg bg-card overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold">Action Required</h2>
            {unresolved > 0 && (
              <span className="text-xs font-bold bg-red-500/10 text-red-500 px-2 py-0.5 rounded-full">
                {unresolved}
              </span>
            )}
          </div>
          <div className="divide-y divide-border">
            {/* Reconciliation */}
            <div className="px-5 py-4 flex items-start gap-3">
              {flagsLoading ? (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-0.5 shrink-0" />
              ) : unresolved > 0 ? (
                <XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
              ) : (
                <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
              )}
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {unresolved > 0
                    ? `${unresolved} reconciliation flag${unresolved !== 1 ? "s" : ""}`
                    : "Reconciliation clear"}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {matched} matched · {totalImported} imported
                </p>
                {unresolved > 0 && (
                  <Link
                    href="/reconciliation"
                    className="text-xs text-red-400 hover:underline mt-1 block font-medium cursor-pointer"
                  >
                    Review flags →
                  </Link>
                )}
              </div>
            </div>

            {/* Voids alert — only shown when voids exist */}
            {totalVoids > 0 && (
              <div className="px-5 py-4 flex items-start gap-3">
                <AlertTriangle className="h-4 w-4 text-yellow-500 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-foreground">Voids detected</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {fmtCAD(totalVoids)} voided this period
                  </p>
                </div>
              </div>
            )}

            {/* AI Insights */}
            <div className="px-5 py-4 flex items-start gap-3">
              <Bot className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {insightsLoading
                    ? "Loading…"
                    : `${insights?.meta?.total ?? 0} AI insight${(insights?.meta?.total ?? 0) !== 1 ? "s" : ""}`}
                </p>
                {(insights?.data?.length ?? 0) > 0 && (
                  <p className="text-xs text-muted-foreground mt-0.5 leading-snug line-clamp-2">
                    {insights?.data?.[0]?.summary}
                  </p>
                )}
                <Link href="/insights" className="text-xs text-primary hover:underline mt-1 block cursor-pointer">
                  View all →
                </Link>
              </div>
            </div>

            {/* Toast sync status */}
            <div className="px-5 py-4 flex items-start gap-3">
              <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-foreground">Toast POS synced</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {orderCount} orders this period
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Row 4: P&L Summary + AI Insights ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SectionCard title="P&L Summary" href="/pnl" linkLabel="Full report" loading={pnlLoading}>
          <div className="space-y-2 text-sm font-mono">
            {[
              { label: "Gross Revenue", val: li?.gross_revenue },
              { label: "Total Discounts", val: li?.total_discounts, neg: true },
              { label: "Voids", val: totalVoids > 0 ? String(totalVoids) : null, neg: true },
              { label: "Net Revenue", val: li?.net_revenue, bold: true },
              { label: "COGS", val: li?.cogs, neg: true },
              { label: "Labor Cost", val: li?.labor_cost, neg: true },
              { label: "Operating Expenses", val: li?.operating_expenses, neg: true },
            ].map(({ label, val, neg, bold }) => (
              <div
                key={label}
                className={`flex justify-between gap-4 ${
                  bold ? "font-bold border-t border-border pt-2 mt-1" : ""
                }`}
              >
                <span className={bold ? "text-foreground" : "text-muted-foreground"}>{label}</span>
                <span className={neg ? "text-red-400" : "text-foreground"}>
                  {neg && val && parseFloat(val as string) > 0
                    ? `(${fmtCAD(val)})`
                    : fmtCAD(val)}
                </span>
              </div>
            ))}
            <div className="flex justify-between gap-4 font-bold border-t-2 border-border pt-2 mt-1">
              <span>Net Profit</span>
              <span className={profitColor(li?.net_profit_pct)}>{fmtCAD(li?.net_profit)}</span>
            </div>
            {/* Banner: no expense data = P&L incomplete */}
            {!li?.cogs && !li?.labor_cost && !pnlLoading && (
              <div className="mt-3 flex items-start gap-2 rounded-md bg-yellow-500/10 border border-yellow-500/20 px-3 py-2.5">
                <AlertTriangle className="h-3.5 w-3.5 text-yellow-500 shrink-0 mt-0.5" />
                <div className="text-xs text-yellow-600 dark:text-yellow-400">
                  <span className="font-semibold">No expense data.</span>{" "}
                  COGS and Labor show as zero — P&L is incomplete.{" "}
                  <Link href="/documents" className="underline hover:no-underline">
                    Upload invoices →
                  </Link>
                </div>
              </div>
            )}
            {/* Banner: no bank statement on file = unreconciled P&L */}
            {!pnlLoading && pnl && !pnl.bank_statement_verified && (
              <div className="mt-3 flex items-start gap-2 rounded-md bg-red-500/10 border border-red-500/20 px-3 py-2.5">
                <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0 mt-0.5" />
                <div className="text-xs text-red-600 dark:text-red-400">
                  <span className="font-semibold">No bank statement for this period.</span>{" "}
                  This P&L is unreconciled and may not be accurate.{" "}
                  <Link href="/documents" className="underline hover:no-underline">
                    Upload bank statement →
                  </Link>
                </div>
              </div>
            )}
          </div>
        </SectionCard>

        <SectionCard
          title="AI Insights"
          href="/insights"
          linkLabel={`View all (${insightsLoading ? "…" : insights?.meta?.total ?? 0})`}
          loading={insightsLoading}
        >
          {!insights?.data?.length ? (
            <div className="flex flex-col items-center justify-center gap-2 text-muted-foreground py-6">
              <Bot className="h-8 w-8 opacity-20" />
              <p className="text-sm">No insights yet.</p>
              <Link href="/insights" className="text-xs text-primary hover:underline cursor-pointer">
                Generate insights →
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {insights.data.slice(0, 4).map((insight) => (
                <div key={insight.id} className="flex gap-2.5">
                  <Bot className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm text-foreground leading-snug">{insight.summary}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Confidence:{" "}
                      {insight.confidence_score != null
                        ? `${(parseFloat(String(insight.confidence_score)) * 100).toFixed(0)}%`
                        : "—"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── Row 5: Expense Categories + Toast POS ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SectionCard title="Expense Categories" href="/expenses" linkLabel="All expenses" loading={pnlLoading}>
          {!pnl?.expense_breakdown?.length ? (
            <p className="text-sm text-muted-foreground">No expenses recorded.</p>
          ) : (
            <div className="space-y-3">
              {[...pnl.expense_breakdown]
                .sort((a, b) => parseFloat(String(b.total)) - parseFloat(String(a.total)))
                .slice(0, 6)
                .map((cat) => {
                  const total = parseFloat(String(cat.total));
                  const netRev = li?.net_revenue ? parseFloat(String(li.net_revenue)) : 0;
                  const pct = netRev > 0 ? (total / netRev) * 100 : 0;
                  return (
                    <div key={cat.category} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">{cat.category}</span>
                        <span className="font-mono font-medium text-foreground">{fmtCAD(total)}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full bg-primary/60 rounded-full transition-all"
                          style={{ width: `${Math.min(pct, 100).toFixed(1)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </SectionCard>

        {/* Toast POS — only show rows with actual data */}
        <SectionCard title="Toast POS" href="/integrations/toast" linkLabel="Configure">
          <div className="space-y-2 text-sm">
            {(
              [
                {
                  label: "Transactions",
                  value: orderCount > 0 ? orderCount.toLocaleString("en-CA") : null,
                },
                { label: "Avg Check", value: avgCheck != null ? fmtCAD(avgCheck) : null },
                {
                  label: "Discounts",
                  value: li?.total_discounts ? fmtCAD(li.total_discounts) : null,
                },
                { label: "Voids", value: totalVoids > 0 ? fmtCAD(totalVoids) : null },
              ] as { label: string; value: string | null }[]
            )
              .filter((row) => row.value !== null)
              .map(({ label, value }) => (
                <div key={label} className="flex justify-between items-center">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="font-mono font-medium text-foreground">{value}</span>
                </div>
              ))}
            {orderCount === 0 && (
              <p className="text-sm text-muted-foreground">No transactions in this period.</p>
            )}
            <div className="pt-2 border-t border-border">
              <span className="text-xs text-green-500 font-medium flex items-center gap-1.5">
                <CheckCircle2 className="h-3 w-3" /> Toast sync active
              </span>
            </div>
          </div>
        </SectionCard>
      </div>

      {/* ── Reconciliation — full-width stat boxes ── */}
      <SectionCard
        title="Reconciliation"
        href="/reconciliation"
        linkLabel="Review flags"
        loading={flagsLoading}
      >
        <div className="grid grid-cols-3 gap-4 text-center">
          {[
            { label: "Invoices Imported", value: totalImported, accent: false },
            { label: "Matched", value: matched, accent: false },
            { label: "Unmatched / Flags", value: unresolved, accent: unresolved > 0 },
          ].map(({ label, value, accent }) => (
            <div key={label}>
              <p
                className={`text-2xl font-bold tabular-nums ${
                  accent ? "text-red-400" : "text-foreground"
                }`}
              >
                {value}
              </p>
              <p className="text-xs text-muted-foreground mt-1">{label}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-3 border-t border-border">
          {unresolved === 0 ? (
            <p className="text-xs text-green-500 font-medium">All clear — no flags to review.</p>
          ) : (
            <Link
              href="/reconciliation"
              className="text-xs text-red-400 font-medium hover:underline cursor-pointer"
            >
              {unresolved} flag{unresolved !== 1 ? "s" : ""} need review →
            </Link>
          )}
        </div>
      </SectionCard>

      {/* ── Connect Integrations Strip (replaces empty Google cards) ── */}
      <div className="border border-dashed border-border rounded-lg px-5 py-4 flex flex-wrap items-center gap-x-6 gap-y-2">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider shrink-0">
          Connect:
        </span>
        <Link
          href="/integrations"
          className="text-xs text-primary hover:underline font-medium cursor-pointer"
        >
          + Google Business Profile (Reviews &amp; Ratings)
        </Link>
        <Link
          href="/integrations"
          className="text-xs text-primary hover:underline font-medium cursor-pointer"
        >
          + Google Ads (Campaign Spend &amp; ROAS)
        </Link>
      </div>

      {/* Click-away to close date menu */}
      {showDateMenu && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => {
            setShowDateMenu(false);
            setShowCustom(false);
          }}
        />
      )}
    </div>
  );
}
