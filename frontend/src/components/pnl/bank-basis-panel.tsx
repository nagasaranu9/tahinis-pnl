"use client";

import { useEffect, useState } from "react";
import { Loader2, Pencil, Check, X, Landmark } from "lucide-react";
import { useBankBasisPnL, usePartners, useSetPartners } from "@/hooks/use-pnl";
import type { BankBasisPnL, Partner } from "@/types/pnl";

function fmt(val: string | number | null | undefined): string {
  if (val == null) return "—";
  const n = typeof val === "number" ? val : parseFloat(val);
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    minimumFractionDigits: 2,
  }).format(n);
}

const CHANNEL_LABEL: Record<string, string> = {
  toast: "Toast (POS)",
  square: "Square / Tacit",
  uber: "Uber Eats",
  doordash: "DoorDash",
  skip: "Skip",
};

export function BankBasisPanel({
  periodStart,
  periodEnd,
}: {
  periodStart: string;
  periodEnd: string;
}) {
  const { data, isLoading } = useBankBasisPnL({ period_start: periodStart, period_end: periodEnd });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-6">
      <RevenueByChannel data={data} />
      <BeforeAfterHst data={data} />
      <HstSummary data={data} />
      <PartnerSplit data={data} />
      {parseFloat(data.principal_excluded) > 0 && (
        <p className="text-xs text-slate-500">
          Loan principal {fmt(data.principal_excluded)} excluded — balance-sheet movement, not a
          P&amp;L expense. Only interest ({fmt(data.interest)}) is a cost.
        </p>
      )}
    </div>
  );
}

function RevenueByChannel({ data }: { data: BankBasisPnL }) {
  const entries = Object.entries(data.revenue_by_channel).sort(
    (a, b) => parseFloat(b[1]) - parseFloat(a[1])
  );
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
        <Landmark className="h-4 w-4" /> Revenue — bank deposits (what landed)
      </div>
      <div className="flex flex-wrap gap-2">
        {entries.map(([ch, amt]) => (
          <span
            key={ch}
            className="rounded-lg bg-slate-100 px-3 py-1.5 text-sm dark:bg-slate-800"
          >
            <span className="text-slate-500 dark:text-slate-400">
              {CHANNEL_LABEL[ch] ?? ch}
            </span>{" "}
            <span className="font-semibold text-slate-800 dark:text-slate-100">{fmt(amt)}</span>
          </span>
        ))}
        <span className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white">
          Total {fmt(data.revenue)}
        </span>
      </div>
    </div>
  );
}

function Row({
  label,
  before,
  after,
  bold,
  accent,
}: {
  label: string;
  before: string;
  after: string;
  bold?: boolean;
  accent?: boolean;
}) {
  return (
    <tr className={accent ? "bg-slate-50 dark:bg-slate-800/50" : ""}>
      <td className={`py-2.5 pl-4 pr-2 text-sm ${bold ? "font-semibold text-slate-800 dark:text-slate-100" : "text-slate-600 dark:text-slate-300"}`}>
        {label}
      </td>
      <td className={`py-2.5 px-3 text-right text-sm tabular-nums ${bold ? "font-semibold text-slate-900 dark:text-white" : "text-slate-700 dark:text-slate-200"}`}>
        {fmt(before)}
      </td>
      <td className={`py-2.5 pl-3 pr-4 text-right text-sm tabular-nums ${bold ? "font-semibold text-slate-900 dark:text-white" : "text-slate-700 dark:text-slate-200"}`}>
        {fmt(after)}
      </td>
    </tr>
  );
}

function BeforeAfterHst({ data }: { data: BankBasisPnL }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <table className="w-full">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            <th className="py-3 pl-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
              Line
            </th>
            <th className="py-3 px-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
              Before HST
            </th>
            <th className="py-3 pl-3 pr-4 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
              After HST
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          <Row label="Revenue" before={data.before_hst.revenue} after={data.after_hst.revenue} bold />
          <Row label="COGS" before={data.cogs} after={data.cogs} />
          <Row label="Labor" before={data.labor} after={data.labor} />
          <Row label="Operating Expenses" before={data.operating_expenses} after={data.operating_expenses} />
          <Row label="EBITDA" before={data.before_hst.ebitda} after={data.after_hst.ebitda} bold accent />
          <Row label="Interest & Financing" before={data.interest} after={data.interest} />
          <Row label="Net Profit" before={data.before_hst.net_profit} after={data.after_hst.net_profit} bold accent />
        </tbody>
      </table>
    </div>
  );
}

function HstSummary({ data }: { data: BankBasisPnL }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {[
        ["HST collected on sales", data.hst.collected_on_sales],
        ["Input tax credits (ITC)", data.hst.input_tax_credits],
        ["Net HST owed to CRA", data.hst.net_remittance],
      ].map(([label, val], i) => (
        <div
          key={label}
          className={`rounded-xl border p-4 ${
            i === 2
              ? "border-amber-300 bg-amber-50 dark:border-amber-800/60 dark:bg-amber-950/30"
              : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
          }`}
        >
          <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-slate-900 dark:text-white">
            {fmt(val)}
          </div>
        </div>
      ))}
    </div>
  );
}

function PartnerSplit({ data }: { data: BankBasisPnL }) {
  const { data: partners } = usePartners();
  const setPartners = useSetPartners();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partner[]>([]);

  useEffect(() => {
    if (partners) setDraft(partners);
  }, [partners]);

  const draftTotal = draft.reduce((s, p) => s + (parseFloat(p.share_pct) || 0), 0);
  const canSave = Math.abs(draftTotal - 100) < 0.01;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Partner distribution
        </h3>
        {!editing ? (
          <button
            onClick={() => setEditing(true)}
            className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
          >
            <Pencil className="h-3.5 w-3.5" /> Edit shares
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className={`text-xs ${canSave ? "text-slate-400" : "text-red-500"}`}>
              {draftTotal.toFixed(1)}% / 100%
            </span>
            <button
              disabled={!canSave || setPartners.isPending}
              onClick={() => setPartners.mutate(draft, { onSuccess: () => setEditing(false) })}
              className="flex items-center gap-1 rounded-md bg-indigo-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
            >
              <Check className="h-3.5 w-3.5" /> Save
            </button>
            <button
              onClick={() => {
                setDraft(partners ?? []);
                setEditing(false);
              }}
              className="flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700"
            >
              <X className="h-3.5 w-3.5" /> Cancel
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          {draft.map((p, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                value={p.name}
                onChange={(e) => {
                  const next = [...draft];
                  next[i] = { ...next[i], name: e.target.value };
                  setDraft(next);
                }}
                className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="Partner name"
              />
              <input
                value={p.share_pct}
                onChange={(e) => {
                  const next = [...draft];
                  next[i] = { ...next[i], share_pct: e.target.value };
                  setDraft(next);
                }}
                className="w-20 rounded-md border border-slate-300 px-2 py-1 text-right text-sm tabular-nums dark:border-slate-700 dark:bg-slate-800"
                inputMode="decimal"
              />
              <span className="text-sm text-slate-400">%</span>
              <button
                onClick={() => setDraft(draft.filter((_, j) => j !== i))}
                className="text-slate-400 hover:text-red-500"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
          <button
            onClick={() => setDraft([...draft, { name: "", share_pct: "0" }])}
            className="text-xs text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
          >
            + Add partner
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                <th className="py-2 text-left">Partner</th>
                <th className="py-2 text-right">Revenue (before)</th>
                <th className="py-2 text-right">Revenue (after)</th>
                <th className="py-2 text-right">Net (before)</th>
                <th className="py-2 text-right">Net (after)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.partner_split.map((p) => (
                <tr key={p.name}>
                  <td className="py-2.5 text-sm font-medium text-slate-700 dark:text-slate-200">
                    {p.name}{" "}
                    <span className="text-xs text-slate-400">{parseFloat(p.share_pct)}%</span>
                  </td>
                  <td className="py-2.5 text-right text-sm tabular-nums text-slate-600 dark:text-slate-300">
                    {fmt(p.revenue_before_hst)}
                  </td>
                  <td className="py-2.5 text-right text-sm tabular-nums text-slate-600 dark:text-slate-300">
                    {fmt(p.revenue_after_hst)}
                  </td>
                  <td className="py-2.5 text-right text-sm tabular-nums text-slate-600 dark:text-slate-300">
                    {fmt(p.net_before_hst)}
                  </td>
                  <td className="py-2.5 text-right text-sm font-semibold tabular-nums text-slate-900 dark:text-white">
                    {fmt(p.net_after_hst)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
