'use client';

import { useAuthStore } from '@/lib/auth-store';
import { useLocations } from '@/hooks/use-locations';
import { useReviewsSummary, useReviewsList } from '@/hooks/use-reviews';
import { usePlatformMetrics } from '@/hooks/use-pipeboard';
import { Tile, TileHeader } from '@/components/ui/tile';
import { MarketingMetricsTile } from '@/components/marketing-metrics-tile';
import { Star, RefreshCw, Settings, Zap } from 'lucide-react';
import Link from 'next/link';

export default function MarketingPage() {
  const { getLocationId } = useAuthStore();
  const { selectedLocationId } = useLocations();
  const locationId = selectedLocationId ?? getLocationId() ?? undefined;

  const { data: reviews, isLoading } = useReviewsSummary(locationId);
  const { data: reviewsData } = useReviewsList(locationId, 1, 5);
  const recentReviews = reviewsData?.data || reviews?.recent_reviews;

  const { data: platformMetrics, isLoading: metricsLoading } = usePlatformMetrics();
  const googleAds = platformMetrics?.find((m) => m.platform === 'google_ads');
  const metaAds = platformMetrics?.find((m) => m.platform === 'meta_ads');

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
