"use client";

import { useState } from "react";
import Link from "next/link";
import { RefreshCw, AlertTriangle, Receipt } from "lucide-react";
import { useLocationStore } from "@/lib/location-store";
import { useHstSummary, useHstBackfill, type HstPeriod } from "@/hooks/use-hst";

function money(v: string | number) {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return n.toLocaleString("en-CA", { style: "currency", currency: "CAD" });
}

const QUARTER_MONTHS: Record<number, string> = {
  1: "Jan–Mar",
  2: "Apr–Jun",
  3: "Jul–Sep",
  4: "Oct–Dec",
};

export default function TaxPage() {
  const locationId = useLocationStore((s) => s.selectedLocationId);
  const now = new Date();
  const [start, setStart] = useState(() => `${now.getFullYear()}-01-01`);
  const [end, setEnd] = useState(() => now.toISOString().slice(0, 10));

  const { data, isLoading } = useHstSummary({
    period_start: start,
    period_end: end,
    location_id: locationId ?? undefined,
  });
  const { mutate: backfill, isPending: backfilling } = useHstBackfill();

  const missing = data?.total_missing_tax_count ?? 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Receipt className="h-6 w-6 text-primary" /> HST / Tax
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Input Tax Credits (ITCs) — the HST/GST you paid on expenses, recoverable against
            HST collected on sales at filing time. Rolled up by month and quarter.
          </p>
        </div>
        <button
          onClick={() => backfill()}
          disabled={backfilling}
          className="flex items-center gap-1.5 px-3 py-2 text-sm border border-border rounded-md bg-card hover:bg-muted/50 disabled:opacity-50 cursor-pointer shrink-0"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${backfilling ? "animate-spin" : ""}`} />
          Backfill HST from older docs
        </button>
      </div>

      <div className="flex items-center gap-2 text-sm">
        <input
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          className="border border-border rounded-md px-2 py-1 bg-card"
        />
        <span className="text-muted-foreground">to</span>
        <input
          type="date"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
          className="border border-border rounded-md px-2 py-1 bg-card"
        />
      </div>

      {/* Headline: net remittance = collected − ITCs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs text-muted-foreground">HST collected on sales</p>
          <p className="text-2xl font-semibold mt-1">
            {isLoading ? "…" : money(data?.total_hst_collected ?? 0)}
          </p>
        </div>
        <div className="rounded-xl border border-primary/30 bg-primary/[0.04] p-4">
          <p className="text-xs text-muted-foreground">Recoverable HST (ITCs)</p>
          <p className="text-2xl font-semibold text-primary mt-1">
            {isLoading ? "…" : money(data?.total_hst ?? 0)}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-muted/40 p-4">
          <p className="text-xs text-muted-foreground">Net remittance (owe CRA)</p>
          <p className="text-2xl font-semibold mt-1">
            {isLoading ? "…" : money(data?.total_net_remittance ?? 0)}
          </p>
          <p className="text-xs text-muted-foreground mt-1">collected − ITCs</p>
        </div>
        {missing > 0 && (
          <Link
            href="/expenses?missing_tax=1"
            className="rounded-xl border border-amber-500/40 bg-amber-500/[0.05] p-4 block hover:bg-amber-500/[0.09] transition-colors"
          >
            <p className="text-xs text-amber-700 dark:text-amber-400 flex items-center gap-1">
              <AlertTriangle className="h-3.5 w-3.5" /> Expenses missing tax
            </p>
            <p className="text-2xl font-semibold mt-1">{missing}</p>
            <p className="text-xs text-muted-foreground mt-1">
              Mostly bank-statement rows — the invoice has the HST. Click to review →
            </p>
          </Link>
        )}
      </div>

      {/* Quarterly */}
      <Section title="By quarter" rows={data?.quarters ?? []} isLoading={isLoading} isQuarter />
      {/* Monthly */}
      <Section title="By month" rows={data?.months ?? []} isLoading={isLoading} />

      <p className="text-xs text-muted-foreground border-t border-border pt-4">
        Not tax advice. Restaurants: raw food purchases are often zero-rated (no HST to
        recover), while packaging, utilities, rent, software, and prepared goods usually
        carry recoverable HST. Confirm your net remittance with your CPA before filing.
      </p>
    </div>
  );
}

function Section({
  title,
  rows,
  isLoading,
  isQuarter = false,
}: {
  title: string;
  rows: HstPeriod[];
  isLoading: boolean;
  isQuarter?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className="px-4 py-2.5 border-b border-border bg-muted/30">
        <h2 className="text-sm font-medium">{title}</h2>
      </div>
      {isLoading ? (
        <div className="p-4 text-sm text-muted-foreground">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="p-4 text-sm text-muted-foreground">No expenses in this range.</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground text-left">
              <th className="px-4 py-2 font-medium">Period</th>
              <th className="px-4 py-2 font-medium text-right">HST collected</th>
              <th className="px-4 py-2 font-medium text-right">Recoverable (ITC)</th>
              <th className="px-4 py-2 font-medium text-right">Net remit</th>
              <th className="px-4 py-2 font-medium text-right">Expenses</th>
              <th className="px-4 py-2 font-medium text-right">Missing tax</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.period_label} className="border-t border-border">
                <td className="px-4 py-2 font-medium">
                  {isQuarter
                    ? `${r.year} Q${r.quarter} (${QUARTER_MONTHS[r.quarter]})`
                    : r.period_label}
                </td>
                <td className="px-4 py-2 text-right">{money(r.hst_collected)}</td>
                <td className="px-4 py-2 text-right font-medium text-primary">
                  {money(r.hst_total)}
                </td>
                <td className="px-4 py-2 text-right font-medium">{money(r.net_remittance)}</td>
                <td className="px-4 py-2 text-right text-muted-foreground">
                  {money(r.expense_total)}
                </td>
                <td className="px-4 py-2 text-right">
                  {r.missing_tax_count > 0 ? (
                    <Link
                      href="/expenses?missing_tax=1"
                      className="text-amber-600 dark:text-amber-400 underline underline-offset-2 hover:opacity-80"
                    >
                      {r.missing_tax_count}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
