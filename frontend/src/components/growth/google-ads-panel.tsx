'use client';

import { Tile, TileHeader } from '@/components/ui/tile';
import {
  useOptimizationSummary,
  useOptimizationRecommendations,
  useOptimizationActions,
  useRunOptimization,
} from '@/hooks/use-google-ads-optimization';
import { useAdsDetail, useAdsCampaigns } from '@/hooks/use-dashboard';
import { useLocations } from '@/hooks/use-locations';
import { Zap, RefreshCw, CheckCircle2, XCircle, Clock, TrendingUp, Pause, Plus, DollarSign, Megaphone } from 'lucide-react';

function fmtCAD(n: number, digits = 0): string {
  return new Intl.NumberFormat('en-CA', {
    style: 'currency',
    currency: 'CAD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}

function last30(): { date_from: string; date_to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 29);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { date_from: iso(from), date_to: iso(to) };
}

const STATUS_STYLES: Record<string, string> = {
  healthy: 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30',
  watch: 'bg-amber-500/15 text-amber-500 border-amber-500/30',
  alert: 'bg-red-500/15 text-red-500 border-red-500/30',
};

const ACTION_ICONS: Record<string, typeof Zap> = {
  pause_campaign: Pause,
  pause_keyword: Pause,
  increase_budget: TrendingUp,
  add_negative: Plus,
};

function fmtRelative(iso: string | null): string {
  if (!iso) return 'Never';
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  const hours = Math.floor(diffMs / 3600000);
  const days = Math.floor(diffMs / 86400000);
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

function prettyType(t: string): string {
  return t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Google Ads optimization panel. Rendered inside the Campaigns page under the
 * Google Ads platform tab (and previously the standalone /google-ads route).
 */
export function GoogleAdsPanel() {
  const { data: summary, isLoading: summaryLoading } = useOptimizationSummary();
  const { data: recommendations, isLoading: recsLoading } = useOptimizationRecommendations();
  const { data: actions, isLoading: actionsLoading } = useOptimizationActions();
  const runOptimization = useRunOptimization();

  const { selectedLocationId } = useLocations();
  const range = last30();
  const adsParams = { ...range, location_id: selectedLocationId ?? undefined };
  const { data: ads } = useAdsDetail(adsParams);
  const { data: campaigns } = useAdsCampaigns(adsParams);

  const status = summary?.status ?? 'watch';

  return (
    <div className="space-y-6">
      {/* Live Google Ads performance (last 30 days) */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Performance · last 30 days</h3>
          {ads?.roas != null && (
            <span className="text-xs text-muted-foreground">ROAS {ads.roas.toFixed(2)}x</span>
          )}
        </div>
        {ads && ads.spend > 0 ? (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <Tile>
                <TileHeader label="Spend" icon={DollarSign} />
                <p className="text-2xl font-bold mt-3 tabular-nums">{fmtCAD(ads.spend)}</p>
              </Tile>
              <Tile>
                <TileHeader label="Clicks" icon={TrendingUp} />
                <p className="text-2xl font-bold mt-3 tabular-nums">{ads.clicks.toLocaleString('en-CA')}</p>
                <p className="text-xs text-muted-foreground mt-1">CTR {ads.ctr}% · CPC {fmtCAD(ads.cpc, 2)}</p>
              </Tile>
              <Tile>
                <TileHeader label="Conversions" icon={CheckCircle2} />
                <p className="text-2xl font-bold mt-3 tabular-nums">{ads.conversions}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {ads.cost_per_conversion != null ? `${fmtCAD(ads.cost_per_conversion, 2)}/conv` : '—'}
                </p>
              </Tile>
              <Tile>
                <TileHeader label="Impressions" icon={Zap} />
                <p className="text-2xl font-bold mt-3 tabular-nums">{ads.impressions.toLocaleString('en-CA')}</p>
              </Tile>
            </div>

            {campaigns?.campaigns && campaigns.campaigns.length > 0 && (
              <Tile className="mt-4">
                <TileHeader label="Campaigns" icon={Megaphone} />
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-muted-foreground border-b border-border">
                        <th className="text-left font-medium py-1.5">Campaign</th>
                        <th className="text-right font-medium py-1.5">Spend</th>
                        <th className="text-right font-medium py-1.5">Clicks</th>
                        <th className="text-right font-medium py-1.5">Conv</th>
                        <th className="text-right font-medium py-1.5">ROAS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaigns.campaigns.map((c) => (
                        <tr key={c.campaign_id} className="border-b border-border/50 last:border-0">
                          <td className="py-1.5 pr-2">
                            <span className="truncate block max-w-[240px]">{c.name}</span>
                            <span className="text-[10px] text-muted-foreground uppercase">{c.status}</span>
                          </td>
                          <td className="text-right tabular-nums">{fmtCAD(c.spend)}</td>
                          <td className="text-right tabular-nums">{c.clicks.toLocaleString('en-CA')}</td>
                          <td className="text-right tabular-nums">{c.conversions}</td>
                          <td className="text-right tabular-nums">{c.roas != null ? `${c.roas.toFixed(1)}x` : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Tile>
            )}
          </>
        ) : (
          <div className="border border-border rounded-lg bg-card p-8 text-center text-sm text-muted-foreground">
            No Google Ads spend in the last 30 days for this location.
          </div>
        )}
      </div>

      <div className="h-px bg-border" />

      {/* Header row: description + run button */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold">Auto-optimization</h3>
          <p className="text-sm text-muted-foreground">
            Runs daily. Recommendations are executed automatically.
          </p>
        </div>
        <button
          onClick={() => runOptimization.mutate()}
          disabled={runOptimization.isPending}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer"
        >
          <RefreshCw className={`h-4 w-4 ${runOptimization.isPending ? 'animate-spin' : ''}`} />
          {runOptimization.isPending ? 'Running…' : 'Run Now'}
        </button>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Tile>
          <TileHeader label="Status" icon={Zap} />
          <div className="mt-3">
            <span
              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border ${
                STATUS_STYLES[status] ?? STATUS_STYLES.watch
              }`}
            >
              {status === 'healthy' ? 'Healthy' : status === 'alert' ? 'Alert' : 'Watch'}
            </span>
            <p className="text-xs text-muted-foreground mt-2">
              Last run {fmtRelative(summary?.last_run_at ?? null)}
            </p>
          </div>
        </Tile>

        <Tile>
          <TileHeader label="Recommendations" icon={TrendingUp} />
          <p className="text-2xl font-bold mt-3 tabular-nums">
            {summaryLoading ? '—' : summary?.total_recommendations ?? 0}
          </p>
          <p className="text-xs text-muted-foreground mt-1">All time</p>
        </Tile>

        <Tile>
          <TileHeader label="Actions Executed" icon={CheckCircle2} />
          <p className="text-2xl font-bold mt-3 tabular-nums text-emerald-500">
            {summaryLoading ? '—' : summary?.actions_succeeded ?? 0}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            of {summary?.total_actions ?? 0} total
          </p>
        </Tile>

        <Tile>
          <TileHeader label="Failed" icon={XCircle} />
          <p
            className={`text-2xl font-bold mt-3 tabular-nums ${
              (summary?.actions_failed ?? 0) > 0 ? 'text-red-500' : ''
            }`}
          >
            {summaryLoading ? '—' : summary?.actions_failed ?? 0}
          </p>
          <p className="text-xs text-muted-foreground mt-1">Need review</p>
        </Tile>
      </div>

      {/* Two-column: recommendations + action history */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Today's recommendations */}
        <Tile>
          <TileHeader label="Today's Recommendations" icon={TrendingUp} />
          <div className="mt-4 space-y-3">
            {recsLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : !recommendations?.length ? (
              <p className="text-sm text-muted-foreground py-6 text-center">
                No recommendations today. Campaigns performing within thresholds.
              </p>
            ) : (
              recommendations.map((rec) => {
                const Icon = ACTION_ICONS[rec.recommendation_type] ?? Zap;
                return (
                  <div
                    key={rec.id}
                    className="flex items-start gap-3 p-3 rounded-md border border-border bg-muted/30"
                  >
                    <Icon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-medium truncate">
                          {prettyType(rec.recommendation_type)}
                        </p>
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${
                            rec.status === 'executed'
                              ? 'bg-emerald-500/15 text-emerald-500'
                              : rec.status === 'skipped'
                                ? 'bg-red-500/15 text-red-500'
                                : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {rec.status}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        {rec.entity_name ?? rec.entity_id}
                      </p>
                      {rec.reasoning && (
                        <p className="text-xs text-muted-foreground mt-1">{rec.reasoning}</p>
                      )}
                      {rec.confidence_score != null && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Confidence: {Math.round(rec.confidence_score * 100)}%
                        </p>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </Tile>

        {/* Action history */}
        <Tile>
          <TileHeader label="Action History" icon={Clock} />
          <div className="mt-4 space-y-3">
            {actionsLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : !actions?.length ? (
              <p className="text-sm text-muted-foreground py-6 text-center">
                No actions executed today.
              </p>
            ) : (
              actions.map((action) => {
                const Icon = ACTION_ICONS[action.action_type] ?? Zap;
                const ok = action.status === 'success';
                return (
                  <div
                    key={action.id}
                    className="flex items-start gap-3 p-3 rounded-md border border-border"
                  >
                    <Icon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-medium truncate">
                          {prettyType(action.action_type)}
                        </p>
                        {ok ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500 shrink-0" />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        {action.entity_id}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {fmtRelative(action.executed_at ?? action.created_at)}
                      </p>
                      {action.error_message && (
                        <p className="text-xs text-red-500 mt-1">{action.error_message}</p>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </Tile>
      </div>

      {/* Run result toast */}
      {runOptimization.data && (
        <Tile className="border-primary/30 bg-primary/5">
          <p className="text-sm">
            Last manual run: {runOptimization.data.recommendations_generated} recommendations,{' '}
            {runOptimization.data.actions_executed} actions executed across{' '}
            {runOptimization.data.campaigns_synced} campaigns.
            {runOptimization.data.errors.length > 0 && (
              <span className="text-red-500"> Errors: {runOptimization.data.errors.join(', ')}</span>
            )}
          </p>
        </Tile>
      )}
    </div>
  );
}
