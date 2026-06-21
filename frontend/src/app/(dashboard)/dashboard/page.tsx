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
  Timer,
  Flame,
  CheckCircle2,
} from "lucide-react";
import { usePnLReport } from "@/hooks/use-pnl";
import { useReconciliationFlags } from "@/hooks/use-reconciliation";
import { usePlatformMetrics } from "@/hooks/use-pipeboard";
import { useReviewsSummary } from "@/hooks/use-reviews";
import {
  useChannelMix,
  useFulfillment,
  useTopVendors,
  useCashForecast,
} from "@/hooks/use-dashboard";
import { useLocations } from "@/hooks/use-locations";
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
  accent,
  href,
  className = "",
}: {
  children: React.ReactNode;
  accent?: string;
  href?: string;
  className?: string;
}) {
  const inner = (
    <div
      className={`border border-border ${accent ? `border-t-2 ${accent}` : ""} rounded-lg p-4 bg-card hover:border-primary/30 transition-colors h-full ${className}`}
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
    <p className="text-[11px] font-semibold text-muted-foreground/70 uppercase tracking-wider mb-2">
      {children}
    </p>
  );
}

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

  // P&L — current range + prior period (deltas)
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

  // MTD + prior full month for pace
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

  // Operational
  const { data: channelMix, isLoading: channelLoading } = useChannelMix(rangeArgs);
  const { data: fulfillment, isLoading: fulfillmentLoading } = useFulfillment(rangeArgs);
  const { data: topFood } = useTopVendors({ ...rangeArgs, category: "Food Cost", limit: 1 });
  const { data: forecast } = useCashForecast(locationParam);

  // Marketing + reviews + reconciliation
  const { data: platformMetrics = [] } = usePlatformMetrics();
  const { data: reviews } = useReviewsSummary(locationParam);
  const { data: flags } = useReconciliationFlags({ unresolved_only: true });
  const { data: allFlags } = useReconciliationFlags({ unresolved_only: false });

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

  const suppressDelta = activePreset === "today";
  const netDelta = suppressDelta ? null : calcDelta(li?.net_revenue, prevLi?.net_revenue);
  const profitDelta = suppressDelta ? null : calcDelta(li?.net_profit, prevLi?.net_profit);
  const avgCheckDelta = suppressDelta ? null : calcDelta(avgCheck, prevAvgCheck);

  // Pace: MTD vs prior month run-rate to same day-of-month
  const pace = useMemo(() => {
    const mtd = mtdPnl?.line_items?.net_revenue
      ? parseFloat(mtdPnl.line_items.net_revenue)
      : null;
    const lastTotal = lastMonthPnl?.line_items?.net_revenue
      ? parseFloat(lastMonthPnl.line_items.net_revenue)
      : null;
    if (mtd == null || lastTotal == null || lastTotal === 0) return null;
    const now = new Date();
    const dayOfMonth = now.getDate();
    const daysInLastMonth = new Date(now.getFullYear(), now.getMonth(), 0).getDate();
    const expectedByNow = lastTotal * (dayOfMonth / daysInLastMonth);
    if (expectedByNow === 0) return null;
    return Math.round((mtd / expectedByNow) * 100);
  }, [mtdPnl, lastMonthPnl]);

  // Food cost over-target
  const foodPct = li?.cogs_pct ? parseFloat(li.cogs_pct) : null;
  const FOOD_TARGET = 30;
  const foodOverPp = foodPct != null ? foodPct - FOOD_TARGET : null;

  // Invoices
  const totalImported = allFlags?.meta?.total ?? 0;
  const unresolved = flags?.meta?.total ?? 0;
  const matched = totalImported - unresolved;
  const matchRate = totalImported > 0 ? (matched / totalImported) * 100 : null;

  // Ads
  const googleAds = platformMetrics.find((m) => /google/i.test(m.platform));
  const metaAds = platformMetrics.find((m) => /meta|facebook/i.test(m.platform));

  const handleRefresh = useCallback(() => {
    qc.invalidateQueries();
  }, [qc]);

  return (
    <div className="space-y-5 max-w-7xl">
      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-red-500/10 flex items-center justify-center">
            <Flame className="h-5 w-5 text-red-500" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">
              Tahini&apos;s {storeId ? `#${storeId}` : ""} {location?.name ? `— ${location.name}` : ""}
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
              <CheckCircle2 className="h-3 w-3 text-green-500" />
              Synced · {dateRange.label}
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
            className="p-2 rounded-md border border-border bg-card text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors cursor-pointer"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* ── Row 1: Hero metrics ── */}
      <div>
        <RowLabel>Hero metrics</RowLabel>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Tile accent="border-t-primary" href="/pnl">
            <TileHeader label="Net Sales" icon={TrendingUp} />
            <p className="text-2xl font-bold tabular-nums text-primary">{pnlLoading ? "…" : fmtCAD(li?.net_revenue)}</p>
            <div className="mt-1"><DeltaText delta={netDelta} /> <span className="text-xs text-muted-foreground">{dateRange.label}</span></div>
          </Tile>
          <Tile accent="border-t-purple-500" href="/pnl">
            <TileHeader label="MTD Sales" icon={DollarSign} />
            <p className="text-2xl font-bold tabular-nums">{fmtCAD(mtdPnl?.line_items?.net_revenue)}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {pace != null ? `Pace ${pace}% of last month` : "Pace —"}
            </p>
          </Tile>
          <Tile accent="border-t-green-500" href="/pnl">
            <TileHeader label="Prime Cost" icon={ShoppingCart} />
            <p className={`text-2xl font-bold tabular-nums ${pctColor(li?.prime_cost_pct, { warn: 60, bad: 68 })}`}>
              {fmtPct(li?.prime_cost_pct)}
            </p>
            <p className="text-xs text-muted-foreground mt-1">Target &lt; 60%</p>
          </Tile>
          <Tile accent="border-t-red-500" href="/pnl">
            <TileHeader label="Net Profit" icon={TrendingUp} />
            <p className={`text-2xl font-bold tabular-nums ${profitColor(li?.net_profit)}`}>{fmtCAD(li?.net_profit)}</p>
            <div className="mt-1"><DeltaText delta={profitDelta} /> {li?.net_profit_pct && <span className="text-xs text-muted-foreground">{fmtPct(li.net_profit_pct)} margin</span>}</div>
          </Tile>
        </div>
      </div>

      {/* ── Row 2: Toast POS ── */}
      <div>
        <RowLabel>Toast POS</RowLabel>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <Tile className="lg:col-span-2">
            <TileHeader label="Revenue by Channel" icon={ShoppingCart} />
            {channelLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : !channelMix?.channels?.length ? (
              <p className="text-sm text-muted-foreground">No orders in this period.</p>
            ) : (
              <>
                <div className="flex h-3.5 rounded overflow-hidden my-2">
                  {channelMix.channels.map((c, i) => (
                    <div
                      key={c.channel}
                      style={{ width: `${c.pct}%`, background: CHANNEL_COLORS[i % CHANNEL_COLORS.length] }}
                      title={`${c.channel} ${c.pct}%`}
                    />
                  ))}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  {channelMix.channels.slice(0, 4).map((c, i) => (
                    <span key={c.channel} className="flex items-center gap-1.5">
                      <span className="inline-block w-2 h-2 rounded-sm" style={{ background: CHANNEL_COLORS[i % CHANNEL_COLORS.length] }} />
                      {c.channel} {c.pct}%
                    </span>
                  ))}
                </div>
              </>
            )}
          </Tile>
          <Tile>
            <TileHeader label="Avg Check Size" icon={DollarSign} />
            <p className="text-2xl font-bold tabular-nums">{fmtCAD(avgCheck)}</p>
            <div className="mt-1"><DeltaText delta={avgCheckDelta} /> {orderCount > 0 && <span className="text-xs text-muted-foreground">{orderCount.toLocaleString("en-CA")} orders</span>}</div>
          </Tile>
        </div>
      </div>

      {/* ── Row 3: Food & Labor ── */}
      <div>
        <RowLabel>Food &amp; labor</RowLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Tile href="/expenses">
            <TileHeader label="Food Cost" icon={ShoppingCart} />
            <p className={`text-2xl font-bold tabular-nums ${pctColor(foodPct, { warn: 32, bad: 38 })}`}>{fmtPct(foodPct)}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {foodOverPp != null && foodOverPp > 0
                ? `Over by ${foodOverPp.toFixed(1)}pp vs ${FOOD_TARGET}% target`
                : foodOverPp != null
                ? `${Math.abs(foodOverPp).toFixed(1)}pp under target`
                : "—"}
            </p>
            {topFood?.vendors?.[0] && (
              <p className="text-xs text-muted-foreground mt-0.5">
                Top supplier: <span className="text-foreground font-medium">{topFood.vendors[0].vendor}</span> ({fmtCAD(topFood.vendors[0].total)})
              </p>
            )}
          </Tile>
          <Tile>
            <TileHeader label="Labor Cost" icon={Users} />
            <p className="text-2xl font-bold tabular-nums text-muted-foreground">—</p>
            <ComingSoon note="Hours, headcount & avg wage land once the PushOperations integration is live." />
          </Tile>
        </div>
      </div>

      {/* ── Row 4: Reviews & Ads ── */}
      <div>
        <RowLabel>Reviews &amp; ads</RowLabel>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Tile href="/reviews">
            <TileHeader label="Google Rating" icon={Star} />
            {reviews?.average_rating != null ? (
              <>
                <p className="text-2xl font-bold tabular-nums text-yellow-500">
                  {reviews.average_rating.toFixed(1)} ★
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {reviews.total_review_count.toLocaleString("en-CA")} reviews
                </p>
              </>
            ) : (
              <>
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1">
                  <Link href="/integrations" className="text-primary hover:underline">Connect Google Business →</Link>
                </p>
              </>
            )}
          </Tile>
          <Tile href="/marketing">
            <TileHeader label="Google Ads" icon={Megaphone} />
            {googleAds ? (
              <>
                <p className="text-2xl font-bold tabular-nums">{googleAds.roas ? `${googleAds.roas.toFixed(1)}x` : "—"}</p>
                <p className="text-xs text-muted-foreground mt-1">{fmtCAD(googleAds.spend)} spend</p>
              </>
            ) : (
              <>
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1">
                  <Link href="/marketing" className="text-primary hover:underline">Connect Google Ads →</Link>
                </p>
              </>
            )}
          </Tile>
          <Tile href="/marketing">
            <TileHeader label="Meta Ads" icon={Megaphone} />
            {metaAds ? (
              <>
                <p className="text-2xl font-bold tabular-nums">{metaAds.roas ? `${metaAds.roas.toFixed(1)}x` : "—"}</p>
                <p className="text-xs text-muted-foreground mt-1">{fmtCAD(metaAds.spend)} spend</p>
              </>
            ) : (
              <>
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1">
                  <Link href="/marketing" className="text-primary hover:underline">Connect Meta Ads →</Link>
                </p>
              </>
            )}
          </Tile>
        </div>
      </div>

      {/* ── Row 5: Invoices & Forecast ── */}
      <div>
        <RowLabel>Invoices &amp; forecast</RowLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Tile href="/reconciliation">
            <TileHeader label="Invoice Match Rate" icon={FileCheck2} />
            <p className={`text-2xl font-bold tabular-nums ${matchRate != null ? pctColor(100 - (matchRate ?? 100), { warn: 10, bad: 25 }) : "text-muted-foreground"}`}>
              {matchRate != null ? fmtPct(matchRate) : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {matched} matched · {unresolved} flagged · {totalImported} imported
            </p>
          </Tile>
          <Tile>
            <TileHeader label="7-Day Cash Forecast" icon={Wallet} />
            {forecast ? (
              <>
                <p className={`text-2xl font-bold tabular-nums ${forecast.projected_net_flow >= 0 ? "text-green-500" : "text-red-500"}`}>
                  {forecast.projected_net_flow >= 0 ? "+" : ""}{fmtCAD(forecast.projected_net_flow)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Projected net flow · {fmtCAD(forecast.avg_daily_sales)}/day sales run-rate
                </p>
              </>
            ) : (
              <>
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1">Run-rate projection</p>
              </>
            )}
          </Tile>
        </div>
      </div>

      {/* ── Row 6: Fulfillment time ── */}
      <div>
        <RowLabel>Operations</RowLabel>
        <Tile>
          <TileHeader label="Avg Fulfillment Time" icon={Timer} />
          {fulfillmentLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : !fulfillment || fulfillment.avg_seconds == null ? (
            <>
              <p className="text-2xl font-bold text-muted-foreground">—</p>
              <p className="text-xs text-muted-foreground mt-1">
                No timed orders in this period (needs Toast open/close timestamps).
              </p>
            </>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <p className="text-3xl font-bold tabular-nums">{fmtDuration(fulfillment.avg_seconds)}</p>
                <p className="text-xs mt-1">
                  Target {fmtDuration(fulfillment.target_seconds)} ·{" "}
                  {fulfillment.avg_seconds <= fulfillment.target_seconds ? (
                    <span className="text-green-500 font-medium">
                      {fmtDuration(fulfillment.target_seconds - fulfillment.avg_seconds)} faster
                    </span>
                  ) : (
                    <span className="text-red-500 font-medium">
                      {fmtDuration(fulfillment.avg_seconds - fulfillment.target_seconds)} slower
                    </span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground mt-2">
                  Fastest {fmtDuration(fulfillment.fastest_seconds)} · Slowest {fmtDuration(fulfillment.slowest_seconds)} · {fulfillment.sample_size} orders
                </p>
              </div>
              <div className="md:col-span-2 space-y-1.5">
                {fulfillment.by_channel.map((c) => (
                  <div key={c.channel} className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">{c.channel}</span>
                    <span className="font-mono font-medium text-foreground">{fmtDuration(c.avg_seconds)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Tile>
      </div>

      {/* Click-away */}
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

const CHANNEL_COLORS = ["#378ADD", "#7F77DD", "#1D9E75", "#EF9F27", "#D85A30"];
