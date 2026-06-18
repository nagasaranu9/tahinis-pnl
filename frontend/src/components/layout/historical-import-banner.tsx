"use client";

import Link from "next/link";
import { Loader2, AlertTriangle, RefreshCw } from "lucide-react";
import { useLocations } from "@/hooks/use-locations";
import { useToastStatus, useTriggerSync } from "@/hooks/use-toast-integration";

/**
 * Persistent top banner for the Toast historical import. Stays visible on every
 * dashboard page until the backfill completes, so the operator always knows the
 * import state and can retry a stalled/failed run from anywhere.
 */
export function HistoricalImportBanner() {
  const { selectedLocationId } = useLocations();
  const { data: status } = useToastStatus(selectedLocationId ?? undefined);
  const { mutate: triggerSync, isPending: triggering } = useTriggerSync();

  // Nothing to show once complete, or when Toast isn't connected.
  if (!status || !status.is_active || status.historical_import_complete) return null;

  const s = status.historical_status;
  const orders = status.historical_orders_synced ?? 0;

  // Stalled = a job was started but isn't progressing (worker down). Treat a
  // pending job with no started_at, or a failed job, as actionable.
  const isRunning = s === "running";
  const isFailed = s === "failed";
  const startedAt = status.historical_started_at;
  // pending for a while with no start => likely stuck (worker not consuming)
  const isStalled =
    s === "pending" &&
    !startedAt;

  function retry() {
    if (selectedLocationId) {
      triggerSync({ location_id: selectedLocationId, sync_type: "historical" });
    }
  }

  return (
    <div
      className={`flex items-center gap-3 px-4 py-2.5 text-sm border-b ${
        isFailed
          ? "bg-destructive/10 border-destructive/30 text-destructive"
          : isStalled
            ? "bg-yellow-500/10 border-yellow-500/30 text-yellow-700 dark:text-yellow-400"
            : "bg-primary/10 border-primary/20 text-primary"
      }`}
    >
      {isRunning ? (
        <Loader2 className="h-4 w-4 animate-spin shrink-0" />
      ) : isFailed || isStalled ? (
        <AlertTriangle className="h-4 w-4 shrink-0" />
      ) : (
        <Loader2 className="h-4 w-4 animate-spin shrink-0" />
      )}

      <div className="flex-1 min-w-0">
        {isRunning && (
          <span>
            Toast historical import running — {orders.toLocaleString()} orders imported so far. Revenue
            will populate as it finishes.
          </span>
        )}
        {isFailed && (
          <span>
            Toast historical import failed{status.historical_error ? `: ${status.historical_error}` : ""}.
            Retry below.
          </span>
        )}
        {isStalled && (
          <span>
            Toast historical import queued but not progressing (sync worker may be down). Retry, or
            check the worker service.
          </span>
        )}
        {!isRunning && !isFailed && !isStalled && (
          <span>Toast historical import in progress…</span>
        )}
      </div>

      {(isFailed || isStalled || s == null) && (
        <button
          onClick={retry}
          disabled={triggering}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-md border border-current/30 hover:bg-current/10 disabled:opacity-50 transition-colors shrink-0"
        >
          <RefreshCw className={`h-3 w-3 ${triggering ? "animate-spin" : ""}`} />
          Retry import
        </button>
      )}
      <Link
        href="/integrations/toast"
        className="text-xs font-medium underline hover:no-underline shrink-0"
      >
        Details
      </Link>
    </div>
  );
}
