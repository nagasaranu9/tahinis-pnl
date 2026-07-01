'use client';

import { useState, useMemo } from 'react';
import { useAuthStore } from '@/lib/auth-store';
import { useLocations } from '@/hooks/use-locations';
import { useReviewsSummary, useReviewsList } from '@/hooks/use-reviews';
import { usePlatformMetrics } from '@/hooks/use-pipeboard';
import { Tile, TileHeader } from '@/components/ui/tile';
import { MarketingMetricsTile } from '@/components/marketing-metrics-tile';
import { Star, RefreshCw, Settings, Zap, Calendar, ChevronDown } from 'lucide-react';
import Link from 'next/link';

type PresetKey = 'today' | 'yesterday' | 'last7' | 'last30' | 'thisMonth' | 'lastMonth' | 'thisYear' | 'ytd' | 'custom';

interface DateRange {
  start: string;
  end: string;
  label: string;
}

function toISO(d: Date): string {
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${month}-${day}`;
}

function getPreset(key: PresetKey): DateRange {
  const now = new Date();
  const today = toISO(now);
  switch (key) {
    case 'today':
      return { start: today, end: today, label: 'Today' };
    case 'yesterday': {
      const y = new Date(now);
      y.setDate(y.getDate() - 1);
      const yesterday = toISO(y);
      return { start: yesterday, end: yesterday, label: 'Yesterday' };
    }
    case 'last7': {
      const s = new Date(now);
      s.setDate(s.getDate() - 6);
      return { start: toISO(s), end: today, label: 'Last 7 days' };
    }
    case 'last30': {
      const s = new Date(now);
      s.setDate(s.getDate() - 29);
      return { start: toISO(s), end: today, label: 'Last 30 days' };
    }
    case 'thisMonth':
      return {
        start: toISO(new Date(now.getFullYear(), now.getMonth(), 1)),
        end: today,
        label: 'This month',
      };
    case 'lastMonth': {
      const s = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const e = new Date(now.getFullYear(), now.getMonth(), 0);
      return { start: toISO(s), end: toISO(e), label: 'Last month' };
    }
    case 'thisYear':
      return {
        start: toISO(new Date(now.getFullYear(), 0, 1)),
        end: today,
        label: 'This year',
      };
    case 'ytd':
      return {
        start: toISO(new Date(now.getFullYear(), 0, 1)),
        end: today,
        label: 'Year to date',
      };
    default:
      return { start: today, end: today, label: 'Today' };
  }
}

const PRESETS: { key: PresetKey; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: 'last7', label: 'Last 7 days' },
  { key: 'last30', label: 'Last 30 days' },
  { key: 'thisMonth', label: 'This month' },
  { key: 'lastMonth', label: 'Last month' },
  { key: 'thisYear', label: 'This year' },
  { key: 'ytd', label: 'Year to date' },
  { key: 'custom', label: 'Custom' },
];

export default function MarketingPage() {
  const { getLocationId } = useAuthStore();
  const { selectedLocationId } = useLocations();
  const locationId = selectedLocationId ?? getLocationId() ?? undefined;

  const [activePreset, setActivePreset] = useState<PresetKey>('last30');
  const [showDateMenu, setShowDateMenu] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');

  const dateRange: DateRange = useMemo(() => {
    if (activePreset === 'custom' && customStart && customEnd) {
      return { start: customStart, end: customEnd, label: `${customStart} to ${customEnd}` };
    }
    if (activePreset === 'custom') return getPreset('last30');
    return getPreset(activePreset);
  }, [activePreset, customStart, customEnd]);

  const { data: reviews, isLoading } = useReviewsSummary(locationId, {
    from: dateRange.start,
    to: dateRange.end,
  });
  const { data: reviewsData } = useReviewsList(locationId, 1, 5, {
    from: dateRange.start,
    to: dateRange.end,
  });
  const recentReviews = reviewsData?.data || reviews?.recent_reviews;

  const { data: platformMetrics, isLoading: metricsLoading } = usePlatformMetrics({
    from: dateRange.start,
    to: dateRange.end,
  });
  // Endpoint returns display labels ("Google Ads"), not raw keys ("google_ads").
  const matchPlatform = (m: { platform: string }, key: string) =>
    m.platform.toLowerCase().replace(/[\s_]/g, '') === key;
  const googleAds = platformMetrics?.find((m) => matchPlatform(m, 'googleads'));
  const metaAds = platformMetrics?.find((m) => matchPlatform(m, 'metaads'));

  const formatDate = (isoDate: string | null) => {
    if (!isoDate) return 'Never';
    const d = new Date(isoDate);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  return (
    <main className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Marketing</h1>
          <p className="text-sm text-muted-foreground mt-1">Reviews, Google Ads, Meta Ads, and spend analytics.</p>
        </div>
      </div>

      {/* Date Range Selector */}
      <div className="relative">
        <button
          onClick={() => {
            setShowDateMenu(!showDateMenu);
            setShowCustom(false);
          }}
          className="flex items-center gap-2 px-4 py-2 rounded-md bg-primary/10 border border-primary/25 text-sm font-semibold text-primary hover:bg-primary/15 transition-colors cursor-pointer"
        >
          <Calendar className="h-3.5 w-3.5" />
          {dateRange.label}
          <ChevronDown className="h-3.5 w-3.5 opacity-70" />
        </button>
        {showDateMenu && (
          <div className="absolute left-0 top-full mt-1 w-52 rounded-md border border-border bg-card shadow-lg z-50 py-1">
            {PRESETS.map((p) => (
              <button
                key={p.key}
                onClick={() => {
                  if (p.key === 'custom') {
                    setShowCustom(true);
                  } else {
                    setActivePreset(p.key);
                    setShowDateMenu(false);
                    setShowCustom(false);
                  }
                }}
                className={`w-full text-left px-4 py-2 text-sm hover:bg-accent transition-colors cursor-pointer ${
                  activePreset === p.key ? 'text-primary font-medium' : 'text-foreground'
                }`}
              >
                {p.label}
              </button>
            ))}
            {showCustom && (
              <div className="px-4 py-3 border-t border-border space-y-2">
                <input
                  type="date"
                  value={customStart}
                  onChange={(e) => setCustomStart(e.target.value)}
                  className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                />
                <input
                  type="date"
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                  className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                />
                <button
                  onClick={() => {
                    if (customStart && customEnd) {
                      setActivePreset('custom');
                      setShowDateMenu(false);
                      setShowCustom(false);
                    }
                  }}
                  className="w-full rounded bg-primary text-primary-foreground text-xs py-1.5 font-medium hover:opacity-90 transition-opacity cursor-pointer"
                >
                  Apply
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Reviews Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Reviews</h2>
          <Link
            href="/settings?tab=integrations"
            className="inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded-md hover:bg-muted/60 transition-colors"
          >
            <Settings className="h-4 w-4" />
            Configure
          </Link>
        </div>

        {isLoading ? (
          <Tile className="h-40 flex items-center justify-center">
            <div className="text-muted-foreground">Loading reviews...</div>
          </Tile>
        ) : !reviews ? (
          <Tile className="h-40 flex items-center justify-center">
            <div className="text-muted-foreground">
              Reviews not connected.{' '}
              <Link href="/settings?tab=integrations" className="text-primary hover:underline">
                Connect Google Business Profile
              </Link>
            </div>
          </Tile>
        ) : (
          <>
            {/* Status Card */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <Tile className="p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground mb-2">Average Rating</p>
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-bold">{(reviews.average_rating ?? 0).toFixed(1)}</span>
                      <div className="flex gap-0.5">
                        {[...Array(5)].map((_, i) => (
                          <Star
                            key={i}
                            className={`h-4 w-4 ${
                              i < Math.round(reviews.average_rating ?? 0)
                                ? 'fill-amber-400 text-amber-400'
                                : 'text-muted-foreground/30'
                            }`}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </Tile>

              <Tile className="p-6">
                <p className="text-sm text-muted-foreground mb-2">Total Reviews</p>
                <p className="text-3xl font-bold">{reviews.total_review_count || 0}</p>
              </Tile>

              <Tile className="p-6">
                <p className="text-sm text-muted-foreground mb-2">5-Star Rating</p>
                <p className="text-3xl font-bold">{reviews.five_star || 0}</p>
              </Tile>
            </div>

            {/* Recent Reviews */}
            {recentReviews && recentReviews.length > 0 && (
              <Tile className="p-6">
                <TileHeader label="Recent Reviews" icon={Star} />
                <div className="space-y-4 mt-4">
                  {recentReviews.map((review) => (
                    <div key={review.id} className="border-b border-border/50 pb-4 last:border-0">
                      <div className="flex items-start justify-between gap-4 mb-2">
                        <div>
                          <p className="font-medium">{review.author_name || 'Anonymous'}</p>
                          <p className="text-xs text-muted-foreground">{formatDate(review.published_at)}</p>
                        </div>
                        <div className="flex gap-0.5">
                          {[...Array(5)].map((_, i) => (
                            <Star
                              key={i}
                              className={`h-3.5 w-3.5 ${
                                i < (review.rating || 0)
                                  ? 'fill-amber-400 text-amber-400'
                                  : 'text-muted-foreground/30'
                              }`}
                            />
                          ))}
                        </div>
                      </div>
                      <p className="text-sm text-muted-foreground line-clamp-3">{review.comment}</p>
                    </div>
                  ))}
                </div>
              </Tile>
            )}
          </>
        )}
      </div>

      {/* Google Ads */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Google Ads</h2>
          <Link
            href="/google-ads"
            className="inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded-md hover:bg-muted/60 transition-colors"
          >
            <Zap className="h-4 w-4" />
            Optimization
          </Link>
        </div>
        {metricsLoading ? (
          <Tile className="h-40 flex items-center justify-center">
            <div className="text-muted-foreground">Loading Google Ads…</div>
          </Tile>
        ) : googleAds ? (
          <MarketingMetricsTile {...googleAds} />
        ) : (
          <Tile className="h-40 flex items-center justify-center">
            <div className="text-muted-foreground text-center">
              No Google Ads data.{' '}
              <Link href="/settings?tab=integrations" className="text-primary hover:underline">
                Connect Pipeboard
              </Link>
            </div>
          </Tile>
        )}
      </div>

      {/* Meta Ads */}
      <div className="space-y-4">
        <h2 className="text-xl font-semibold">Meta Ads</h2>
        {metricsLoading ? (
          <Tile className="h-40 flex items-center justify-center">
            <div className="text-muted-foreground">Loading Meta Ads…</div>
          </Tile>
        ) : metaAds ? (
          <MarketingMetricsTile {...metaAds} />
        ) : (
          <Tile className="h-40 flex items-center justify-center">
            <div className="text-muted-foreground">Meta Ads integration coming soon</div>
          </Tile>
        )}
      </div>
    </main>
  );
}
