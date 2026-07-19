"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import {
  TrendingDown,
  TrendingUp,
  Minus,
  Download,
  FileText,
  Loader2,
  GitCompareArrows,
  ChevronDown,
} from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { usePnLReport, usePnLTrend, useDiscountBreakdown } from "@/hooks/use-pnl";
import { useLocationStore } from "@/lib/location-store";
import { downloadPnL } from "@/lib/export-pnl";
import type {
  BenchmarkChip,
  ExpenseCategoryBreakdown,
  PnLLineItems,
  PnLTrendPoint,
} from "@/types/pnl";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function toISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fmt(val: string | null | undefined): string {
  if (val == null) return "—";
  const n = parseFloat(val);
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    minimumFractionDigits: 2,
  }).format(n);
}

function fmtPct(val: string | null | undefined): string {
  if (val == null) return "";
  return `${parseFloat(val).toFixed(1)}%`;
}

function delta(
  curr: string | null | undefined,
  prev: string | null | undefined
): { pct: string; dir: "up" | "down" | "flat" } | null {
  if (curr == null || prev == null) return null;
  const c = parseFloat(curr);
  const p = parseFloat(prev);
  if (isNaN(c) || isNaN(p) || p === 0) return null;
  const d = ((c - p) / Math.abs(p)) * 100;
  return {
    pct: `${d >= 0 ? "+" : ""}${d.toFixed(1)}%`,
    dir: d > 0.05 ? "up" : d < -0.05 ? "down" : "flat",
  };
}

// ─── Date Presets ─────────────────────────────────────────────────────────────

type PresetKey =
  | "thisMonth"
  | "lastMonth"
  | "last30"
  | "last7"
  | "quarter"
  | "ytd"
  | "lastYear"
  | "custom";

interface DateRange {
  start: string;
  end: string;
  label: string;
}

function getPreset(key: PresetKey): DateRange {
  const now = new Date();
  const today = toISO(now);
  switch (key) {
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
    case "lastYear": {
      const y = now.getFullYear() - 1;
      return { start: `${y}-01-01`, end: `${y}-12-31`, label: String(y) };
    }
    default:
      return { start: today, end: today, label: "Custom" };
  }
}

const PRESETS: { key: PresetKey; label: string }[] = [
  { key: "last7", label: "7D" },
  { key: "last30", label: "30D" },
  { key: "thisMonth", label: "This Month" },
  { key: "lastMonth", label: "Last Month" },
  { key: "quarter", label: "Quarter" },
  { key: "ytd", label: "YTD" },
  { key: "lastYear", label: "Last Year" },
  { key: "custom", label: "Custom" },
];

/** Given a period, compute the equivalent prior period of the same length. */
function priorPeriod(start: string, end: string): { start: string; end: string } {
  const [sy, sm, sd] = start.split("-").map(Number);
  const [ey, em, ed] = end.split("-").map(Number);
  const s = new Date(sy, sm - 1, sd);
  const e = new Date(ey, em - 1, ed);
  const days = Math.round((e.getTime() - s.getTime()) / 86_400_000) + 1;
  const pe = new Date(sy, sm - 1, sd - 1);
  const ps = new Date(sy, sm - 1, sd - days);
  return { start: toISO(ps), end: toISO(pe) };
}

// ─── Table components ─────────────────────────────────────────────────────────

function DeltaCell({ curr, prev }: { curr: string | null | undefined; prev: string | null | undefined }) {
  const d = delta(curr, prev);
  if (!d) return <td className="py-2 pr-3 text-right text-xs text-muted-foreground w-20">—</td>;
  const cls =
    d.dir === "up"
      ? "text-green-400"
      : d.dir === "down"
      ? "text-red-400"
      : "text-muted-foreground";
  const Icon = d.dir === "up" ? TrendingUp : d.dir === "down" ? TrendingDown : Minus;
  return (
    <td className={`py-2 pr-3 text-right text-xs font-mono w-20 ${cls}`}>
      <span className="flex items-center justify-end gap-0.5">
        <Icon className="h-3 w-3" />
        {d.pct}
      </span>
    </td>
  );
}

function PnLRow({
  label,
  value,
  prevValue,
  pct,
  indent = false,
  bold = false,
  highlight,
  compare,
}: {
  label: string;
  value: string | null | undefined;
  prevValue?: string | null | undefined;
  pct?: string | null;
  indent?: boolean;
  bold?: boolean;
  highlight?: "green" | "red" | "neutral";
  compare: boolean;
}) {
  const valueColor =
    highlight === "green"
      ? "text-green-400"
      : highlight === "red"
      ? "text-red-400"
      : "text-foreground";

  return (
    <tr className={`border-b border-border last:border-0 ${bold ? "bg-muted/20" : ""}`}>
      <td className={`py-2 text-sm ${indent ? "pl-8" : "pl-3"} ${bold ? "font-semibold" : ""}`}>
        {label}
      </td>
      <td
        className={`py-2 pr-3 text-right text-sm font-mono tabular-nums ${
          bold ? "font-bold" : ""
        } ${valueColor}`}
      >
        {fmt(value)}
      </td>
      <td className="hidden sm:table-cell py-2 pr-3 text-right text-xs text-muted-foreground font-mono w-20">
        {fmtPct(pct)}
      </td>
      {compare && (
        <>
          <td className="py-2 pr-3 text-right text-sm font-mono tabular-nums text-muted-foreground">
            {fmt(prevValue)}
          </td>
          <DeltaCell curr={value} prev={prevValue} />
        </>
      )}
    </tr>
  );
}

function SeparatorRow({ label, compare }: { label: string; compare: boolean }) {
  return (
    <tr>
      <td
        colSpan={compare ? 5 : 3}
        className="pt-4 pb-1 px-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </td>
    </tr>
  );
}

function ExpenseBreakdownRow({ row }: { row: ExpenseCategoryBreakdown }) {
  const hasMultiple = row.expenses.length > 1;
  const [open, setOpen] = useState(false);
  return (
    <tr className="border-b last:border-0">
      <td className="py-2 px-4 text-sm relative">
        <span
          onClick={() => hasMultiple && setOpen((v) => !v)}
          className={hasMultiple ? "group relative inline-flex items-center gap-1 cursor-pointer underline decoration-dotted decoration-muted-foreground/50 select-none" : ""}
        >
          {row.category}
          {hasMultiple && <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />}
          {hasMultiple && (
            <div className={`${open ? "visible" : "invisible"} sm:group-hover:visible absolute left-0 top-full z-50 mt-1.5 min-w-[200px] max-w-[280px] rounded-md border border-border bg-card text-card-foreground shadow-xl ring-1 ring-black/5 py-1.5`}>
              {row.expenses.map((e, i) => (
                <div key={i} className="flex justify-between gap-3 px-2.5 py-1 text-xs">
                  <span className="truncate text-muted-foreground">{e.vendor_name || "—"}</span>
                  <span className="font-mono tabular-nums shrink-0">{fmt(e.amount)}</span>
                </div>
              ))}
            </div>
          )}
        </span>
      </td>
      <td className="py-2 px-4 text-xs text-muted-foreground">{row.expense_count} items</td>
      <td className="py-2 px-4 text-right text-sm font-mono tabular-nums">{fmt(row.total)}</td>
    </tr>
  );
}

// Distinct, repeatable palette for expense-category slices.
const PIE_COLORS = [
  "#3b82f6", "#ef4444", "#f59e0b", "#10b981", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
  "#06b6d4", "#e11d48", "#a855f7", "#22c55e",
];

function ExpensePie({ breakdown }: { breakdown: ExpenseCategoryBreakdown[] }) {
  const data = useMemo(
    () =>
      breakdown
        .map((b) => ({ name: b.category, value: Math.abs(parseFloat(b.total) || 0) }))
        .filter((d) => d.value > 0)
        .sort((a, b) => b.value - a.value),
    [breakdown]
  );
  const grand = data.reduce((s, d) => s + d.value, 0);
  if (data.length === 0 || grand === 0) return null;

  return (
    <div className="px-4 py-4 border-b">
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={95}
              paddingAngle={1.5}
              stroke="none"
            >
              {data.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v: number) => [
                `${fmt(String(v))} · ${((v / grand) * 100).toFixed(1)}%`,
                "",
              ]}
              contentStyle={{
                background: "var(--card, #111)",
                border: "1px solid var(--border, #333)",
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Legend
              layout="vertical"
              align="right"
              verticalAlign="middle"
              iconType="circle"
              formatter={(value: string) => {
                const d = data.find((x) => x.name === value);
                const pct = d ? ((d.value / grand) * 100).toFixed(0) : "0";
                return `${value} · ${pct}%`;
              }}
              wrapperStyle={{ fontSize: 12 }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── Benchmarks ──────────────────────────────────────────────────────────────

const BENCH_STYLES: Record<string, string> = {
  good: "border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400",
  watch: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  bad: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  unknown: "border-border bg-muted/30 text-muted-foreground",
};

function BenchmarkPill({ chip }: { chip: BenchmarkChip }) {
  return (
    <span
      className={`inline-flex items-baseline gap-1.5 rounded-md border px-2.5 py-1 text-xs ${
        BENCH_STYLES[chip.status] ?? BENCH_STYLES.unknown
      }`}
      title={`${chip.label}: industry ${chip.target_label}`}
    >
      <span className="font-medium">{chip.label}</span>
      <span className="font-mono font-semibold tabular-nums">
        {chip.value_pct != null ? `${parseFloat(chip.value_pct).toFixed(1)}%` : "—"}
      </span>
      <span className="opacity-60">· {chip.target_label}</span>
    </span>
  );
}

// ─── Trend sparklines ────────────────────────────────────────────────────────

/** Inline sparkline. Kept as raw SVG rather than a chart lib: these are ~6
 *  points inside a table-dense page, where a full chart component costs more
 *  than it communicates. */
function Sparkline({
  values,
  invert = false,
}: {
  values: (number | null)[];
  /** true when lower is better (cost ratios), so the trend colour flips. */
  invert?: boolean;
}) {
  const pts = values.filter((v): v is number => v != null);
  if (pts.length < 2) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const W = 72;
  const H = 22;
  const step = W / (values.length - 1);

  // Nulls (a month with no data) break the line rather than being drawn as
  // zero, which would invent a cliff that never happened.
  const segments: string[] = [];
  let current: string[] = [];
  values.forEach((v, i) => {
    if (v == null) {
      if (current.length > 1) segments.push(current.join(" "));
      current = [];
      return;
    }
    const x = i * step;
    const y = H - ((v - min) / span) * (H - 4) - 2;
    current.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  });
  if (current.length > 1) segments.push(current.join(" "));

  const first = pts[0];
  const last = pts[pts.length - 1];
  const rising = last > first;
  const better = invert ? !rising : rising;
  const stroke = last === first ? "#94a3b8" : better ? "#22c55e" : "#ef4444";

  const lastIdx = values.map((v, i) => (v != null ? i : -1)).filter((i) => i >= 0).pop() ?? 0;
  const lastX = lastIdx * step;
  const lastY = H - ((last - min) / span) * (H - 4) - 2;

  return (
    <svg width={W} height={H} className="overflow-visible shrink-0" aria-hidden>
      {segments.map((pointsAttr, i) => (
        <polyline
          key={i}
          points={pointsAttr}
          fill="none"
          stroke={stroke}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
      <circle cx={lastX} cy={lastY} r={2} fill={stroke} />
    </svg>
  );
}

const TREND_METRICS: {
  key: keyof PnLTrendPoint;
  label: string;
  pct?: boolean;
  invert?: boolean;
}[] = [
  { key: "net_revenue", label: "Net Revenue" },
  { key: "cogs_pct", label: "Food %", pct: true, invert: true },
  { key: "labor_pct", label: "Labor %", pct: true, invert: true },
  { key: "prime_cost_pct", label: "Prime %", pct: true, invert: true },
  { key: "net_profit", label: "Net Profit" },
];

function TrendStrip({ locationId }: { locationId: string | null }) {
  const { data, isLoading } = usePnLTrend({
    months: 6,
    location_id: locationId ?? undefined,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground border border-border rounded-lg px-4 py-3">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading 6-month trend…
      </div>
    );
  }
  if (!data?.points?.length) return null;

  const range = `${data.points[0].period_label} → ${data.points[data.points.length - 1].period_label}`;

  return (
    <div className="border border-border rounded-lg bg-card">
      <div className="px-4 py-2.5 border-b border-border flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold">6-Month Trend</h2>
        <span className="text-xs text-muted-foreground font-mono">{range}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 divide-y sm:divide-y-0 sm:divide-x divide-border">
        {TREND_METRICS.map(({ key, label, pct, invert }) => {
          const values = data.points.map((p) => {
            const raw = p[key];
            return raw == null ? null : parseFloat(raw as string);
          });
          const last = [...values].reverse().find((v) => v != null) ?? null;
          return (
            <div key={key} className="px-4 py-3 space-y-1.5">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-mono font-semibold tabular-nums">
                  {last == null
                    ? "—"
                    : pct
                    ? `${last.toFixed(1)}%`
                    : `$${last.toLocaleString("en-CA", { maximumFractionDigits: 0 })}`}
                </span>
                <Sparkline values={values} invert={invert} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Discount breakdown ──────────────────────────────────────────────────────

function DiscountBreakdownCard({
  periodStart,
  periodEnd,
  locationId,
  totalDiscounts,
  grossRevenue,
}: {
  periodStart: string;
  periodEnd: string;
  locationId: string | null;
  totalDiscounts: string | null;
  grossRevenue: string | null;
}) {
  const { data, isLoading } = useDiscountBreakdown({
    period_start: periodStart,
    period_end: periodEnd,
    location_id: locationId ?? undefined,
  });

  const pctOfGross =
    totalDiscounts && grossRevenue && parseFloat(grossRevenue) > 0
      ? (parseFloat(totalDiscounts) / parseFloat(grossRevenue)) * 100
      : null;

  if (isLoading) return null;

  // No named rows yet means the backfill hasn't run for this period — say so
  // rather than rendering an empty card that reads like "no discounts".
  if (!data?.discounts?.length) {
    if (!totalDiscounts || parseFloat(totalDiscounts) === 0) return null;
    return (
      <div className="border border-border rounded-lg bg-card px-4 py-3">
        <h2 className="text-sm font-semibold">Discount Breakdown</h2>
        <p className="text-xs text-muted-foreground mt-1">
          {fmt(totalDiscounts)} in discounts this period, not yet itemized by promo.
          Run a Toast sync to capture discount names.
        </p>
      </div>
    );
  }

  // Ranked by amount server-side; the long tail is dozens of sub-$10 promos
  // that add noise without changing a decision.
  const top = data.discounts.slice(0, 5);

  return (
    <div className="border border-border rounded-lg bg-card overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold">Discount Breakdown — Top 5</h2>
        <p className="text-xs text-muted-foreground">
          {fmt(data.total)} across {data.discounts.length} promo
          {data.discounts.length === 1 ? "" : "s"}
          {pctOfGross != null && ` · ${pctOfGross.toFixed(1)}% of gross revenue`}
        </p>
      </div>
      <table className="w-full">
        <tbody>
          {top.map((d) => (
            <tr key={`${d.name}-${d.scope}`} className="border-b border-border/60 last:border-0">
              <td className="py-2 px-4 text-sm">
                {d.name}
                {d.scope === "item" && (
                  <span className="ml-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                    item
                  </span>
                )}
              </td>
              <td className="py-2 px-3 text-right text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                {d.count.toLocaleString("en-CA")}×
              </td>
              <td className="py-2 px-3 text-right text-xs text-muted-foreground tabular-nums w-16">
                {d.pct_of_discounts != null ? `${parseFloat(d.pct_of_discounts).toFixed(1)}%` : "—"}
              </td>
              <td className="py-2 px-4 text-right text-sm font-mono tabular-nums whitespace-nowrap">
                {fmt(d.total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

function defaultPeriod(): DateRange {
  return getPreset("thisMonth");
}

export default function PnLPage() {
  const [activePreset, setActivePreset] = useState<PresetKey>("thisMonth");
  const [customStart, setCustomStart] = useState(new Date().toISOString().slice(0, 10));
  const [customEnd, setCustomEnd] = useState(new Date().toISOString().slice(0, 10));
  const [compare, setCompare] = useState(false);
  const [exporting, setExporting] = useState<"csv" | "pdf" | null>(null);
  const locationId = useLocationStore((s) => s.selectedLocationId);

  const period = useMemo<DateRange>(() => {
    if (activePreset === "custom") {
      return { start: customStart, end: customEnd, label: `${customStart} → ${customEnd}` };
    }
    return getPreset(activePreset);
  }, [activePreset, customStart, customEnd]);

  const prior = useMemo(() => priorPeriod(period.start, period.end), [period]);

  const { data: report, isLoading, isError } = usePnLReport({
    period_start: period.start,
    period_end: period.end,
    location_id: locationId ?? undefined,
  });

  const { data: priorReport, isLoading: priorLoading } = usePnLReport({
    period_start: prior.start,
    period_end: prior.end,
    location_id: locationId ?? undefined,
  });

  const li: PnLLineItems | undefined = report?.line_items;
  const pli: PnLLineItems | undefined = compare ? priorReport?.line_items : undefined;

  async function handleExport(format: "csv" | "pdf") {
    setExporting(format);
    try {
      await downloadPnL({
        format,
        period_start: period.start,
        period_end: period.end,
        location_id: locationId ?? undefined,
      });
    } finally {
      setExporting(null);
    }
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">P&L Report</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Profit & Loss statement — {period.label}
          </p>
        </div>

        {/* Action buttons */}
        {report && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCompare((v) => !v)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border rounded-md transition-colors ${
                compare
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-card text-muted-foreground hover:text-foreground hover:border-primary/40"
              }`}
            >
              <GitCompareArrows className="h-3.5 w-3.5" />
              Compare
            </button>
            <button
              onClick={() => handleExport("csv")}
              disabled={!!exporting}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-border rounded-md bg-card text-muted-foreground hover:text-foreground hover:border-primary/40 disabled:opacity-50 transition-colors"
            >
              {exporting === "csv" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              CSV
            </button>
            <button
              onClick={() => handleExport("pdf")}
              disabled={!!exporting}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-border rounded-md bg-card text-muted-foreground hover:text-foreground hover:border-primary/40 disabled:opacity-50 transition-colors"
            >
              {exporting === "pdf" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <FileText className="h-3.5 w-3.5" />
              )}
              PDF
            </button>
          </div>
        )}
      </div>

      {/* Period selector */}
      <div className="border border-border rounded-lg p-4 bg-card space-y-3">
        {/* Preset chips */}
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.key}
              onClick={() => setActivePreset(p.key)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                activePreset === p.key
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-primary/40"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Custom date inputs — shown when custom preset active */}
        {activePreset === "custom" && (
          <div className="flex flex-wrap gap-3 items-end pt-1">
            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">
                From
              </label>
              <input
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
                className="text-sm border border-input rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">
                To
              </label>
              <input
                type="date"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="text-sm border border-input rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
        )}

        {/* Period info */}
        <p className="text-xs text-muted-foreground">
          {period.start} → {period.end}
          {compare && (
            <span className="ml-3 text-muted-foreground/60">
              vs. {prior.start} → {prior.end}
            </span>
          )}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Computing P&L…
        </div>
      )}
      {isError && (
        <p className="text-sm text-destructive">Failed to load report. Check period dates.</p>
      )}

      {report && !report.bank_statement_verified && (
        <div className="flex items-start gap-2 rounded-md bg-red-500/10 border border-red-500/20 px-3 py-2.5">
          <span className="text-xs text-red-600 dark:text-red-400">
            <span className="font-semibold">No bank statement for this period.</span>{" "}
            {report.bank_statement_warning ?? "This P&L is unreconciled and may not be accurate."}{" "}
            <Link href="/documents" className="underline hover:no-underline">
              Upload bank statement →
            </Link>
          </span>
        </div>
      )}

      {report && li && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Net Revenue", val: li.net_revenue, prev: pli?.net_revenue },
              { label: "Gross Profit", val: li.gross_profit, prev: pli?.gross_profit },
              { label: "Prime Cost", val: li.prime_cost, prev: pli?.prime_cost },
              { label: "Net Profit", val: li.net_profit, prev: pli?.net_profit },
            ].map(({ label, val, prev }) => {
              const d = compare ? delta(val, prev) : null;
              return (
                <div key={label} className="border border-border rounded-lg p-4 bg-card space-y-1">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
                  <p className="text-lg font-bold tabular-nums font-mono text-primary">
                    {fmt(val)}
                  </p>
                  {compare && prev != null && (
                    <p className="text-xs text-muted-foreground">
                      vs. {fmt(prev)}
                      {d && (
                        <span
                          className={`ml-1 font-medium ${
                            d.dir === "up"
                              ? "text-green-400"
                              : d.dir === "down"
                              ? "text-red-400"
                              : "text-muted-foreground"
                          }`}
                        >
                          {d.pct}
                        </span>
                      )}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {/* Benchmark chips — key operating ratios vs industry targets */}
          {report.benchmarks?.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {report.benchmarks.map((b) => (
                <BenchmarkPill key={b.metric} chip={b} />
              ))}
            </div>
          )}

          {/* 6-month trend */}
          <TrendStrip locationId={locationId} />

          {/* Full P&L table */}
          <div className="border border-border rounded-lg overflow-x-auto">
            {compare && (
              <div className="border-b border-border bg-muted/20 px-3 py-2 flex items-center justify-end gap-4 sm:gap-6 text-xs text-muted-foreground font-medium min-w-[480px] flex-wrap">
                {priorLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                <span className="text-foreground">{period.label}</span>
                <span>{prior.start} → {prior.end}</span>
                <span>Δ Change</span>
              </div>
            )}
            <table className={`w-full ${compare ? "min-w-[560px]" : "min-w-0"}`}>
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="py-2.5 px-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Line Item
                  </th>
                  <th className="py-2.5 px-3 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Amount
                  </th>
                  <th className="hidden sm:table-cell py-2.5 px-3 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground w-20">
                    % Rev
                  </th>
                  {compare && (
                    <>
                      <th className="py-2.5 px-3 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Prior
                      </th>
                      <th className="py-2.5 px-3 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground w-20">
                        Δ
                      </th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                <SeparatorRow label="Revenue" compare={compare} />
                <PnLRow label="Gross Revenue" value={li.gross_revenue} prevValue={pli?.gross_revenue} compare={compare} />
                <PnLRow label="Discounts" indent value={li.total_discounts} prevValue={pli?.total_discounts} highlight="red" compare={compare} />
                <PnLRow label="Net Revenue" value={li.net_revenue} prevValue={pli?.net_revenue} bold highlight="neutral" compare={compare} />

                <SeparatorRow label="Cost of Goods" compare={compare} />
                <PnLRow label="COGS" value={li.cogs} prevValue={pli?.cogs} pct={li.cogs_pct} indent highlight="red" compare={compare} />
                <PnLRow label="Gross Profit" value={li.gross_profit} prevValue={pli?.gross_profit} bold highlight="green" compare={compare} />

                <SeparatorRow label="Labor" compare={compare} />
                <PnLRow label="Labor Cost" value={li.labor_cost} prevValue={pli?.labor_cost} pct={li.labor_pct} indent highlight="red" compare={compare} />
                <PnLRow label="Prime Cost" value={li.prime_cost} prevValue={pli?.prime_cost} pct={li.prime_cost_pct} bold highlight="neutral" compare={compare} />

                <SeparatorRow label="Operating Expenses" compare={compare} />
                <PnLRow label="Other Operating Expenses" value={li.operating_expenses} prevValue={pli?.operating_expenses} indent highlight="red" compare={compare} />

                <SeparatorRow label="Bottom Line" compare={compare} />
                <PnLRow
                  label="EBITDA"
                  value={li.ebitda}
                  prevValue={pli?.ebitda}
                  pct={li.ebitda_pct}
                  bold
                  highlight={parseFloat(li.ebitda ?? "0") >= 0 ? "green" : "red"}
                  compare={compare}
                />
                {li.interest_expense && (
                  <PnLRow
                    label="Interest & Financing"
                    indent
                    value={li.interest_expense}
                    prevValue={pli?.interest_expense}
                    highlight="red"
                    compare={compare}
                  />
                )}
                <PnLRow
                  label="Net Profit"
                  value={li.net_profit}
                  prevValue={pli?.net_profit}
                  pct={li.net_profit_pct}
                  bold
                  highlight={parseFloat(li.net_profit ?? "0") >= 0 ? "green" : "red"}
                  compare={compare}
                />
              </tbody>
            </table>
            <p className="px-4 py-2 text-[11px] text-muted-foreground border-t">
              Net Profit is pre-tax and pre-depreciation: EBITDA less interest &amp;
              financing costs. Depreciation/amortization and income tax are not
              tracked in this system — consult your accountant for after-tax figures.
            </p>
          </div>

          {/* Discount breakdown — attributes the discount line to promos */}
          <DiscountBreakdownCard
            periodStart={period.start}
            periodEnd={period.end}
            locationId={locationId}
            totalDiscounts={li.total_discounts}
            grossRevenue={li.gross_revenue}
          />

          {/* Expense breakdown */}
          {report.expense_breakdown.length > 0 && (
            <div className="border rounded-lg overflow-visible">
              <div className="px-4 py-3 border-b bg-muted/20">
                <h2 className="text-sm font-semibold">Expense Breakdown</h2>
                <p className="text-xs text-muted-foreground">{report.expense_count} expenses · hover a category for line items</p>
              </div>
              <ExpensePie breakdown={report.expense_breakdown} />
              <table className="w-full">
                <tbody>
                  {report.expense_breakdown.map((row) => (
                    <ExpenseBreakdownRow key={row.category} row={row} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="text-xs text-muted-foreground">
            {report.order_count} Toast orders · {report.expense_count} expenses ·{" "}
            {report.currency_code}
          </p>
        </>
      )}
    </div>
  );
}
