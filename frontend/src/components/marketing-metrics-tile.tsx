'use client';

import { TrendingUp, AlertCircle } from 'lucide-react';

export interface MarketingMetricsTileProps {
  platform: string;
  spend: number;
  revenue: number;
  roas: number;
  cpa: number;
  ctr: number;
  status: 'healthy' | 'watch' | 'alert';
  lastUpdated: string | null;
}

export function MarketingMetricsTile({
  platform,
  spend,
  revenue,
  roas,
  cpa,
  ctr,
  status,
  lastUpdated,
}: MarketingMetricsTileProps) {
  const statusColors = {
    healthy: 'bg-green-500/20 text-green-400 border-green-500/30',
    watch: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    alert: 'bg-red-500/20 text-red-400 border-red-500/30',
  };

  const statusLabels = {
    healthy: 'Healthy',
    watch: 'Watch',
    alert: 'Alert',
  };

  const statusDots = {
    healthy: 'bg-green-400',
    watch: 'bg-yellow-400',
    alert: 'bg-red-400',
  };

  return (
    <div className="border border-slate-700 rounded-lg bg-slate-900/50 p-6 backdrop-blur-sm hover:border-slate-600 transition-colors duration-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-lg font-semibold text-slate-100">{platform}</h3>
        <div
          className={`flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-medium ${statusColors[status]}`}
        >
          <span className={`w-2 h-2 rounded-full ${statusDots[status]}`}></span>
          {statusLabels[status]}
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="space-y-4">
        {/* Row 1: Spend & Revenue */}
        <div className="grid grid-cols-2 gap-4">
          <MetricItem label="Spend" value={`$${spend.toLocaleString()}`} />
          <MetricItem label="Revenue" value={`$${revenue.toLocaleString()}`} />
        </div>

        {/* Row 2: ROAS & CPA */}
        <div className="grid grid-cols-2 gap-4">
          <MetricItem label="ROAS" value={`${roas.toFixed(2)}x`} highlight={roas > 5} />
          <MetricItem label="CPA" value={`$${cpa.toFixed(2)}`} />
        </div>

        {/* Row 3: CTR */}
        <div className="grid grid-cols-2 gap-4">
          <MetricItem label="CTR" value={`${ctr.toFixed(1)}%`} />
          <div></div>
        </div>
      </div>

      {/* Footer */}
      {lastUpdated && (
        <div className="mt-5 pt-4 border-t border-slate-700/50 text-xs text-slate-400">
          Updated {new Date(lastUpdated).toLocaleDateString()}
        </div>
      )}
    </div>
  );
}

function MetricItem({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-xs font-medium text-slate-400 mb-1">{label}</span>
      <span
        className={`text-sm font-semibold ${
          highlight ? 'text-green-400' : 'text-slate-100'
        }`}
      >
        {value}
      </span>
    </div>
  );
}
