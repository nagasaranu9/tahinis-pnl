"use client";

import { useState } from "react";
import { format } from "date-fns";
import { AlertTriangle, CheckCircle, Loader2, Play, ShieldCheck, XCircle } from "lucide-react";
import {
  useReconciliationRuns,
  useTriggerReconciliation,
  useReconciliationFlags,
  useResolveFlag,
} from "@/hooks/use-reconciliation";
import { useLocationStore } from "@/lib/location-store";
import type { FlagSeverity, FlagType, ReconciliationRun } from "@/types/reconciliation";

const SEVERITY_STYLES: Record<FlagSeverity, string> = {
  low: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  medium: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  high: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  critical: "bg-red-500/10 text-red-400 border-red-500/20",
};

const FLAG_LABELS: Record<FlagType, string> = {
  missing_invoice: "Missing Invoice",
  duplicate_invoice: "Duplicate Invoice",
  duplicate_expense: "Duplicate Expense",
  uncategorized_expense: "Uncategorized",
  suspicious_amount: "Suspicious Amount",
  unmatched_sale: "Unmatched Sale",
  unverified_payroll: "Unverified Payroll",
};

function StatusBadge({ status }: { status: ReconciliationRun["status"] }) {
  const map = {
    pending: { icon: <Loader2 className="h-3 w-3 animate-spin" />, label: "Pending", cls: "text-muted-foreground" },
    running: { icon: <Loader2 className="h-3 w-3 animate-spin" />, label: "Running", cls: "text-blue-400" },
    complete: { icon: <CheckCircle className="h-3 w-3" />, label: "Complete", cls: "text-green-400" },
    failed: { icon: <XCircle className="h-3 w-3" />, label: "Failed", cls: "text-destructive" },
  };
  const s = map[status];
  return (
    <span className={`flex items-center gap-1 text-xs font-medium ${s.cls}`}>
      {s.icon} {s.label}
    </span>
  );
}

function TriggerForm({ onSubmit, loading }: { onSubmit: (start: string, end: string) => void; loading: boolean }) {
  const [start, setStart] = useState(() => {
    const d = new Date(); d.setDate(1);
    return d.toISOString().slice(0, 10);
  });
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10));

  return (
    <div className="border border-border rounded-lg p-4 flex flex-wrap gap-3 items-end bg-card">
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Period start</label>
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
          className="text-sm border border-input rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
      </div>
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">Period end</label>
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
          className="text-sm border border-input rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
      </div>
      <button
        onClick={() => onSubmit(`${start}T00:00:00Z`, `${end}T23:59:59Z`)}
        disabled={loading || !start || !end}
        className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold bg-primary text-primary-foreground rounded-md disabled:opacity-50 hover:bg-primary/90 transition-colors"
      >
        <Play className="h-3.5 w-3.5" />
        {loading ? "Queuing…" : "Run Reconciliation"}
      </button>
    </div>
  );
}

function FlagRow({ flag, onResolve }: { flag: import("@/types/reconciliation").ReconciliationFlag; onResolve: (id: string, note: string) => void }) {
  const [note, setNote] = useState("");
  const [showInput, setShowInput] = useState(false);

  return (
    <div className={`border border-border rounded-lg p-3 text-sm space-y-2 bg-card ${flag.is_resolved ? "opacity-50" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-1">
          <span className={`text-xs px-2 py-0.5 rounded border font-medium ${SEVERITY_STYLES[flag.severity]}`}>
            {flag.severity.toUpperCase()}
          </span>
          <span className="font-medium">{FLAG_LABELS[flag.flag_type] ?? flag.flag_type}</span>
        </div>
        {flag.is_resolved ? (
          <span className="flex items-center gap-1 text-xs text-green-400">
            <ShieldCheck className="h-3.5 w-3.5" /> Resolved
          </span>
        ) : (
          <button onClick={() => setShowInput(!showInput)}
            className="text-xs px-2 py-1 border border-border rounded-md hover:bg-accent transition-colors">
            Resolve
          </button>
        )}
      </div>
      <p className="text-muted-foreground text-xs leading-relaxed">{flag.message}</p>
      {showInput && !flag.is_resolved && (
        <div className="flex gap-2 pt-1">
          <input
            type="text"
            placeholder="Resolution note…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="flex-1 text-xs border border-input rounded-md px-2 py-1 bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <button
            onClick={() => { onResolve(flag.id, note); setShowInput(false); }}
            disabled={!note}
            className="text-xs px-3 py-1 bg-primary text-primary-foreground rounded disabled:opacity-50"
          >
            Save
          </button>
        </div>
      )}
    </div>
  );
}

export default function ReconciliationPage() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [unresolvedOnly, setUnresolvedOnly] = useState(true);
  const locationId = useLocationStore((s) => s.selectedLocationId);

  const { data: runsData, isLoading: runsLoading } = useReconciliationRuns({
    location_id: locationId ?? undefined,
  });
  const { mutate: triggerRun, isPending: triggering } = useTriggerReconciliation();
  const { data: flagsData } = useReconciliationFlags({
    run_id: selectedRunId ?? undefined,
    unresolved_only: unresolvedOnly,
  });
  const { mutate: resolveFlag } = useResolveFlag();

  const runs = runsData?.data ?? [];

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Reconciliation</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Match Toast sales, invoices, and expenses. Review and resolve flags.
        </p>
      </div>

      <TriggerForm
        loading={triggering}
        onSubmit={(start, end) =>
          triggerRun({ period_start: start, period_end: end })
        }
      />

      {runsLoading ? (
        <p className="text-sm text-muted-foreground">Loading runs…</p>
      ) : runs.length === 0 ? (
        <div className="border rounded-lg p-8 text-center text-sm text-muted-foreground">
          <AlertTriangle className="h-8 w-8 mx-auto mb-2 opacity-30" />
          No reconciliation runs yet.
        </div>
      ) : (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold">Recent Runs</h2>
          {runs.map((run) => (
            <button
              key={run.id}
              onClick={() => setSelectedRunId(run.id === selectedRunId ? null : run.id)}
              className={`w-full text-left border rounded-lg p-3 bg-card hover:bg-accent transition-colors ${
                selectedRunId === run.id ? "border-primary/60" : "border-border"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="text-sm">
                  <span className="font-medium">
                    {format(new Date(run.period_start), "MMM d")} – {format(new Date(run.period_end), "MMM d, yyyy")}
                  </span>
                </div>
                <StatusBadge status={run.status} />
              </div>
              {run.status === "complete" && (
                <div className="mt-1 flex gap-4 text-xs text-muted-foreground">
                  <span>{run.documents_checked} docs</span>
                  <span>{run.expenses_checked} expenses</span>
                  <span>{run.toast_orders_checked} orders</span>
                  <span className={run.flags_raised > 0 ? "text-orange-400 font-medium" : ""}>
                    {run.flags_raised} flags
                  </span>
                  {run.net_variance !== null && (
                    <span className={parseFloat(run.net_variance) < 0 ? "text-red-400" : "text-green-400"}>
                      Variance: {parseFloat(run.net_variance ?? "0").toFixed(2)}
                    </span>
                  )}
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {selectedRunId && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Flags</h2>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="checkbox" checked={unresolvedOnly} onChange={(e) => setUnresolvedOnly(e.target.checked)} />
              Unresolved only
            </label>
          </div>
          {flagsData?.data.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-4">
              No flags for this run.
            </div>
          ) : (
            flagsData?.data.map((flag) => (
              <FlagRow
                key={flag.id}
                flag={flag}
                onResolve={(id, note) => resolveFlag({ flagId: id, note })}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
