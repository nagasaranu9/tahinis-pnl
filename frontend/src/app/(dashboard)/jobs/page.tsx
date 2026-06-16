"use client";

import { useState } from "react";
import { CheckCircle2, XCircle, Loader2, RefreshCw, Clock, AlertTriangle } from "lucide-react";
import { useJobs, useJobSummary, type JobRun } from "@/hooks/use-jobs";
import { useQueryClient } from "@tanstack/react-query";

// ─── Helpers ────────────────────────────────────────────────────────────────

function shortName(name: string): string {
  // "app.workers.tasks.toast_sync.run_all_tenants" → "toast_sync.run_all_tenants"
  const parts = name.split(".");
  return parts.length > 3 ? parts.slice(-2).join(".") : name;
}

function fmtDuration(seconds: string | null): string {
  if (!seconds) return "—";
  const s = parseFloat(seconds);
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${(s / 60).toFixed(1)}m`;
}

function fmtDatetime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-CA", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusBadge({ status }: { status: JobRun["status"] }) {
  const config = {
    success: { icon: CheckCircle2, label: "Success", cls: "text-green-400 bg-green-400/10" },
    failure: { icon: XCircle, label: "Failed", cls: "text-red-400 bg-red-400/10" },
    running: { icon: Loader2, label: "Running", cls: "text-blue-400 bg-blue-400/10", spin: true },
    pending: { icon: Clock, label: "Pending", cls: "text-yellow-400 bg-yellow-400/10" },
    retry: { icon: AlertTriangle, label: "Retry", cls: "text-orange-400 bg-orange-400/10" },
  }[status] ?? { icon: Clock, label: status, cls: "text-muted-foreground bg-muted", spin: false };

  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.cls}`}>
      <Icon className={`h-3 w-3 ${"spin" in config && config.spin ? "animate-spin" : ""}`} />
      {config.label}
    </span>
  );
}

// ─── Summary Cards ───────────────────────────────────────────────────────────

function SummaryCard({
  label,
  value,
  cls,
}: {
  label: string;
  value: number;
  cls: string;
}) {
  return (
    <div className="border border-border rounded-lg p-4 bg-card text-center">
      <p className={`text-2xl font-bold tabular-nums ${cls}`}>{value}</p>
      <p className="text-xs text-muted-foreground mt-1 uppercase tracking-wider">{label}</p>
    </div>
  );
}

// ─── Main ────────────────────────────────────────────────────────────────────

export default function JobsPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [nameFilter, setNameFilter] = useState("");
  const [page, setPage] = useState(1);

  const { data: summary } = useJobSummary();
  const { data, isLoading } = useJobs({
    status: statusFilter || undefined,
    task_name: nameFilter || undefined,
    page,
    limit: 50,
  });

  const jobs = data?.data ?? [];
  const total = data?.meta?.total ?? 0;
  const totalPages = Math.ceil(total / 50);

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Job Monitor</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Background sync, OCR, reconciliation, and AI tasks.
          </p>
        </div>
        <button
          onClick={() => {
            qc.invalidateQueries({ queryKey: ["jobs"] });
            qc.invalidateQueries({ queryKey: ["jobs-summary"] });
          }}
          className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-border bg-card text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <SummaryCard label="Total" value={summary.total} cls="text-foreground" />
          <SummaryCard label="Running" value={summary.running} cls="text-blue-400" />
          <SummaryCard label="Success" value={summary.success} cls="text-green-400" />
          <SummaryCard label="Failed" value={summary.failure} cls="text-red-400" />
          <SummaryCard label="Retry" value={summary.retry} cls="text-orange-400" />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="text-sm border border-border rounded-md px-3 py-2 bg-background text-foreground"
        >
          <option value="">All statuses</option>
          <option value="running">Running</option>
          <option value="success">Success</option>
          <option value="failure">Failed</option>
          <option value="retry">Retry</option>
          <option value="pending">Pending</option>
        </select>
        <input
          type="text"
          placeholder="Filter by task name…"
          value={nameFilter}
          onChange={(e) => { setNameFilter(e.target.value); setPage(1); }}
          className="text-sm border border-border rounded-md px-3 py-2 bg-background text-foreground w-64"
        />
        {(statusFilter || nameFilter) && (
          <button
            onClick={() => { setStatusFilter(""); setNameFilter(""); setPage(1); }}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-muted-foreground self-center ml-auto">
          {total} job{total !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg bg-card overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading…
          </div>
        ) : jobs.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            No jobs found.{" "}
            {statusFilter || nameFilter
              ? "Try clearing the filters."
              : "Jobs will appear here once background tasks run."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Task
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Status
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Started
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Duration
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Error
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job, i) => (
                  <tr
                    key={job.id}
                    className={`border-b border-border last:border-0 ${i % 2 === 0 ? "" : "bg-muted/10"}`}
                  >
                    <td className="px-4 py-3">
                      <p className="font-medium text-foreground font-mono text-xs">
                        {shortName(job.task_name)}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5 font-mono">
                        {job.celery_task_id.slice(0, 8)}…
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {fmtDatetime(job.started_at ?? job.created_at)}
                    </td>
                    <td className="px-4 py-3 text-xs font-mono text-muted-foreground">
                      {fmtDuration(job.duration_seconds)}
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      {job.error_message ? (
                        <p className="text-xs text-red-400 truncate" title={job.error_message}>
                          {job.error_message}
                        </p>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-xs rounded border border-border disabled:opacity-40 hover:bg-accent transition-colors"
          >
            Previous
          </button>
          <span className="text-xs text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-xs rounded border border-border disabled:opacity-40 hover:bg-accent transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
