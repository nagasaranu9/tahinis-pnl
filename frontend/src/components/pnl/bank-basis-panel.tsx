"use client";

import { useEffect, useState, Fragment } from "react";
import { Loader2, Pencil, Check, X, Landmark, Car, ChevronRight } from "lucide-react";
import {
  useBankBasisPnL,
  usePartners,
  useSetPartners,
  usePartnerDraws,
  useSetPartnerDraws,
} from "@/hooks/use-pnl";
import type { BankBasisPnL, ExpenseLine, Partner } from "@/types/pnl";

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
      <PartnerSplit data={data} periodStart={periodStart} periodEnd={periodEnd} />
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

// Opex drilldown grouped by category (Royalties, Utilities, Miscellaneous, …).
// Each category is a collapsible subgroup: header shows total + count, click to
// reveal the individual bank lines.
function GroupedLines({ lines }: { lines: ExpenseLine[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const groups = new Map<string, ExpenseLine[]>();
  for (const ln of lines) {
    const c = ln.category || "Uncategorized";
    (groups.get(c) ?? groups.set(c, []).get(c)!).push(ln);
  }
  const ordered = [...groups.entries()].sort(
    (a, b) =>
      b[1].reduce((s, l) => s + parseFloat(l.amount), 0) -
      a[1].reduce((s, l) => s + parseFloat(l.amount), 0)
  );
  return (
    <table className="w-full">
      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
        {ordered.map(([cat, items]) => {
          const total = items.reduce((s, l) => s + parseFloat(l.amount), 0);
          const isOpen = !!open[cat];
          return (
            <Fragment key={cat}>
              <tr className="bg-slate-100/70 dark:bg-slate-800/50">
                <td colSpan={3} className="py-1.5 pl-3 pr-2">
                  <button
                    onClick={() => setOpen((o) => ({ ...o, [cat]: !o[cat] }))}
                    className="inline-flex items-center gap-1 text-xs font-medium text-slate-700 hover:text-indigo-600 dark:text-slate-200 dark:hover:text-indigo-400"
                  >
                    <ChevronRight
                      className={`h-3 w-3 transition-transform ${isOpen ? "rotate-90" : ""}`}
                    />
                    {cat}
                    <span className="text-slate-400">({items.length})</span>
                  </button>
                </td>
                <td className="py-1.5 pl-2 pr-3 text-right text-xs font-semibold tabular-nums text-slate-800 dark:text-slate-100">
                  {fmt(total)}
                </td>
              </tr>
              {isOpen &&
                items.map((ln, i) => (
                  <tr key={i}>
                    <td className="py-1.5 pl-6 pr-2 text-xs text-slate-500 dark:text-slate-400">
                      {ln.date ?? ""}
                    </td>
                    <td className="py-1.5 px-2 text-xs text-slate-700 dark:text-slate-200" colSpan={2}>
                      {ln.vendor_name ?? "—"}
                    </td>
                    <td className="py-1.5 pl-2 pr-3 text-right text-xs tabular-nums text-slate-700 dark:text-slate-200">
                      {fmt(ln.amount)}
                    </td>
                  </tr>
                ))}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

function Row({
  label,
  before,
  after,
  bold,
  accent,
  revBase,
  lines,
  expanded,
  onToggle,
  grouped,
}: {
  label: string;
  before: string;
  after: string;
  bold?: boolean;
  accent?: boolean;
  revBase?: number;
  lines?: ExpenseLine[];
  expanded?: boolean;
  onToggle?: () => void;
  grouped?: boolean;
}) {
  const pct = (v: string) =>
    revBase && revBase !== 0 ? ` (${((parseFloat(v) / revBase) * 100).toFixed(1)}%)` : "";
  const expandable = !!lines && lines.length > 0;
  return (
    <>
      <tr className={accent ? "bg-slate-50 dark:bg-slate-800/50" : ""}>
        <td className={`py-2.5 pl-4 pr-2 text-sm ${bold ? "font-semibold text-slate-800 dark:text-slate-100" : "text-slate-600 dark:text-slate-300"}`}>
          {expandable ? (
            <button
              onClick={onToggle}
              className="inline-flex items-center gap-1 hover:text-indigo-600 dark:hover:text-indigo-400"
            >
              <ChevronRight
                className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-90" : ""}`}
              />
              {label}
            </button>
          ) : (
            label
          )}
        </td>
        <td className={`py-2.5 px-3 text-right text-sm tabular-nums ${bold ? "font-semibold text-slate-900 dark:text-white" : "text-slate-700 dark:text-slate-200"}`}>
          {fmt(before)}
          <span className="text-xs font-normal text-slate-400">{pct(before)}</span>
        </td>
        <td className={`py-2.5 pl-3 pr-4 text-right text-sm tabular-nums ${bold ? "font-semibold text-slate-900 dark:text-white" : "text-slate-700 dark:text-slate-200"}`}>
          {fmt(after)}
        </td>
      </tr>
      {expandable && expanded && (
        <tr className="bg-slate-50/60 dark:bg-slate-800/30">
          <td colSpan={3} className="px-4 py-2">
            <div className="max-h-72 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700">
              {grouped ? (
                <GroupedLines lines={lines!} />
              ) : (
                <table className="w-full">
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {lines!.map((ln, i) => (
                      <tr key={i}>
                        <td className="py-1.5 pl-3 pr-2 text-xs text-slate-500 dark:text-slate-400">
                          {ln.date ?? ""}
                        </td>
                        <td className="py-1.5 px-2 text-xs text-slate-700 dark:text-slate-200">
                          {ln.vendor_name ?? "—"}
                        </td>
                        <td className="py-1.5 px-2 text-xs text-slate-400">{ln.category}</td>
                        <td className="py-1.5 pl-2 pr-3 text-right text-xs tabular-nums text-slate-700 dark:text-slate-200">
                          {fmt(ln.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function BeforeAfterHst({ data }: { data: BankBasisPnL }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (k: string) => setOpen((o) => ({ ...o, [k]: !o[k] }));
  const revBase = parseFloat(data.before_hst.revenue);
  const el = data.expense_lines;
  return (
    <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
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
          <Row label="COGS" before={data.cogs} after={data.cogs} revBase={revBase}
            lines={el?.cogs} expanded={open.cogs} onToggle={() => toggle("cogs")} />
          <Row label="Labor" before={data.labor} after={data.labor} revBase={revBase}
            lines={el?.labor} expanded={open.labor} onToggle={() => toggle("labor")} />
          <Row label="Operating Expenses" before={data.operating_expenses} after={data.operating_expenses} revBase={revBase}
            lines={el?.opex} expanded={open.opex} onToggle={() => toggle("opex")} grouped />
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

function PartnerSplit({
  data,
  periodStart,
  periodEnd,
}: {
  data: BankBasisPnL;
  periodStart: string;
  periodEnd: string;
}) {
  const { data: partners } = usePartners();
  const setPartners = useSetPartners();
  const { data: savedDraws } = usePartnerDraws({ period_start: periodStart, period_end: periodEnd });
  const setDraws = useSetPartnerDraws();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partner[]>([]);
  // Manual draw inputs keyed by partner name (strings so the field can be blank).
  const [drawInputs, setDrawInputs] = useState<Record<string, string>>({});

  useEffect(() => {
    if (partners) setDraft(partners);
  }, [partners]);
  useEffect(() => {
    if (savedDraws) setDrawInputs(savedDraws);
  }, [savedDraws]);

  const draftTotal = draft.reduce((s, p) => s + (parseFloat(p.share_pct) || 0), 0);
  const canSave = Math.abs(draftTotal - 100) < 0.01;

  const drawsDirty =
    JSON.stringify(
      Object.fromEntries(
        data.partner_split.map((p) => [p.name, (drawInputs[p.name] ?? "").trim()])
      )
    ) !==
    JSON.stringify(
      Object.fromEntries(data.partner_split.map((p) => [p.name, savedDraws?.[p.name] ?? ""]))
    );

  function saveDraws() {
    const draws: Record<string, string> = {};
    for (const p of data.partner_split) {
      const v = (drawInputs[p.name] ?? "").trim();
      draws[p.name] = v === "" ? "0" : v;
    }
    setDraws.mutate({ period_start: periodStart, period_end: periodEnd, draws });
  }

  // Quarter-to-date + year-to-date roll-ups (from the same endpoint). Look up a
  // partner's net in a given roll-up for each HST basis.
  const q = data.quarter;
  const y = data.ytd;
  const findRow = (rep: BankBasisPnL | undefined, name: string) =>
    rep?.partner_split.find((x) => x.name === name);
  const netAfter = (rep: BankBasisPnL | undefined, name: string) => {
    const r = findRow(rep, name);
    return r ? parseFloat(r.net_after_hst) : null;
  };
  const netBefore = (rep: BankBasisPnL | undefined, name: string) => {
    const r = findRow(rep, name);
    return r ? parseFloat(r.net_before_hst) : null;
  };
  const roll33 = (rep: BankBasisPnL | undefined, sharePct: string) => {
    if (!rep) return null;
    const remit = parseFloat(rep.hst.collected_on_sales) * 0.33;
    const netCo = parseFloat(rep.before_hst.net_profit) - remit;
    return netCo * (parseFloat(sharePct) / 100);
  };
  const rollCell = (v: number | null) => (
    <td className="py-2.5 text-right text-sm tabular-nums text-slate-500 dark:text-slate-400">
      {v == null ? "—" : fmt(v)}
    </td>
  );

  return (
    <div className="space-y-6">
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Partner distribution (After HST)
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
              <label className="flex items-center gap-1 text-xs text-slate-500" title="Company car charged to this partner">
                <input
                  type="checkbox"
                  checked={!!p.gets_vehicle}
                  onChange={(e) => {
                    const next = draft.map((d, j) => ({ ...d, gets_vehicle: j === i ? e.target.checked : false }));
                    setDraft(next);
                  }}
                />
                <Car className="h-3.5 w-3.5" />
              </label>
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
                <th className="py-2 text-right">Net (after HST)</th>
                <th className="py-2 text-right">QTD</th>
                <th className="py-2 text-right">YTD</th>
                <th className="py-2 text-right">Draw taken</th>
                <th className="py-2 text-right">Car</th>
                <th className="py-2 text-right">Remaining</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.partner_split.map((p) => {
                const rem = parseFloat(p.remaining ?? p.net_after_hst);
                return (
                  <tr key={p.name}>
                    <td className="py-2.5 text-sm font-medium text-slate-700 dark:text-slate-200">
                      {p.name}{" "}
                      <span className="text-xs text-slate-400">{parseFloat(p.share_pct)}%</span>
                    </td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-600 dark:text-slate-300">
                      {fmt(p.net_after_hst)}
                    </td>
                    {rollCell(netAfter(q, p.name))}
                    {rollCell(netAfter(y, p.name))}
                    <td className="py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <span className="text-xs text-slate-400">$</span>
                        <input
                          value={drawInputs[p.name] ?? ""}
                          onChange={(e) =>
                            setDrawInputs({ ...drawInputs, [p.name]: e.target.value })
                          }
                          placeholder="0.00"
                          inputMode="decimal"
                          className="w-24 rounded-md border border-slate-300 px-2 py-1 text-right text-sm tabular-nums dark:border-slate-700 dark:bg-slate-800"
                        />
                      </div>
                    </td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-500 dark:text-slate-400">
                      {parseFloat(p.vehicle_draw ?? "0") > 0 ? (
                        <span className="inline-flex items-center gap-1">
                          <Car className="h-3.5 w-3.5" /> {fmt(p.vehicle_draw)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td
                      className={`py-2.5 text-right text-sm font-semibold tabular-nums ${
                        rem < 0 ? "text-red-600 dark:text-red-400" : "text-slate-900 dark:text-white"
                      }`}
                    >
                      {fmt(p.remaining ?? p.net_after_hst)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs text-slate-400">
              Remaining = share of net profit (after HST) − draw taken − car. QTD = quarter-to-date, YTD = year-to-date.
            </p>
            {drawsDirty && (
              <button
                disabled={setDraws.isPending}
                onClick={saveDraws}
                className="flex items-center gap-1 rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-40"
              >
                <Check className="h-3.5 w-3.5" /> Save draws
              </button>
            )}
          </div>
        </div>
      )}
    </div>

    {!editing && (
      <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Partner distribution (Before HST)
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                <th className="py-2 text-left">Partner</th>
                <th className="py-2 text-right">Net (before HST)</th>
                <th className="py-2 text-right">QTD</th>
                <th className="py-2 text-right">YTD</th>
                <th className="py-2 text-right">Draw taken</th>
                <th className="py-2 text-right">Car</th>
                <th className="py-2 text-right">Remaining</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.partner_split.map((p) => {
                const rem = parseFloat(p.remaining_before ?? p.net_before_hst);
                return (
                  <tr key={p.name}>
                    <td className="py-2.5 text-sm font-medium text-slate-700 dark:text-slate-200">
                      {p.name}{" "}
                      <span className="text-xs text-slate-400">{parseFloat(p.share_pct)}%</span>
                    </td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-600 dark:text-slate-300">
                      {fmt(p.net_before_hst)}
                    </td>
                    {rollCell(netBefore(q, p.name))}
                    {rollCell(netBefore(y, p.name))}
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-500 dark:text-slate-400">
                      {parseFloat(p.manual_draw ?? "0") > 0 ? fmt(p.manual_draw) : "—"}
                    </td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-500 dark:text-slate-400">
                      {parseFloat(p.vehicle_draw ?? "0") > 0 ? (
                        <span className="inline-flex items-center gap-1">
                          <Car className="h-3.5 w-3.5" /> {fmt(p.vehicle_draw)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td
                      className={`py-2.5 text-right text-sm font-semibold tabular-nums ${
                        rem < 0 ? "text-red-600 dark:text-red-400" : "text-slate-900 dark:text-white"
                      }`}
                    >
                      {fmt(p.remaining_before ?? p.net_before_hst)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-slate-400">
            Same draws as above; net is the pre-HST share (before the CRA remittance).
          </p>
        </div>
      </div>
    )}

    {!editing && (
      <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Partner distribution (33% HST remitted)
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                <th className="py-2 text-left">Partner</th>
                <th className="py-2 text-right">Net (33% HST)</th>
                <th className="py-2 text-right">QTD</th>
                <th className="py-2 text-right">YTD</th>
                <th className="py-2 text-right">Draw taken</th>
                <th className="py-2 text-right">Car</th>
                <th className="py-2 text-right">Remaining</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.partner_split.map((p) => {
                // Only 33% of collected HST is remitted (ITC/expenses cover the rest).
                const remit33 = parseFloat(data.hst.collected_on_sales) * 0.33;
                const netCompany33 = parseFloat(data.before_hst.net_profit) - remit33;
                const frac = parseFloat(p.share_pct) / 100;
                const net33 = netCompany33 * frac;
                const draw =
                  parseFloat(p.manual_draw ?? "0") + parseFloat(p.vehicle_draw ?? "0");
                const rem = net33 - draw;
                return (
                  <tr key={p.name}>
                    <td className="py-2.5 text-sm font-medium text-slate-700 dark:text-slate-200">
                      {p.name}{" "}
                      <span className="text-xs text-slate-400">{parseFloat(p.share_pct)}%</span>
                    </td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-600 dark:text-slate-300">
                      {fmt(net33)}
                    </td>
                    {rollCell(roll33(q, p.share_pct))}
                    {rollCell(roll33(y, p.share_pct))}
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-500 dark:text-slate-400">
                      {parseFloat(p.manual_draw ?? "0") > 0 ? fmt(p.manual_draw) : "—"}
                    </td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-500 dark:text-slate-400">
                      {parseFloat(p.vehicle_draw ?? "0") > 0 ? (
                        <span className="inline-flex items-center gap-1">
                          <Car className="h-3.5 w-3.5" /> {fmt(p.vehicle_draw)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td
                      className={`py-2.5 text-right text-sm font-semibold tabular-nums ${
                        rem < 0 ? "text-red-600 dark:text-red-400" : "text-slate-900 dark:text-white"
                      }`}
                    >
                      {fmt(rem)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-slate-400">
            Only 33% of collected HST is remitted (ITC/expenses cover the rest):
            pre-HST net − (HST collected × 33%), split by share, minus draws.
          </p>
        </div>
      </div>
    )}
    </div>
  );
}
