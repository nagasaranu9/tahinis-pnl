"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  CheckCircle, Unplug, Zap, AlertCircle, Loader2, ChevronDown,
  DollarSign, Eye, MousePointerClick, Percent, Target, TrendingUp,
} from "lucide-react";
import {
  usePipeboardStatus,
  usePipeboardConnect,
  usePipeboardDisconnect,
  usePipeboardManualSync,
  usePipeboardSyncJobs,
  usePipeboardDeleteSyncJob,
} from "@/hooks/use-pipeboard";
import { useAdsCampaigns } from "@/hooks/use-dashboard";

const fmtCAD = (n: number, d = 0) =>
  `CA$${n.toLocaleString("en-CA", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const fmtNum = (n: number) =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}K` : n.toLocaleString("en-CA");

const STATUS_STYLE: Record<string, string> = {
  ENABLED: "bg-green-500/15 text-green-400",
  PAUSED: "bg-yellow-500/15 text-yellow-500",
  REMOVED: "bg-red-500/15 text-red-400",
};

// ---------------------------------------------------------------------------
// Google Ads campaign performance — cards + table (Marketing → Google Ads tab)
// ---------------------------------------------------------------------------

export function GoogleAdsPerformance() {
  const { data: status, isLoading: statusLoading } = usePipeboardStatus();

  // Campaign performance over a trailing 30-day window (ad spend is sparse).
  const adsRange = useMemo(() => {
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - 29);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    return { date_from: iso(start), date_to: iso(end) };
  }, []);
  const { data: ads, isLoading: adsLoading } = useAdsCampaigns({
    ...adsRange,
    platform: "google_ads",
    enabled: Boolean(status?.connected),
  });

  if (statusLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  if (!status?.connected) {
    return (
      <div className="border border-border rounded-lg bg-card p-6 flex items-center gap-3">
        <AlertCircle className="h-5 w-5 text-yellow-400 shrink-0" />
        <div>
          <p className="font-medium text-sm">Google Ads not connected</p>
          <p className="text-xs text-muted-foreground">
            Connect Pipeboard from{" "}
            <Link href="/integrations" className="text-primary hover:underline">Integrations</Link>{" "}
            to sync campaign performance.
          </p>
        </div>
      </div>
    );
  }

  const t = ads?.totals;
  const STAT_CARDS = t
    ? [
        { label: "Total Spend", value: fmtCAD(t.spend, 2), icon: DollarSign, color: "text-green-400" },
        { label: "Impressions", value: fmtNum(t.impressions), icon: Eye, color: "text-sky-400" },
        { label: "Clicks", value: fmtNum(t.clicks), icon: MousePointerClick, color: "text-violet-400" },
        { label: "Avg CTR", value: `${t.ctr}%`, icon: Percent, color: "text-fuchsia-400" },
        { label: "Avg CPC", value: fmtCAD(t.cpc, 2), icon: TrendingUp, color: "text-amber-400" },
        { label: "Conversions", value: t.conversions.toLocaleString("en-CA"), icon: Target, color: "text-rose-400" },
        { label: "ROAS", value: t.roas != null ? `${t.roas}x` : "—", icon: TrendingUp, color: "text-emerald-400" },
      ]
    : [];

  return (
    <div className="space-y-4">
      {/* Summary stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {adsLoading ? (
          <div className="col-span-full flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading metrics…
          </div>
        ) : STAT_CARDS.length === 0 ? (
          <div className="col-span-full text-sm text-muted-foreground">
            No campaign metrics yet — run a sync from Integrations.
          </div>
        ) : (
          STAT_CARDS.map((c) => (
            <div key={c.label} className="border border-border rounded-lg bg-card p-3">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                <c.icon className="h-3.5 w-3.5" /> {c.label}
              </div>
              <p className={`text-lg font-bold mt-1 tabular-nums ${c.color}`}>{c.value}</p>
            </div>
          ))
        )}
      </div>

      {/* Campaign table */}
      {!adsLoading && (ads?.campaigns?.length ?? 0) > 0 && (
        <div className="border border-border rounded-lg bg-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h3 className="font-semibold text-sm">{ads!.campaigns.length} campaigns</h3>
            <span className="text-xs text-muted-foreground">Last 30 days · by spend</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-border">
                  <th className="px-4 py-2 font-medium">Campaign</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium text-right">Daily budget</th>
                  <th className="px-3 py-2 font-medium text-right">Spend</th>
                  <th className="px-3 py-2 font-medium text-right">Clicks / CTR</th>
                  <th className="px-4 py-2 font-medium text-right">Conversions</th>
                </tr>
              </thead>
              <tbody>
                {ads!.campaigns.map((c) => (
                  <tr key={c.campaign_id} className="border-b border-border/50 last:border-0">
                    <td className="px-4 py-2.5 font-medium max-w-[220px] truncate" title={c.name}>{c.name}</td>
                    <td className="px-3 py-2.5">
                      <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${STATUS_STYLE[c.status] ?? "bg-muted text-muted-foreground"}`}>
                        {c.status}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground">{c.type ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{c.daily_budget != null ? fmtCAD(c.daily_budget, 2) : "—"}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {fmtCAD(c.spend, 2)}
                      <div className="text-[11px] text-muted-foreground">{fmtNum(c.impressions)} impr</div>
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {fmtNum(c.clicks)}
                      <div className="text-[11px] text-muted-foreground">{c.ctr}% · {fmtCAD(c.cpc, 2)} CPC</div>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {c.conversions}
                      <div className="text-[11px] text-muted-foreground">{c.roas != null ? `${c.roas}x ROAS` : "—"}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pipeboard connection management — status, connect, sync, jobs (Integrations)
// ---------------------------------------------------------------------------

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

      {/* Manual Sync — collapsed by default */}
      {status?.connected && (
        <details className="group border border-border rounded-lg bg-card">
          <summary className="flex items-center gap-2 p-4 cursor-pointer list-none select-none">
            <Zap className="h-4 w-4" />
            <h3 className="font-semibold text-sm">Manual sync</h3>
            <ChevronDown className="h-4 w-4 ml-auto text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div className="px-4 pb-4 space-y-4">
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
        </details>
      )}

      {/* Sync Job History — collapsed by default */}
      {syncJobs.length > 0 && (
        <details className="group border border-border rounded-lg bg-card">
          <summary className="flex items-center gap-2 p-4 cursor-pointer list-none select-none">
            <h3 className="font-semibold text-sm">Recent sync jobs</h3>
            <span className="text-xs text-muted-foreground">({syncJobs.length})</span>
            <ChevronDown className="h-4 w-4 ml-auto text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div className="px-4 pb-4 space-y-2">
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
        </details>
      )}
    </div>
  );
}
