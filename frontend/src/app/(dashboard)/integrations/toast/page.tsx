"use client";

import { useState } from "react";
import { format } from "date-fns";
import { CheckCircle, RefreshCw, Plug, AlertCircle, Unplug, Layers } from "lucide-react";
import {
  useToastStatus,
  useConnectToast,
  useTriggerSync,
  useDisconnectToast,
  useBackfillChannels,
  useSyncJobs,
} from "@/hooks/use-toast-integration";
import { useLocationStore } from "@/lib/location-store";
import type { ToastSyncJob } from "@/types/toast";

const JOB_STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-500/10 text-yellow-400",
  running: "bg-blue-500/10 text-blue-400 animate-pulse",
  complete: "bg-green-500/10 text-green-400",
  failed: "bg-red-500/10 text-red-400",
};

function SyncJobRow({ job }: { job: ToastSyncJob }) {
  return (
    <tr className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors">
      <td className="px-4 py-2 capitalize text-sm">{job.job_type}</td>
      <td className="px-4 py-2">
        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${JOB_STATUS_COLORS[job.status] ?? "bg-muted text-muted-foreground"}`}>
          {job.status}
        </span>
      </td>
      <td className="px-4 py-2 text-sm text-muted-foreground">
        {job.started_at ? format(new Date(job.started_at), "MMM d, HH:mm") : "—"}
      </td>
      <td className="px-4 py-2 text-sm">{job.orders_synced.toLocaleString()}</td>
      <td className="px-4 py-2 text-sm">{job.time_entries_synced.toLocaleString()}</td>
      <td className="px-4 py-2 text-sm text-destructive truncate max-w-[200px]" title={job.error_message ?? ""}>
        {job.error_message ?? "—"}
      </td>
    </tr>
  );
}

export default function ToastIntegrationPage() {
  const locationId = useLocationStore((s) => s.selectedLocationId) ?? "";
  const [showConnectForm, setShowConnectForm] = useState(false);
  const [form, setForm] = useState({
    client_id: "",
    client_secret: "",
    toast_restaurant_guid: "",
    historical_import_from: "",
  });

  const { data: status, isLoading: statusLoading } = useToastStatus(locationId || undefined);
  const { data: jobsData, isLoading: jobsLoading } = useSyncJobs(locationId || undefined);
  const { mutate: connect, isPending: connecting, error: connectError } = useConnectToast();
  const { mutate: triggerSync, isPending: syncing } = useTriggerSync();
  const { mutate: disconnect, isPending: disconnecting } = useDisconnectToast();
  const {
    mutate: backfillChannels,
    isPending: backfilling,
    data: backfillResult,
  } = useBackfillChannels();

  function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    if (!locationId) return;
    connect(
      {
        location_id: locationId,
        ...form,
        historical_import_from: form.historical_import_from || undefined,
      },
      { onSuccess: () => setShowConnectForm(false) }
    );
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Toast POS</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Connect your Toast account to import sales, labor, and menu data.
        </p>
      </div>

      {/* Connection status card */}
      <div className="border border-border rounded-lg p-6 bg-card space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {status?.is_active ? (
              <CheckCircle className="h-5 w-5 text-green-400" />
            ) : (
              <Plug className="h-5 w-5 text-muted-foreground" />
            )}
            <div>
              <p className="font-medium">
                {status?.is_active ? "Connected" : "Not connected"}
              </p>
              {status && (
                <p className="text-xs text-muted-foreground">
                  Restaurant GUID: {status.toast_restaurant_guid}
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            {status?.is_active ? (
              <>
                <button
                  onClick={() => triggerSync({ location_id: locationId, sync_type: "incremental" })}
                  disabled={syncing}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-border rounded-md hover:bg-muted/50 disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
                  Sync now
                </button>
                <button
                  onClick={() => backfillChannels(locationId)}
                  disabled={backfilling || !locationId}
                  title="Repopulate revenue-by-channel labels on existing orders"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-border rounded-md hover:bg-muted/50 disabled:opacity-50 transition-colors"
                >
                  <Layers className={`h-3.5 w-3.5 ${backfilling ? "animate-pulse" : ""}`} />
                  Backfill channels
                </button>
                {!status.historical_import_complete && (
                  <button
                    onClick={() => triggerSync({ location_id: locationId, sync_type: "historical" })}
                    disabled={syncing}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-primary text-primary rounded-md hover:bg-primary/10 disabled:opacity-50 transition-colors"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
                    Run historical import
                  </button>
                )}
                <button
                  onClick={() => disconnect(locationId)}
                  disabled={disconnecting}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-destructive text-destructive rounded hover:bg-destructive/10 disabled:opacity-50"
                >
                  <Unplug className="h-3.5 w-3.5" />
                  Disconnect
                </button>
              </>
            ) : (
              <button
                onClick={() => setShowConnectForm((v) => !v)}
                className="flex items-center gap-1.5 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:bg-primary/90 transition-colors"
              >
                <Plug className="h-3.5 w-3.5" />
                Connect Toast
              </button>
            )}
          </div>
        </div>

        {status && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-2 border-t border-border text-sm">
            <div>
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Last sync</p>
              <p>{status.last_synced_at ? format(new Date(status.last_synced_at), "MMM d, HH:mm") : "Never"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Historical import</p>
              <p>{status.historical_import_complete ? "Complete" : "Not started — click “Run historical import”"}</p>
            </div>
          </div>
        )}

        {backfillResult && (
          <div className="flex items-start gap-2 pt-2 border-t border-border text-sm text-green-500">
            <CheckCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>
              Backfilled {backfillResult.scanned} orders — {backfillResult.updated} channel
              labels, {backfillResult.fulfillment_updated} fulfillment times
              ({backfillResult.dining_options} dining options).
            </span>
          </div>
        )}
      </div>

      {/* Connect form */}
      {showConnectForm && !status?.is_active && (
        <form onSubmit={handleConnect} className="border border-border rounded-lg p-6 bg-card space-y-4">
          <h2 className="font-semibold">Toast credentials</h2>
          {connectError && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {connectError instanceof Error ? connectError.message : "Connection failed"}
            </div>
          )}
          {[
            { label: "Client ID", key: "client_id", type: "text", placeholder: "Toast client ID" },
            { label: "Client Secret", key: "client_secret", type: "password", placeholder: "Toast client secret" },
            { label: "Restaurant GUID", key: "toast_restaurant_guid", type: "text", placeholder: "Toast restaurant external ID" },
          ].map(({ label, key, type, placeholder }) => (
            <div key={key} className="space-y-1">
              <label className="text-sm font-medium">{label}</label>
              <input
                type={type}
                required
                value={form[key as keyof typeof form]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                placeholder={placeholder}
                className="w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          ))}
          <div className="space-y-1">
            <label className="text-sm font-medium">Historical import from (optional)</label>
            <input
              type="date"
              value={form.historical_import_from}
              onChange={(e) => setForm((f) => ({ ...f, historical_import_from: e.target.value }))}
              className="w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <p className="text-xs text-muted-foreground">Leave blank to default to 1 year back.</p>
          </div>
          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={connecting || !locationId}
              className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {connecting ? "Connecting…" : "Connect"}
            </button>
            <button
              type="button"
              onClick={() => setShowConnectForm(false)}
              className="px-4 py-2 text-sm border border-border rounded-md hover:bg-muted/50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Sync job history */}
      <div className="space-y-3">
        <h2 className="text-base font-semibold">Sync history</h2>
        {jobsLoading && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {jobsData && jobsData.data.length === 0 && (
          <p className="text-sm text-muted-foreground">No sync jobs yet.</p>
        )}
        {jobsData && jobsData.data.length > 0 && (
          <div className="rounded-lg border border-border overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Type</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Status</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Started</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Orders</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Time entries</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Error</th>
                </tr>
              </thead>
              <tbody>
                {jobsData.data.map((job) => (
                  <SyncJobRow key={job.id} job={job} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
