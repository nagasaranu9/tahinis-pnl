"use client";

import { useState } from "react";
import { CheckCircle, Unplug, Zap, AlertCircle, Loader2 } from "lucide-react";
import {
  usePipeboardStatus,
  usePipeboardConnect,
  usePipeboardDisconnect,
  usePipeboardManualSync,
  usePipeboardSyncJobs,
  usePipeboardDeleteSyncJob,
} from "@/hooks/use-pipeboard";

export function PipeboardIntegration() {
  const { data: status, isLoading: statusLoading } = usePipeboardStatus();
  const { mutate: connect, isPending: connecting, error: connectError } = usePipeboardConnect();
  const { mutate: disconnect, isPending: disconnecting } = usePipeboardDisconnect();
  const { mutate: manualSync, isPending: syncPending } = usePipeboardManualSync();
  const { data: syncJobs = [] } = usePipeboardSyncJobs();
  const { mutate: deleteSyncJob, isPending: deleting } = usePipeboardDeleteSyncJob();

  const [apiToken, setApiToken] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  if (statusLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      {/* Connection Status */}
      <div className="border border-border rounded-lg bg-card p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {status?.connected ? (
              <>
                <CheckCircle className="h-5 w-5 text-green-400" />
                <div>
                  <p className="font-medium text-sm">Pipeboard connected</p>
                  <p className="text-xs text-muted-foreground">
                    Google Ads customer {status.pipeboard_account_id}
                  </p>
                  {status.last_sync_at && (
                    <p className="text-xs text-muted-foreground">
                      Last sync: {new Date(status.last_sync_at).toLocaleString()}
                    </p>
                  )}
                </div>
              </>
            ) : (
              <>
                <AlertCircle className="h-5 w-5 text-yellow-400" />
                <div>
                  <p className="font-medium text-sm">Not connected</p>
                  <p className="text-xs text-muted-foreground">Connect Pipeboard to sync Google Ads data</p>
                </div>
              </>
            )}
          </div>
          {status?.connected && (
            <button
              onClick={() => disconnect()}
              disabled={disconnecting}
              className="flex items-center gap-1 px-2 py-1 text-xs border border-destructive text-destructive rounded hover:bg-destructive/10 disabled:opacity-50"
            >
              <Unplug className="h-3 w-3" />
              {disconnecting ? "Disconnecting…" : "Disconnect"}
            </button>
          )}
        </div>
      </div>

      {/* Connect Form */}
      {!status?.connected && (
        <div className="border border-border rounded-lg bg-card p-6 space-y-4">
          <div>
            <h3 className="font-semibold">Connect Pipeboard</h3>
            <p className="text-xs text-muted-foreground mt-1 mb-3">
              Get your API token at{" "}
              <a
                href="https://pipeboard.co/api-tokens"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                pipeboard.co/api-tokens
              </a>
            </p>
          </div>
          <div className="grid gap-3 max-w-md">
            <input
              type="password"
              placeholder="Pipeboard API token"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              className="px-3 py-2 text-sm rounded-md border border-border bg-background"
            />
            {connectError && (
              <p className="text-xs text-destructive">
                {(connectError as Error)?.message || "Connection failed"}
              </p>
            )}
            <button
              onClick={() => connect({ api_token: apiToken, platform: "google_ads" })}
              disabled={!apiToken || connecting}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:opacity-90 disabled:opacity-50 w-fit"
            >
              {connecting && <Loader2 className="h-4 w-4 animate-spin" />}
              {connecting ? "Connecting…" : "Connect"}
            </button>
          </div>
        </div>
      )}

      {/* Manual Sync */}
      {status?.connected && (
        <div className="border border-border rounded-lg bg-card p-6 space-y-4">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            <h3 className="font-semibold">Manual sync</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            Backfill Google Ads data for a date range. Leave blank to sync recent data.
          </p>
          <div className="grid grid-cols-2 gap-3 max-w-md">
            <div>
              <label className="block text-xs font-medium mb-1">From</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background"
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">To</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background"
              />
            </div>
          </div>
          <button
            onClick={() =>
              manualSync({
                date_from: dateFrom || undefined,
                date_to: dateTo || undefined,
                pipeboard_platform: "google_ads",
              })
            }
            disabled={syncPending}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:opacity-90 disabled:opacity-50 w-fit"
          >
            {syncPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {syncPending ? "Syncing…" : "Trigger sync"}
          </button>
        </div>
      )}

      {/* Sync Job History */}
      {syncJobs.length > 0 && (
        <div className="border border-border rounded-lg bg-card p-6">
          <h3 className="font-semibold mb-4">Recent sync jobs</h3>
          <div className="space-y-2">
            {syncJobs.slice(0, 5).map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between text-sm p-3 bg-muted/50 rounded"
              >
                <div>
                  <p className="font-medium capitalize">{job.job_type}</p>
                  <p className="text-xs text-muted-foreground">
                    {job.date_from} → {job.date_to}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-xs">{job.metrics_synced} metrics</p>
                    <p className="text-xs text-muted-foreground capitalize">{job.status}</p>
                  </div>
                  <button
                    onClick={() => deleteSyncJob(job.id)}
                    disabled={deleting}
                    className="text-muted-foreground hover:text-destructive transition-colors disabled:opacity-40 cursor-pointer"
                    title="Delete job"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                      <path d="M10 11v6M14 11v6" />
                      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
