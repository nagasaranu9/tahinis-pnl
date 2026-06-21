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
} from "lucide-react";
import { usePnLReport } from "@/hooks/use-pnl";
import { useLocationStore } from "@/lib/location-store";
import { downloadPnL } from "@/lib/export-pnl";
import type { ExpenseCategoryBreakdown, PnLLineItems } from "@/types/pnl";

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
      <td className="py-2 pr-3 text-right text-xs text-muted-foreground font-mono w-20">
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
  return (
    <tr className="border-b last:border-0">
      <td className="py-2 px-4 text-sm relative">
        <span className={hasMultiple ? "group relative inline-block cursor-pointer underline decoration-dotted decoration-muted-foreground/50" : ""}>
          {row.category}
          {hasMultiple && (
            <div className="invisible group-hover:visible absolute left-0 top-full z-50 mt-1.5 min-w-[200px] max-w-[280px] rounded-md border border-border bg-card text-card-foreground shadow-xl ring-1 ring-black/5 py-1.5">
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
            <table className="w-full min-w-[480px]">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="py-2.5 px-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Line Item
                  </th>
                  <th className="py-2.5 px-3 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Amount
                  </th>
                  <th className="py-2.5 px-3 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground w-20">
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
          </div>

          {/* Expense breakdown */}
          {report.expense_breakdown.length > 0 && (
            <div className="border rounded-lg overflow-visible">
              <div className="px-4 py-3 border-b bg-muted/20">
                <h2 className="text-sm font-semibold">Expense Breakdown</h2>
                <p className="text-xs text-muted-foreground">{report.expense_count} expenses</p>
              </div>
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
