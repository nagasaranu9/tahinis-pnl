"use client";

import { useState } from "react";
import { CheckCircle, Unplug, Zap, AlertCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  usePipeboardStatus,
  usePipeboardConnect,
  usePipeboardDisconnect,
  usePipeboardManualSync,
  usePipeboardSyncJobs,
} from "@/hooks/use-pipeboard";

export function PipeboardIntegration() {
  const { data: status, isLoading: statusLoading } = usePipeboardStatus();
  const { mutate: connect, isPending: connecting, error: connectError } = usePipeboardConnect();
  const { mutate: disconnect, isPending: disconnecting } = usePipeboardDisconnect();
  const { mutate: manualSync, isPending: syncPending } = usePipeboardManualSync();
  const { data: syncJobs = [] } = usePipeboardSyncJobs();

  const [apiToken, setApiToken] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  if (statusLoading) return <div className="text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="space-y-6">
      {/* Connection Status */}
      <div className="border border-border rounded-lg bg-card p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {status?.connected ? (
              <>
                <CheckCircle className="h-5 w-5 text-green-500" />
                <div>
                  <p className="font-medium">Pipeboard Connected</p>
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
                <AlertCircle className="h-5 w-5 text-yellow-500" />
                <div>
                  <p className="font-medium">Not Connected</p>
                  <p className="text-xs text-muted-foreground">Connect Pipeboard to sync Google Ads data</p>
                </div>
              </>
            )}
          </div>
          {status?.connected && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => disconnect()}
              disabled={disconnecting}
              className="gap-1"
            >
              <Unplug className="h-4 w-4" />
              {disconnecting ? "Disconnecting…" : "Disconnect"}
            </Button>
          )}
        </div>
      </div>

      {/* Connect Form */}
      {!status?.connected && (
        <div className="border border-border rounded-lg bg-card p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">Pipeboard API Token</label>
            <p className="text-xs text-muted-foreground mb-3">
              Get your token at <a href="https://pipeboard.co/api-tokens" target="_blank" rel="noopener noreferrer" className="underline">pipeboard.co/api-tokens</a>
            </p>
            <Input
              type="password"
              placeholder="Enter your Pipeboard API token"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              className="mb-3"
            />
            {connectError && (
              <p className="text-xs text-destructive mb-3">
                {(connectError as any)?.message || "Connection failed"}
              </p>
            )}
            <Button
              onClick={() => connect({ api_token: apiToken, platform: "google_ads" })}
              disabled={!apiToken || connecting}
              className="w-full"
            >
              {connecting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Connecting…
                </>
              ) : (
                "Connect Pipeboard"
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Manual Sync */}
      {status?.connected && (
        <div className="border border-border rounded-lg bg-card p-6 space-y-4">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-5 w-5" />
            <h3 className="font-medium">Manual Sync</h3>
          </div>
          <p className="text-xs text-muted-foreground mb-4">
            Backfill Google Ads data for a custom date range. Leave blank to sync recent data.
          </p>
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-xs font-medium mb-1">From</label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                placeholder="2026-01-01"
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">To</label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                placeholder="2026-06-19"
              />
            </div>
          </div>
          <Button
            onClick={() =>
              manualSync({
                date_from: dateFrom || undefined,
                date_to: dateTo || undefined,
                pipeboard_platform: "google_ads",
              })
            }
            disabled={syncPending}
            className="w-full"
          >
            {syncPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Syncing…
              </>
            ) : (
              "Trigger Sync"
            )}
          </Button>
        </div>
      )}

      {/* Sync Job History */}
      {syncJobs.length > 0 && (
        <div className="border border-border rounded-lg bg-card p-6">
          <h3 className="font-medium mb-4">Recent Sync Jobs</h3>
          <div className="space-y-3">
            {syncJobs.slice(0, 5).map((job) => (
              <div key={job.id} className="flex items-center justify-between text-sm p-3 bg-muted/50 rounded">
                <div>
                  <p className="font-medium">
                    {job.status === "complete" && "✓"}
                    {job.status === "failed" && "✗"}
                    {job.status === "running" && "⧗"}
                    {job.status === "pending" && "⟳"} {job.job_type}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {job.date_from} to {job.date_to}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs">{job.metrics_synced} metrics</p>
                  <p className="text-xs text-muted-foreground capitalize">{job.status}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
