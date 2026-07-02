"use client";

import { useMemo, useState, useCallback } from "react";
import Link from "next/link";
import {
  TrendingUp,
  DollarSign,
  Loader2,
  RefreshCw,
  ShoppingCart,
  Users,
  Calendar,
  ChevronDown,
  Star,
  Megaphone,
  FileCheck2,
  Wallet,
  Bell,
  Timer,
  UtensilsCrossed,
  Flame,
  CheckCircle2,
  Scissors,
  Truck,
  Sparkles,
} from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { usePnLReport, useDailyBreakdown } from "@/hooks/use-pnl";
import { useReconciliationFlags } from "@/hooks/use-reconciliation";
import { usePlatformMetrics } from "@/hooks/use-pipeboard";
import {
  useChannelMix,
  useFulfillment,
  useTopVendors,
  useCashForecast,
  useDiscountsVoids,
  useInvoiceStatus,
  useAdsDetail,
  useReviewsDetail,
  useReviewsSentiment,
  useProfitSuggestions,
  useTopLineItems,
  useProductMix,
  useSalesByHour,
} from "@/hooks/use-dashboard";
import { useReviewsList } from "@/hooks/use-reviews";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { useLocations } from "@/hooks/use-locations";
import { useLocationStore } from "@/lib/location-store";
import { useQueryClient } from "@tanstack/react-query";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtCAD(val: string | number | null | undefined, dp = 0): string {
  if (val == null) return "—";
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: dp,
  }).format(n);
}

function fmtPct(val: string | number | null | undefined): string {
  if (val == null) return "—";
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return "—";
  return `${n.toFixed(1)}%`;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function pctColor(val: string | number | null | undefined, t: { warn: number; bad: number }): string {
  if (val == null) return "text-muted-foreground";
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return "text-muted-foreground";
  if (n >= t.bad) return "text-red-500";
  if (n >= t.warn) return "text-yellow-500";
  return "text-green-500";
}

function profitColor(val: string | number | null | undefined): string {
  if (val == null) return "text-muted-foreground";
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return "text-muted-foreground";
  if (n < 0) return "text-red-500";
  return "text-green-500";
}

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

function DeltaText({ delta, invert = false }: { delta: Delta | null; invert?: boolean }) {
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

// ─── Date range ───────────────────────────────────────────────────────────────

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

function getPrevPeriod(start: string, end: string): { start: string; end: string } {
  const [sy, sm, sd] = start.split("-").map(Number);
  const [ey, em, ed] = end.split("-").map(Number);
  const startDate = new Date(sy, sm - 1, sd);
  const endDate = new Date(ey, em - 1, ed);
  const days = Math.round((endDate.getTime() - startDate.getTime()) / 86400000) + 1;
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
      const b = new Date(ty, tm - 1, td);
      b.setDate(b.getDate() - 1);
      const d = toISO(b);
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

// ─── Tile primitives ──────────────────────────────────────────────────────────

function Tile({
  children,
  href,
  className = "",
}: {
  children: React.ReactNode;
  href?: string;
  className?: string;
}) {
  const inner = (
    <div
      className={`rounded-2xl p-5 bg-card border border-border/60 shadow-sm ${href ? "hover:shadow-md hover:-translate-y-0.5" : ""} transition-all duration-200 h-full ${className}`}
    >
      {children}
    </div>
  );
  return href ? (
    <Link href={href} className="block cursor-pointer h-full">
      {inner}
    </Link>
  ) : (
    inner
  );
}

function TileHeader({
  label,
  icon: Icon,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex items-center justify-between mb-2">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</p>
      <Icon className="h-3.5 w-3.5 text-primary" />
    </div>
  );
}

function ComingSoon({ note }: { note?: string }) {
  return (
    <div className="mt-1">
      <span className="inline-block text-[10px] font-semibold uppercase tracking-wide bg-muted text-muted-foreground px-2 py-0.5 rounded">
        Coming soon
      </span>
      {note && <p className="text-xs text-muted-foreground mt-1.5 leading-snug">{note}</p>}
    </div>
  );
}

function RowLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold text-muted-foreground/70 uppercase tracking-[0.08em] mb-3">
      {children}
    </p>
  );
}

function Sparkline({ data, color = "#185FA5" }: { data: number[]; color?: string }) {
  if (!data.length) return null;
  const series = data.map((v, i) => ({ i, v }));
  return (
    <div className="h-8 w-full mt-1">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} fill="url(#spark)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

const CHANNEL_COLORS = ["#378ADD", "#7F77DD", "#1D9E75", "#EF9F27", "#D85A30", "#D4537E"];

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { selectedLocationId } = useLocationStore();
  const { locations } = useLocations();
  const qc = useQueryClient();

  const [activePreset, setActivePreset] = useState<PresetKey>("today");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [showDateMenu, setShowDateMenu] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

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
  const location = locations.find((l) => l.id === selectedLocationId);
  const storeId = location?.store_id ?? location?.toast_location_id ?? null;

  const rangeArgs = { date_from: dateRange.start, date_to: dateRange.end, location_id: locationParam };

  const { data: pnl, isLoading: pnlLoading } = usePnLReport({
    period_start: dateRange.start,
    period_end: dateRange.end,
    location_id: locationParam,
  });
  const { data: prevPnl } = usePnLReport({
    period_start: prevPeriod.start,
    period_end: prevPeriod.end,
    location_id: locationParam,
  });

  const thisMonth = useMemo(() => getPreset("thisMonth"), []);
  const lastMonth = useMemo(() => getPreset("lastMonth"), []);
  const { data: mtdPnl } = usePnLReport({
    period_start: thisMonth.start,
    period_end: thisMonth.end,
    location_id: locationParam,
  });
  const { data: lastMonthPnl } = usePnLReport({
    period_start: lastMonth.start,
    period_end: lastMonth.end,
    location_id: locationParam,
  });

  // 7-day sales sparkline
  const last7 = useMemo(() => getPreset("last7"), []);
  const { data: daily7 } = useDailyBreakdown({
    period_start: last7.start,
    period_end: last7.end,
    location_id: locationParam,
  });

  // Operational
  const { data: channelMix, isLoading: channelLoading } = useChannelMix(rangeArgs);
  const { data: discVoids } = useDiscountsVoids(rangeArgs);
  const { data: fulfillment, isLoading: fulfillmentLoading } = useFulfillment(rangeArgs);
  const { data: productMix } = useProductMix({ ...rangeArgs, limit: 6 });
  const { data: topFood } = useTopVendors({ ...rangeArgs, category: "Food Cost", limit: 5 });
  const { data: alexItems } = useTopLineItems({ ...rangeArgs, vendor: "alex food", limit: 5 });
  const { data: forecast } = useCashForecast(locationParam);
  const { data: invoiceStatus } = useInvoiceStatus(rangeArgs);

  // Marketing + reviews
  const { data: platformMetrics = [] } = usePlatformMetrics();
  // Ad spend is daily-sparse; a single-day range (e.g. "Yesterday") usually has
  // no row. Show ads over a trailing 30-day window ending at the selected end.
  const adsArgs = useMemo(() => {
    const end = new Date(`${dateRange.end}T00:00:00`);
    const start = new Date(end);
    start.setDate(start.getDate() - 29);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    return { date_from: iso(start), date_to: dateRange.end, location_id: locationParam };
  }, [dateRange.end, locationParam]);
  const { data: googleAds } = useAdsDetail({ ...adsArgs, platform: "google_ads" });
  const { data: reviewsDetail } = useReviewsDetail(locationParam);
  const { data: sentiment } = useReviewsSentiment(locationParam);
  const { data: recentReviews } = useReviewsList(locationParam, 1, 2);
  const { data: flags } = useReconciliationFlags({ unresolved_only: true });

  // AI net-profit suggestions — auto-loaded (server caches daily, so this is
  // ~1 Claude call/day/period). Regenerate forces a fresh pass.
  const [refreshSuggestions, setRefreshSuggestions] = useState(false);
  const { data: profitSuggestions, isFetching: suggestionsLoading } = useProfitSuggestions(
    rangeArgs,
    true,
    refreshSuggestions
  );

  // Intraday sales shape
  const { data: salesByHour } = useSalesByHour(rangeArgs);

  const li = pnl?.line_items;
  const prevLi = prevPnl?.line_items;

  const orderCount = pnl?.order_count ?? 0;
  const avgCheck =
    orderCount > 0 && li?.gross_revenue ? parseFloat(li.gross_revenue) / orderCount : null;
  const prevOrderCount = prevPnl?.order_count ?? 0;
  const prevAvgCheck =
    prevOrderCount > 0 && prevLi?.gross_revenue
      ? parseFloat(prevLi.gross_revenue) / prevOrderCount
      : null;

  // Net sales delta — show even on Today (vs yesterday) per spec
  const netDelta = calcDelta(li?.net_revenue, prevLi?.net_revenue);
  const avgCheckDelta = calcDelta(avgCheck, prevAvgCheck);

  const dineInPct = useMemo(() => {
    const c = channelMix?.channels.find((x) => /dine/i.test(x.channel));
    return c?.pct ?? null;
  }, [channelMix]);

  // MTD projection + pace
  const mtdNet = mtdPnl?.line_items?.net_revenue ? parseFloat(mtdPnl.line_items.net_revenue) : null;
  const projection = useMemo(() => {
    if (mtdNet == null) return null;
    const now = new Date();
    const dayOfMonth = now.getDate();
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    if (dayOfMonth === 0) return null;
    return (mtdNet / dayOfMonth) * daysInMonth;
  }, [mtdNet]);
  const pace = useMemo(() => {
    const lastTotal = lastMonthPnl?.line_items?.net_revenue
      ? parseFloat(lastMonthPnl.line_items.net_revenue)
      : null;
    if (mtdNet == null || lastTotal == null || lastTotal === 0) return null;
    const now = new Date();
    const dayOfMonth = now.getDate();
    const daysInLast = new Date(now.getFullYear(), now.getMonth(), 0).getDate();
    const expected = lastTotal * (dayOfMonth / daysInLast);
    return expected === 0 ? null : Math.round((mtdNet / expected) * 100);
  }, [mtdNet, lastMonthPnl]);

  // Net profit vs last month
  const netProfit = li?.net_profit ? parseFloat(li.net_profit) : null;
  // Costs (COGS/labor/opex) come from monthly invoices, not per-day. On a short
  // range (e.g. "Today") they're often zero, making net_profit == net_sales,
  // which misreads as 100% margin. Detect that and flag it instead.
  const totalCosts =
    (li?.cogs ? parseFloat(li.cogs) : 0) +
    (li?.labor_cost ? parseFloat(li.labor_cost) : 0) +
    (li?.operating_expenses ? parseFloat(li.operating_expenses) : 0);
  const profitNoCosts = netProfit != null && totalCosts === 0;
  const lastMonthProfit = lastMonthPnl?.line_items?.net_profit
    ? parseFloat(lastMonthPnl.line_items.net_profit)
    : null;
  const profitBetterBy =
    netProfit != null && lastMonthProfit != null ? netProfit - lastMonthProfit : null;
  const salesSpark = useMemo(
    () => (daily7?.points ?? []).map((p) => parseFloat(p.net_revenue)),
    [daily7]
  );

  // Food cost
  const foodPct = li?.cogs_pct ? parseFloat(li.cogs_pct) : null;
  const FOOD_TARGET = 36;
  const foodOverPp = foodPct != null ? foodPct - FOOD_TARGET : null;
  const monthlyRev = mtdNet ?? (li?.net_revenue ? parseFloat(li.net_revenue) : null);
  const foodOverCost =
    foodOverPp != null && foodOverPp > 0 && monthlyRev != null
      ? (foodOverPp / 100) * monthlyRev
      : null;

  // Ads (fall back to platform-metrics roas if ads-detail empty)
  const gaRoas = googleAds?.roas ?? platformMetrics.find((m) => /google/i.test(m.platform))?.roas ?? null;

  const unresolved = flags?.meta?.total ?? 0;

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      // refetchType "all" also refetches inactive/background queries, not just mounted ones
      await qc.invalidateQueries({ refetchType: "all" });
    } finally {
      setRefreshing(false);
    }
  }, [qc]);

  const greeting = useMemo(() => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 18) return "Good afternoon";
    return "Good evening";
  }, []);

  const starPct = (n: number) =>
    reviewsDetail && reviewsDetail.total_reviews > 0
      ? (n / reviewsDetail.total_reviews) * 100
      : 0;

  return (
    <div className="space-y-8 max-w-7xl mx-auto px-3 sm:px-4 overflow-x-hidden pb-4">
      {/* ── Header ── */}
      <div className="sticky top-0 z-30 -mx-3 sm:-mx-4 px-3 sm:px-4 py-3 bg-background/80 backdrop-blur-md flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-red-500/10 flex items-center justify-center">
            <Flame className="h-5 w-5 text-red-500" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">
              {greeting} <span aria-hidden>👋</span>
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
              <CheckCircle2 className="h-3 w-3 text-green-500" />
              Tahini&apos;s {storeId ? `#${storeId}` : ""}{location?.name ? ` · ${location.name}` : ""} · Synced · {dateRange.label}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
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
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="p-2 rounded-md border border-border bg-card text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* ── Row 1: Hero ── */}
      <div>
        <RowLabel>Hero metrics</RowLabel>
        <div className="flex gap-3 overflow-x-auto snap-x snap-mandatory pb-1 -mx-3 px-3 sm:mx-0 sm:px-0 sm:grid sm:grid-cols-2 lg:grid-cols-4 sm:overflow-visible [&>*]:snap-start [&>*]:shrink-0 [&>*]:min-w-[78%] sm:[&>*]:min-w-0 [&>*]:w-full [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <Tile href="/pnl">
            <TileHeader label="Net Sales" icon={TrendingUp} />
            <p className="text-3xl font-bold tabular-nums tracking-tight text-primary">
              {pnlLoading ? "…" : <AnimatedNumber value={li?.net_revenue != null ? parseFloat(li.net_revenue) : null} format={(n) => fmtCAD(n, 2)} />}
            </p>
            <div className="mt-1 flex items-center gap-1.5"><DeltaText delta={netDelta} /><span className="text-xs text-muted-foreground">vs prior</span></div>
            <p className="text-xs text-muted-foreground">{plural(orderCount, "order")}{dineInPct != null ? ` · Dine-in ${dineInPct.toFixed(0)}%` : ""}</p>
            {salesSpark.length > 1 && <Sparkline data={salesSpark} color="#185FA5" />}
          </Tile>
          <Tile href="/pnl">
            <TileHeader label="MTD Sales" icon={DollarSign} />
            <p className="text-3xl font-bold tabular-nums tracking-tight"><AnimatedNumber value={mtdNet} format={(n) => fmtCAD(n)} /></p>
            <div className="mt-1 flex items-center gap-1.5">
              {pace != null && (
                <span className={`text-xs font-semibold ${pace >= 100 ? "text-green-500" : pace >= 85 ? "text-yellow-500" : "text-red-500"}`}>
                  {pace}% pace
                </span>
              )}
              <span className="text-xs text-muted-foreground">{projection != null ? `${fmtCAD(projection)} est.` : "—"}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {pace != null ? (pace >= 100 ? "Ahead of last month" : "Behind last month") : " "}
            </p>
          </Tile>
          <Tile href="/pnl">
            <TileHeader label="Prime Cost" icon={ShoppingCart} />
            <p className={`text-3xl font-bold tabular-nums tracking-tight ${pctColor(li?.prime_cost_pct, { warn: 60, bad: 62 })}`}>{fmtPct(li?.prime_cost_pct)}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {li?.prime_cost_pct != null
                ? parseFloat(li.prime_cost_pct) < 60 ? "Under 60% target" : "Over 60% target"
                : "Target < 60%"}
            </p>
          </Tile>
          <Tile href="/pnl">
            <TileHeader label="Net Profit" icon={TrendingUp} />
            <p className={`text-3xl font-bold tabular-nums tracking-tight ${profitNoCosts ? "text-muted-foreground" : profitColor(netProfit)}`}><AnimatedNumber value={netProfit} format={(n) => fmtCAD(n, 2)} /></p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {profitNoCosts
                ? "Awaiting cost data"
                : profitBetterBy != null
                ? `${profitBetterBy >= 0 ? "▲ Better" : "▼ Worse"} ${fmtCAD(Math.abs(profitBetterBy))} vs ${lastMonth.label}`
                : `${li?.net_profit_pct ? fmtPct(li.net_profit_pct) + " margin" : ""}`}
            </p>
            {salesSpark.length > 1 && <Sparkline data={salesSpark} color={netProfit != null && netProfit < 0 ? "#ef4444" : "#22c55e"} />}
          </Tile>
        </div>
      </div>

      {/* ── Sales Overview (intraday) ── */}
      {salesByHour && salesByHour.points.some((p) => p.net_revenue > 0) && (
        <div>
          <RowLabel>Sales Overview</RowLabel>
          <Tile>
            <div className="flex items-baseline justify-between">
              <TileHeader label="Net Sales by Hour" icon={TrendingUp} />
              <span className="text-sm font-bold tabular-nums">{fmtCAD(salesByHour.total_revenue)}</span>
            </div>
            <div className="h-56 mt-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={salesByHour.points} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <defs>
                    <linearGradient id="salesHourFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#185FA5" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#185FA5" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border" vertical={false} />
                  <XAxis
                    dataKey="hour"
                    tickFormatter={(h: number) => (h === 0 ? "12a" : h < 12 ? `${h}a` : h === 12 ? "12p" : `${h - 12}p`)}
                    interval={2}
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    className="text-muted-foreground"
                  />
                  <YAxis tick={{ fontSize: 11 }} stroke="currentColor" className="text-muted-foreground" width={48} tickFormatter={(v: number) => `$${v >= 1000 ? (v / 1000).toFixed(1) + "k" : v}`} />
                  <Tooltip
                    formatter={(v: number) => [fmtCAD(v, 2), "Net sales"]}
                    labelFormatter={(h: number) => `${h}:00`}
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  />
                  <Area type="monotone" dataKey="net_revenue" stroke="#185FA5" strokeWidth={2} fill="url(#salesHourFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Tile>
        </div>
      )}

      {/* ── Row 2: Toast POS ── */}
      <div>
        <RowLabel>Toast POS</RowLabel>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <Tile className="lg:col-span-1">
            <TileHeader label="Revenue by Channel" icon={ShoppingCart} />
            {channelLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : !channelMix?.channels?.length ? (
              <p className="text-sm text-muted-foreground">No orders in this period.</p>
            ) : (
              <>
              <table className="w-full text-xs mt-1">
                <tbody>
                  {channelMix.channels.slice(0, 6).map((c, i) => (
                    <tr key={c.channel}>
                      <td className="py-0.5">
                        <span className="inline-block w-2 h-2 rounded-sm mr-1.5" style={{ background: CHANNEL_COLORS[i % CHANNEL_COLORS.length] }} />
                        {c.channel}
                      </td>
                      <td className="py-0.5 text-right font-mono pr-4 border-r border-border">{fmtCAD(c.revenue, 2)}</td>
                      <td className="py-0.5 text-right text-muted-foreground pl-4 w-12">{c.pct}%</td>
                    </tr>
                  ))}
                  <tr className="border-t border-border font-medium">
                    <td className="pt-1">Total</td>
                    <td className="pt-1 text-right font-mono pr-4 border-r border-border">{fmtCAD(channelMix.total_revenue, 2)}</td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
              </>
            )}
          </Tile>
          <Tile>
            <TileHeader label="Avg Check Size" icon={DollarSign} />
            <p className="text-3xl font-bold tabular-nums tracking-tight">{fmtCAD(avgCheck, 2)}</p>
            <div className="mt-1 flex items-center gap-1.5"><DeltaText delta={avgCheckDelta} />{prevAvgCheck != null && <span className="text-xs text-muted-foreground">vs {fmtCAD(prevAvgCheck, 2)}</span>}</div>
          </Tile>
          <Tile>
            <TileHeader label="Discounts & Voids" icon={Scissors} />
            {discVoids ? (
              <>
                <div className="text-xs space-y-0.5 mt-1">
                  <div className="flex justify-between"><span className="text-muted-foreground">Discounts</span><span className="text-red-400">-{fmtCAD(discVoids.discounts, 2)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Voids</span><span className="text-red-400">-{fmtCAD(discVoids.voids, 2)}</span></div>
                  <div className="flex justify-between font-medium border-t border-border pt-0.5"><span>Total loss</span><span className="text-red-500">-{fmtCAD(discVoids.total_loss, 2)}</span></div>
                </div>
                <p className={`text-xs mt-1 ${discVoids.pct_of_sales > 3 ? "text-red-500" : "text-muted-foreground"}`}>{discVoids.pct_of_sales}% of sales</p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">—</p>
            )}
          </Tile>
        </div>
      </div>

      {/* ── Operations: Fulfillment + Product Mix (below Toast POS) ── */}
      <div>
        <RowLabel>Operations</RowLabel>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <Tile>
            <TileHeader label="Avg Fulfillment Time" icon={Timer} />
            {fulfillmentLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : !fulfillment || fulfillment.avg_seconds == null ? (
              <>
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1">No timed orders in this period (needs Toast open/close timestamps).</p>
              </>
            ) : (
              <>
                <p className="text-3xl font-bold tabular-nums">{fmtDuration(fulfillment.avg_seconds)}</p>
                <p className="text-xs mt-1">
                  Target {fmtDuration(fulfillment.target_seconds)} ·{" "}
                  {fulfillment.avg_seconds <= fulfillment.target_seconds ? (
                    <span className="text-green-500 font-medium">{fmtDuration(fulfillment.target_seconds - fulfillment.avg_seconds)} faster</span>
                  ) : (
                    <span className="text-red-500 font-medium">{fmtDuration(fulfillment.avg_seconds - fulfillment.target_seconds)} slower</span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground mt-2">
                  {fulfillment.peak_hour != null && `Peak ${fulfillment.peak_hour}:00 ${fmtDuration(fulfillment.peak_hour_seconds)} · `}
                  fastest {fmtDuration(fulfillment.fastest_seconds)} · slowest {fmtDuration(fulfillment.slowest_seconds)}
                </p>
                <p className="text-xs text-muted-foreground">{plural(fulfillment.sample_size, "order")}</p>
                <div className="mt-3 space-y-1.5 border-t border-border pt-2">
                  {fulfillment.by_channel.filter((c) => (c.avg_seconds ?? 0) > 0).map((c) => (
                    <div key={c.channel} className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{c.channel}</span>
                      <span className="font-mono font-medium text-foreground">{fmtDuration(c.avg_seconds)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Tile>
          <Tile>
            <TileHeader label="Top Product Mix" icon={UtensilsCrossed} />
            {!productMix?.items?.length ? (
              <>
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1">No Toast item sales in this period.</p>
              </>
            ) : (
              <>
                <table className="w-full text-xs mt-1">
                  <tbody>
                    {productMix.items.map((it, i) => (
                      <tr key={it.name}>
                        <td className="py-0.5 truncate max-w-[180px]" title={it.name}>{i + 1}. {it.name}</td>
                        <td className="py-0.5 text-right text-muted-foreground">{plural(Math.round(it.quantity), "order")}</td>
                        <td className="py-0.5 text-right text-muted-foreground w-10">{Math.round(it.share * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[10px] text-muted-foreground mt-1.5">From Toast · {fmtCAD(productMix.total_revenue)} item sales</p>
              </>
            )}
          </Tile>
        </div>
      </div>

      {/* ── Row 3: Food & Labor ── */}
      <div>
        <RowLabel>Food &amp; labor</RowLabel>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <Tile href="/expenses">
            <TileHeader label="Food Cost" icon={ShoppingCart} />
            <p className={`text-3xl font-bold tabular-nums tracking-tight ${pctColor(foodPct, { warn: 38, bad: 40 })}`}>{fmtPct(foodPct)}</p>
            <p className="text-xs text-muted-foreground mt-1">
              Target {FOOD_TARGET}% ·{" "}
              {foodOverPp != null && foodOverPp > 0
                ? `over by ${foodOverPp.toFixed(1)}pp`
                : foodOverPp != null
                ? `${Math.abs(foodOverPp).toFixed(1)}pp under`
                : "—"}
            </p>
            {foodOverCost != null && <p className="text-xs text-red-400">Costing ~{fmtCAD(foodOverCost)}/mo</p>}
          </Tile>
          <Tile>
            {alexItems?.items?.length ? (
              <>
                <TileHeader label="Alex Food — Top Items" icon={Truck} />
                <table className="w-full text-xs mt-1">
                  <tbody>
                    {alexItems.items.slice(0, 5).map((it, i) => (
                      <tr key={it.description}>
                        <td className="py-0.5 truncate max-w-[150px]" title={it.description}>{i + 1}. {it.description}</td>
                        <td className="py-0.5 text-right font-mono">{fmtCAD(it.total)}</td>
                        <td className="py-0.5 text-right text-muted-foreground w-8">{it.pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[10px] text-muted-foreground mt-1.5">From Alex Food invoices · {fmtCAD(alexItems.grand_total)} total</p>
              </>
            ) : (
              <>
                <TileHeader label="Top Suppliers (Food)" icon={Truck} />
                {!topFood?.vendors?.length ? (
                  <p className="text-sm text-muted-foreground">No supplier spend yet.</p>
                ) : (
                  <table className="w-full text-xs mt-1">
                    <tbody>
                      {topFood.vendors.slice(0, 5).map((v, i) => (
                        <tr key={v.vendor}>
                          <td className="py-0.5 truncate max-w-[140px]">{i + 1}. {v.vendor}</td>
                          <td className="py-0.5 text-right font-mono">{fmtCAD(v.total)}</td>
                          <td className="py-0.5 text-right text-muted-foreground w-8">{v.pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <p className="text-[10px] text-muted-foreground mt-1.5">Per-product breakdown shows once Alex Food invoices are OCR&apos;d.</p>
              </>
            )}
          </Tile>
          <Tile>
            <TileHeader label="Labor Cost" icon={Users} />
            <p className="text-3xl font-bold tabular-nums tracking-tight text-muted-foreground">—</p>
            <ComingSoon note="Hours, headcount & avg wage land once PushOperations is live." />
          </Tile>
        </div>
      </div>

      {/* ── Row 4: Reviews & Ads ── */}
      <div>
        <RowLabel>Reviews &amp; ads</RowLabel>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <Tile href="/reviews">
            <TileHeader label="Google Reviews" icon={Star} />
            {reviewsDetail?.average_rating != null ? (
              <>
                <p className="text-3xl font-bold tabular-nums tracking-tight text-yellow-500">{reviewsDetail.average_rating.toFixed(1)} ★ <span className="text-xs text-muted-foreground">· {reviewsDetail.total_reviews.toLocaleString("en-CA")}</span></p>
                <p className="text-xs text-muted-foreground mt-1">
                  +{reviewsDetail.new_this_month} new · {reviewsDetail.response_rate_pct ?? 0}% responded · {reviewsDetail.unanswered} unanswered
                </p>
                <div className="mt-2 space-y-0.5">
                  {[5, 4, 3, 2, 1].map((s) => (
                    <div key={s} className="flex items-center gap-1.5 text-[10px]">
                      <span className="w-3 text-muted-foreground">{s}★</span>
                      <span className="flex-1 h-1.5 bg-muted rounded overflow-hidden">
                        <span className="block h-full rounded" style={{ width: `${starPct(reviewsDetail.stars[`${s}_star`] ?? 0)}%`, background: s >= 4 ? "#639922" : s === 3 ? "#EF9F27" : "#E24B4A" }} />
                      </span>
                      <span className="w-10 text-right text-muted-foreground">{(reviewsDetail.stars[`${s}_star`] ?? 0).toLocaleString("en-CA")}</span>
                    </div>
                  ))}
                </div>
                {sentiment?.available && (
                  <p className="text-xs text-muted-foreground mt-2 leading-snug">
                    {sentiment.positive_pct}% positive · praise: {sentiment.top_praise} · complaint: {sentiment.top_complaint}
                  </p>
                )}
                {recentReviews?.data && recentReviews.data.length > 0 && (
                  <div className="mt-3 space-y-2 border-t border-border pt-2">
                    {recentReviews.data.map((r) => (
                      <div key={r.id} className="space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-medium truncate max-w-[100px]">{r.author_name ?? "Guest"}</span>
                          <span className="text-yellow-400 text-[10px]">{"★".repeat(r.rating ?? 0)}</span>
                        </div>
                        {r.comment && (
                          <p className="text-[10px] text-muted-foreground line-clamp-2 leading-snug">{r.comment}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <>
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1"><Link href="/integrations" className="text-primary hover:underline">Connect Google Business →</Link></p>
              </>
            )}
          </Tile>
          <Tile href="/marketing">
            <TileHeader label="Google Ads" icon={Megaphone} />
            {googleAds && googleAds.spend > 0 ? (
              <>
                <p className="text-3xl font-bold tabular-nums tracking-tight">{gaRoas != null ? `${gaRoas.toFixed(1)}x` : "—"} <span className="text-xs text-muted-foreground">ROAS</span></p>
                <table className="w-full text-xs mt-2">
                  <tbody>
                    <tr><td className="text-muted-foreground">Spend</td><td className="text-right">{fmtCAD(googleAds.spend)}</td><td className="text-muted-foreground pl-3">CTR</td><td className="text-right">{googleAds.ctr}%</td></tr>
                    <tr><td className="text-muted-foreground">Clicks</td><td className="text-right">{googleAds.clicks.toLocaleString("en-CA")}</td><td className="text-muted-foreground pl-3">CPC</td><td className="text-right">{fmtCAD(googleAds.cpc, 2)}</td></tr>
                    <tr><td className="text-muted-foreground">Conv</td><td className="text-right">{googleAds.conversions}</td><td className="text-muted-foreground pl-3">$/conv</td><td className="text-right">{googleAds.cost_per_conversion != null ? fmtCAD(googleAds.cost_per_conversion, 2) : "—"}</td></tr>
                  </tbody>
                </table>
              </>
            ) : (
              <>
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1"><Link href="/marketing" className="text-primary hover:underline">Connect Google Ads →</Link></p>
              </>
            )}
          </Tile>
          <Tile>
            <TileHeader label="Meta Ads" icon={Megaphone} />
            <ComingSoon note="Meta Ads spend & ROAS land once the integration is live." />
          </Tile>
        </div>
      </div>

      {/* ── AI Command Center ── */}
      <div>
        <RowLabel>AI command center</RowLabel>
        <div className="rounded-2xl p-5 bg-card border border-violet-500/20 shadow-sm ring-1 ring-violet-500/5">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-lg bg-violet-500/10 flex items-center justify-center">
                <Sparkles className="h-4 w-4 text-violet-500" />
              </div>
              <p className="text-sm font-semibold">Top ways to grow profit</p>
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="/insights"
                className="text-xs font-medium text-violet-500 hover:text-violet-600 transition-colors"
              >
                View all →
              </Link>
              <button
                onClick={() => setRefreshSuggestions(true)}
                disabled={suggestionsLoading}
                className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-md bg-violet-500/10 border border-violet-500/25 text-violet-600 hover:bg-violet-500/15 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {suggestionsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                Refresh
              </button>
            </div>
          </div>

          {suggestionsLoading ? (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-24 rounded-xl bg-muted/40 animate-pulse" />
              ))}
            </div>
          ) : !profitSuggestions?.available ? (
            <p className="text-xs text-muted-foreground mt-4">
              No recommendations yet{profitSuggestions?.reason ? ` (${profitSuggestions.reason})` : ""}. Needs P&amp;L data in this period.
            </p>
          ) : (
            <>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                {(profitSuggestions.suggestions ?? []).slice(0, 3).map((s, i) => (
                  <div key={i} className="rounded-xl border border-border/60 p-3.5 bg-background/40 flex flex-col">
                    <span
                      className={`self-start text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${
                        s.priority === "high"
                          ? "bg-red-500/15 text-red-500"
                          : s.priority === "medium"
                          ? "bg-orange-500/15 text-orange-600"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {s.priority}
                    </span>
                    <p className="text-sm font-semibold mt-2 leading-snug line-clamp-2">{s.title}</p>
                    <p className="text-xs text-muted-foreground mt-1 leading-snug line-clamp-2">{s.detail}</p>
                    <div className="flex items-center justify-between gap-2 mt-auto pt-3">
                      {s.impact_monthly > 0 ? (
                        <span className="text-sm font-bold text-green-600 tabular-nums">
                          +{fmtCAD(s.impact_monthly)}<span className="text-[10px] font-medium text-muted-foreground">/mo</span>
                        </span>
                      ) : <span />}
                      <Link
                        href="/insights"
                        className="shrink-0 text-xs font-semibold px-2.5 py-1 rounded-md bg-violet-500/10 text-violet-600 hover:bg-violet-500/15 transition-colors"
                      >
                        Review
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-muted-foreground mt-3">
                AI estimate · validate before acting. Not financial advice.
              </p>
            </>
          )}
        </div>
      </div>

      {/* ── Row 5: Invoices & Forecast ── */}
      <div>
        <RowLabel>Invoices &amp; forecast</RowLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <Tile href="/reconciliation">
            <TileHeader label="Invoice Status" icon={FileCheck2} />
            {invoiceStatus ? (
              <>
                <p className={`text-3xl font-bold tabular-nums tracking-tight ${invoiceStatus.coverage_pct != null ? pctColor(100 - invoiceStatus.coverage_pct, { warn: 10, bad: 25 }) : "text-muted-foreground"}`}>
                  {invoiceStatus.coverage_pct != null ? `${invoiceStatus.coverage_pct}%` : "—"} <span className="text-xs text-muted-foreground">coverage</span>
                </p>
                <div className="text-xs text-muted-foreground mt-1 space-y-0.5">
                  <div className="flex justify-between"><span>✅ Matched</span><span>{invoiceStatus.matched}</span></div>
                  <div className="flex justify-between"><span>⚠️ Pending / unmatched</span><span>{invoiceStatus.unmatched}</span></div>
                  <div className="flex justify-between"><span>🔄 Duplicate</span><span>{invoiceStatus.duplicate}</span></div>
                  <div className="flex justify-between border-t border-border pt-0.5"><span>Imported</span><span>{invoiceStatus.imported}</span></div>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">{unresolved} open flags</p>
            )}
          </Tile>
          <Tile>
            <TileHeader label="7-Day Cash Forecast" icon={Wallet} />
            {forecast ? (
              <>
                <p className={`text-3xl font-bold tabular-nums tracking-tight ${forecast.projected_net_flow >= 0 ? "text-green-500" : "text-red-500"}`}>
                  {forecast.projected_net_flow >= 0 ? "+" : ""}{fmtCAD(forecast.projected_net_flow)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">Projected net flow · {fmtCAD(forecast.avg_daily_sales)}/day sales · {fmtCAD(forecast.avg_daily_expense)}/day costs</p>
              </>
            ) : (
              <p className="text-2xl font-bold text-muted-foreground">—</p>
            )}
          </Tile>
          <Tile href="/reconciliation">
            <TileHeader label="Recent Alerts" icon={Bell} />
            {!flags?.data?.length ? (
              <p className="text-sm text-muted-foreground mt-1">No open alerts.</p>
            ) : (
              <ul className="mt-1 space-y-1.5">
                {flags.data.slice(0, 4).map((f) => (
                  <li key={f.id} className="flex items-start gap-2 text-xs">
                    <span
                      className={`mt-1 h-1.5 w-1.5 rounded-full shrink-0 ${
                        f.severity === "high" ? "bg-red-500" : f.severity === "medium" ? "bg-amber-500" : "bg-muted-foreground/50"
                      }`}
                    />
                    <span className="flex-1 min-w-0">
                      <span className="block truncate text-foreground" title={f.message}>{f.message}</span>
                      <span className="text-[10.5px] text-muted-foreground">{fmtRelative(f.created_at)}</span>
                    </span>
                  </li>
                ))}
                {unresolved > 4 && (
                  <li className="text-[11px] text-muted-foreground pt-0.5">+{unresolved - 4} more open</li>
                )}
              </ul>
            )}
          </Tile>
        </div>
      </div>

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
