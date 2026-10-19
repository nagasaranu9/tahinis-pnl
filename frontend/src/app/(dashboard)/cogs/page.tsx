"use client";

import { Fragment, useMemo, useState } from "react";
import { Upload, Trash2, ChevronRight, Loader2, FileSpreadsheet } from "lucide-react";
import { useCogsWeeks, useCogsWeek, useUploadCogs, useDeleteCogs, usePatchCogs } from "@/hooks/use-cogs";
import type { CogsItem } from "@/types/cogs";

function fmt(v: string | null | undefined): string {
  if (v == null) return "—";
  const n = parseFloat(v);
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { style: "currency", currency: "CAD" });
}

// Inventory is counted Sunday morning — default the count date to the upcoming
// Sunday (or today if it already is Sunday).
function nextSunday(): string {
  const d = new Date();
  d.setDate(d.getDate() + ((0 - d.getDay() + 7) % 7));
  return d.toISOString().slice(0, 10);
}

function UploadCard() {
  const upload = useUploadCogs();
  const [file, setFile] = useState<File | null>(null);
  const [weekEnding, setWeekEnding] = useState<string>(nextSunday());
  const [purchases, setPurchases] = useState("");
  const [netSales, setNetSales] = useState("");

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
        Upload weekly COGS sheet
      </h3>
      <p className="mb-4 text-xs text-slate-400">
        Count sheet (.xlsx). COGS = prior week&apos;s inventory + this week&apos;s purchases − this
        week&apos;s count. Purchases &amp; net sales auto-pull once synced; the sheet carries only the
        count, so enter purchases here (or edit later) for an accurate COGS %. Re-uploading replaces the week.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-[220px]">
          <span className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Inventory sheet</span>
          <input
            type="file"
            accept=".xlsx,.xlsm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-indigo-600 dark:text-slate-300 dark:file:bg-indigo-950/40 dark:file:text-indigo-300"
          />
        </label>
        <label>
          <span className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Count date (Sunday)</span>
          <input
            type="date"
            value={weekEnding}
            onChange={(e) => setWeekEnding(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800"
          />
        </label>
        <label>
          <span className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Purchases $ (week)</span>
          <input
            type="number" inputMode="decimal" placeholder="auto" value={purchases}
            onChange={(e) => setPurchases(e.target.value)}
            className="w-28 rounded-md border border-slate-300 px-2 py-1.5 text-right text-sm tabular-nums dark:border-slate-700 dark:bg-slate-800"
          />
        </label>
        <label>
          <span className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Net sales $</span>
          <input
            type="number" inputMode="decimal" placeholder="auto" value={netSales}
            onChange={(e) => setNetSales(e.target.value)}
            className="w-28 rounded-md border border-slate-300 px-2 py-1.5 text-right text-sm tabular-nums dark:border-slate-700 dark:bg-slate-800"
          />
        </label>
        <button
          disabled={!file || !weekEnding || upload.isPending}
          onClick={() => file && upload.mutate({ file, weekEnding, purchases: purchases || undefined, netSales: netSales || undefined })}
          className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          Upload
        </button>
      </div>
      {upload.isError && (
        <p className="mt-3 text-xs text-red-600 dark:text-red-400">
          {(upload.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
            "Upload failed."}
        </p>
      )}
      {upload.isSuccess && (
        <p className="mt-3 text-xs text-emerald-600 dark:text-emerald-400">
          Uploaded — week of {upload.data?.week_ending}. COGS{" "}
          {fmt(upload.data?.report.totals.cogs)}
          {upload.data && !upload.data.report.has_prior_week && " (no prior week — opening = 0, COGS reads high until next week chains)"}.
        </p>
      )}
    </div>
  );
}

function CategoryItems({ items }: { items: CogsItem[] }) {
  const byCat = useMemo(() => {
    const m = new Map<string, CogsItem[]>();
    for (const i of items) (m.get(i.category) ?? m.set(i.category, []).get(i.category)!).push(i);
    return [...m.entries()];
  }, [items]);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  return (
    <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
      {byCat.map(([cat, rows]) => {
        const total = rows.reduce((s, r) => s + parseFloat(r.extended_total), 0);
        const isOpen = !!open[cat];
        return (
          <div key={cat}>
            <button
              onClick={() => setOpen((o) => ({ ...o, [cat]: !o[cat] }))}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800/50"
            >
              <span className="inline-flex items-center gap-1 font-medium text-slate-700 dark:text-slate-200">
                <ChevronRight className={`h-3.5 w-3.5 transition-transform ${isOpen ? "rotate-90" : ""}`} />
                {cat} <span className="text-xs text-slate-400">({rows.length})</span>
              </span>
              <span className="tabular-nums text-slate-600 dark:text-slate-300">{fmt(String(total))}</span>
            </button>
            {isOpen && (
              <table className="w-full text-xs">
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td className="py-1.5 pl-8 pr-2 text-slate-600 dark:text-slate-300">{r.item_name}</td>
                      <td className="py-1.5 px-2 text-slate-400">{r.pack_size ?? ""}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-slate-400">
                        {r.unit_price ? fmt(r.unit_price) : ""}
                      </td>
                      <td className="py-1.5 pl-2 pr-3 text-right tabular-nums text-slate-700 dark:text-slate-200">
                        {fmt(r.extended_total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </div>
  );
}

function EditOverrides({ id, report }: { id: string; report: import("@/types/cogs").CogsReport }) {
  const patch = usePatchCogs();
  const [purch, setPurch] = useState(report.purchases_is_override ? report.totals.purchases : "");
  const [sales, setSales] = useState(report.net_sales_is_override ? report.net_sales : "");
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
      <label>
        <span className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
          Purchases $ {report.purchases_is_override ? "(manual)" : "(from sheet)"}
        </span>
        <input type="number" inputMode="decimal" placeholder="auto" value={purch}
          onChange={(e) => setPurch(e.target.value)}
          className="w-32 rounded-md border border-slate-300 px-2 py-1.5 text-right text-sm tabular-nums dark:border-slate-700 dark:bg-slate-800" />
      </label>
      <label>
        <span className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
          Net sales $ {report.net_sales_is_override ? "(manual)" : "(auto)"}
        </span>
        <input type="number" inputMode="decimal" placeholder="auto" value={sales}
          onChange={(e) => setSales(e.target.value)}
          className="w-32 rounded-md border border-slate-300 px-2 py-1.5 text-right text-sm tabular-nums dark:border-slate-700 dark:bg-slate-800" />
      </label>
      <button
        disabled={patch.isPending}
        onClick={() => patch.mutate({ id, purchases: purch === "" ? null : purch, net_sales: sales === "" ? null : sales })}
        className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
      >
        {patch.isPending ? "Saving…" : "Save & recalc"}
      </button>
      <span className="text-xs text-slate-400">Blank = auto (sheet / live revenue).</span>
    </div>
  );
}

function WeekDetail({ id }: { id: string }) {
  const { data, isLoading } = useCogsWeek(id);
  if (isLoading || !data) return <div className="p-4 text-sm text-slate-400">Loading…</div>;
  const r = data.report;
  return (
    <div className="space-y-4 bg-slate-50/60 p-4 dark:bg-slate-800/30">
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
              <th className="py-2 pl-4 text-left">Category</th>
              <th className="py-2 px-3 text-right">Opening</th>
              <th className="py-2 px-3 text-right">Purchases</th>
              <th className="py-2 px-3 text-right">Ending</th>
              <th className="py-2 pr-4 text-right">COGS</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {r.categories.map((c) => (
              <tr key={c.category}>
                <td className="py-2 pl-4 text-slate-700 dark:text-slate-200">{c.category}</td>
                <td className="py-2 px-3 text-right tabular-nums text-slate-500">{fmt(c.opening_inventory)}</td>
                <td className="py-2 px-3 text-right tabular-nums text-slate-500">{fmt(c.purchases)}</td>
                <td className="py-2 px-3 text-right tabular-nums text-slate-500">{fmt(c.ending_inventory)}</td>
                <td className="py-2 pr-4 text-right font-medium tabular-nums text-slate-900 dark:text-white">{fmt(c.cogs)}</td>
              </tr>
            ))}
            <tr className="bg-slate-50 font-semibold dark:bg-slate-800/50">
              <td className="py-2 pl-4 text-slate-800 dark:text-slate-100">Total</td>
              <td className="py-2 px-3 text-right tabular-nums">{fmt(r.totals.opening_inventory)}</td>
              <td className="py-2 px-3 text-right tabular-nums">{fmt(r.totals.purchases)}</td>
              <td className="py-2 px-3 text-right tabular-nums">{fmt(r.totals.ending_inventory)}</td>
              <td className="py-2 pr-4 text-right tabular-nums text-slate-900 dark:text-white">{fmt(r.totals.cogs)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-3 text-sm">
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-2 dark:border-slate-700 dark:bg-slate-900">
          <div className="text-xs text-slate-400">Net sales (7d)</div>
          <div className="font-semibold tabular-nums text-slate-900 dark:text-white">{fmt(r.net_sales)}</div>
        </div>
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 dark:border-amber-800/60 dark:bg-amber-950/30">
          <div className="text-xs text-slate-500 dark:text-slate-400">COGS %</div>
          <div className="font-semibold tabular-nums text-slate-900 dark:text-white">
            {r.totals.cogs_pct ? `${r.totals.cogs_pct}%` : "—"}
          </div>
        </div>
      </div>
      <EditOverrides id={id} report={r} />
      {!r.has_prior_week && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          First week — no prior count to open against (opening = 0), so COGS reads as the full count.
          Accurate from the next week once the chain has a prior.
        </p>
      )}
      <CategoryItems items={data.items} />
    </div>
  );
}

export default function CogsPage() {
  const { data: weeks, isLoading } = useCogsWeeks();
  const del = useDeleteCogs();
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white">COGS — Weekly Inventory</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Upload the weekly count sheet; COGS chains week-to-week against live net sales.
        </p>
      </div>

      <UploadCard />

      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="border-b border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 dark:border-slate-800 dark:text-slate-200">
          Weekly submissions
        </div>
        {isLoading ? (
          <div className="p-6 text-center text-sm text-slate-400">Loading…</div>
        ) : !weeks || weeks.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-10 text-center text-sm text-slate-400">
            <FileSpreadsheet className="h-8 w-8 opacity-40" />
            No submissions yet. Upload a sheet above.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                  <th className="py-2.5 pl-5 text-left">Week ending</th>
                  <th className="py-2.5 px-3 text-right">Net sales</th>
                  <th className="py-2.5 px-3 text-right">Ending inv.</th>
                  <th className="py-2.5 px-3 text-right">Purchases</th>
                  <th className="py-2.5 px-3 text-right">COGS</th>
                  <th className="py-2.5 px-3 text-right">COGS %</th>
                  <th className="py-2.5 pr-5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {weeks.map((w) => (
                  <Fragment key={w.id}>
                    <tr
                      className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40"
                      onClick={() => setOpenId(openId === w.id ? null : w.id)}
                    >
                      <td className="py-2.5 pl-5 font-medium text-slate-700 dark:text-slate-200">
                        <span className="inline-flex items-center gap-1">
                          <ChevronRight className={`h-3.5 w-3.5 transition-transform ${openId === w.id ? "rotate-90" : ""}`} />
                          {w.week_ending}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-slate-500">{fmt(w.net_sales)}</td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-slate-500">{fmt(w.totals.ending_inventory)}</td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-slate-500">{fmt(w.totals.purchases)}</td>
                      <td className="py-2.5 px-3 text-right font-medium tabular-nums text-slate-900 dark:text-white">{fmt(w.totals.cogs)}</td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-slate-600 dark:text-slate-300">
                        {w.totals.cogs_pct ? `${w.totals.cogs_pct}%` : "—"}
                      </td>
                      <td className="py-2.5 pr-5 text-right">
                        <button
                          onClick={(e) => { e.stopPropagation(); if (confirm(`Delete week ${w.week_ending}?`)) del.mutate(w.id); }}
                          className="text-slate-400 hover:text-red-500"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                    {openId === w.id && (
                      <tr>
                        <td colSpan={7} className="p-0">
                          <WeekDetail id={w.id} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
