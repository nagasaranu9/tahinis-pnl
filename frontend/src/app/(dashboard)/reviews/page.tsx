"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { format, parseISO } from "date-fns";
import { Star, RefreshCw, Unplug, Plug, AlertCircle, CheckCircle } from "lucide-react";
import {
  useReviewsStatus,
  useReviewsAuthUrl,
  useReviewsSummary,
  useReviewsList,
  useReviewsSync,
  useReviewsDisconnect,
  useSetReviewLocation,
  useDiscoverReviewLocation,
} from "@/hooks/use-reviews";
import type { GoogleReview } from "@/types/google-reviews";

function StarRating({ rating }: { rating: number | null }) {
  if (!rating) return <span className="text-muted-foreground text-xs">No rating</span>;
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={`h-3.5 w-3.5 ${i <= rating ? "text-yellow-400 fill-yellow-400" : "text-muted-foreground/30"}`}
        />
      ))}
    </div>
  );
}

function StarBar({ label, count, total }: { label: string; count: number; total: number }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-8 text-right text-muted-foreground">{label}</span>
      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-yellow-400 rounded-full transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-6 text-muted-foreground">{count}</span>
    </div>
  );
}

function ReviewCard({ review }: { review: GoogleReview }) {
  return (
    <div className="p-4 border border-border rounded-lg bg-card space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{review.author_name ?? "Anonymous"}</p>
          {review.published_at && (
            <p className="text-xs text-muted-foreground">
              {format(parseISO(review.published_at), "MMM d, yyyy")}
            </p>
          )}
        </div>
        <StarRating rating={review.rating} />
      </div>
      {review.comment && (
        <p className="text-sm text-muted-foreground line-clamp-3">{review.comment}</p>
      )}
      {review.reply_comment && (
        <div className="mt-2 pl-3 border-l-2 border-primary/40">
          <p className="text-xs text-muted-foreground font-medium mb-0.5">Owner reply</p>
          <p className="text-xs text-muted-foreground line-clamp-2">{review.reply_comment}</p>
        </div>
      )}
    </div>
  );
}

function LocationPin({
  locationId,
  accountName,
  locationName,
}: {
  locationId: string;
  accountName: string | null;
  locationName: string | null;
}) {
  const { mutate: save, isPending, isSuccess } = useSetReviewLocation();
  const { mutate: discover, isPending: discovering, data: discovered, error: discoverError } =
    useDiscoverReviewLocation();
  const [account, setAccount] = useState(accountName ?? "");
  const [location, setLocation] = useState(locationName ?? "");
  const pinned = !!accountName && !!locationName;

  return (
    <div className="border border-border rounded-lg bg-card p-6 space-y-3">
      <h3 className="text-sm font-semibold">Business Profile location</h3>
      {!pinned && (
        <div className="flex items-start gap-2 text-xs text-yellow-500">
          <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>
            Sync stays empty until your Google account + location IDs are set.
            Easiest: click <strong>Auto-detect</strong> below. Manual fallback —
            copy them from the business.google.com URL (format{" "}
            <code>accounts/123</code> and <code>accounts/123/locations/456</code>).
          </span>
        </div>
      )}
      <div className="space-y-1">
        <button
          onClick={() => discover(locationId)}
          disabled={discovering}
          className="text-sm px-3 py-1.5 rounded-md border border-primary text-primary hover:bg-primary/10 disabled:opacity-50"
        >
          {discovering ? "Detecting…" : "Auto-detect from Google"}
        </button>
        {discovered?.account_name && (
          <p className="text-xs text-green-500">
            Detected {discovered.account_name} / {discovered.location_name}. Click Sync Now.
          </p>
        )}
        {discovered?.error && (
          <p className="text-xs text-yellow-500">
            Couldn’t auto-detect ({discovered.error}). Enter IDs manually below.
          </p>
        )}
        {discoverError && (
          <p className="text-xs text-destructive">
            {discoverError instanceof Error ? discoverError.message : "Auto-detect failed"}
          </p>
        )}
      </div>
      <div className="space-y-2">
        <div>
          <label className="text-xs font-medium text-muted-foreground">Account name</label>
          <input
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            placeholder="accounts/123456789"
            className="mt-1 w-full text-sm border border-input rounded-md px-3 py-1.5 bg-background"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground">Location name</label>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="accounts/123456789/locations/987654321"
            className="mt-1 w-full text-sm border border-input rounded-md px-3 py-1.5 bg-background"
          />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() =>
            save({ location_id: locationId, account_name: account.trim(), location_name: location.trim() })
          }
          disabled={isPending || !account.trim() || !location.trim()}
          className="text-sm px-3 py-1.5 rounded-md bg-primary text-primary-foreground disabled:opacity-50"
        >
          {isPending ? "Saving…" : pinned ? "Update" : "Save & enable sync"}
        </button>
        {isSuccess && (
          <span className="flex items-center gap-1 text-xs text-green-500">
            <CheckCircle className="h-3.5 w-3.5" /> Saved — now click Sync Now.
          </span>
        )}
      </div>
    </div>
  );
}

function ReviewsContent() {
  const searchParams = useSearchParams();
  const connected = searchParams.get("connected") === "google";
  const error = searchParams.get("error");

  const { data: configs, isLoading: configsLoading } = useReviewsStatus();
  const { mutate: connect, isPending: connecting } = useReviewsAuthUrl();
  const { mutate: sync, isPending: syncing } = useReviewsSync();
  const { mutate: disconnect, isPending: disconnecting } = useReviewsDisconnect();

  const activeConfig = configs?.find((c) => c.is_active);
  const { data: summary } = useReviewsSummary(activeConfig?.location_id);
  const { data: reviewsData } = useReviewsList(activeConfig?.location_id);
  const totalStars = summary?.total_review_count ?? 0;

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Reviews</h1>
          <p className="text-sm text-muted-foreground mt-1">Google Business ratings and review tracking.</p>
        </div>
        {activeConfig && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => sync(activeConfig.location_id)}
              disabled={syncing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-border rounded-md hover:bg-muted/40 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
              {syncing ? "Syncing…" : "Sync Now"}
            </button>
            <button
              onClick={() => disconnect(activeConfig.id)}
              disabled={disconnecting}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-destructive border border-destructive/30 rounded-md hover:bg-destructive/10 disabled:opacity-50 transition-colors"
            >
              <Unplug className="h-3.5 w-3.5" />
              Disconnect
            </button>
          </div>
        )}
      </div>

      {connected && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-green-500/10 border border-green-500/20 text-green-600 text-sm">
          <CheckCircle className="h-4 w-4 shrink-0" />
          Google Business connected! Syncing reviews in background.
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to connect Google Business. Please try again.
        </div>
      )}

      {!configsLoading && !activeConfig && (
        <div className="border border-border rounded-lg bg-card p-12 flex flex-col items-center gap-4 text-center">
          <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
            <Star className="h-8 w-8 text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Connect Google Business Profile</h2>
            <p className="text-sm text-muted-foreground mt-1 max-w-md">
              Import ratings, reviews, and response data automatically.
            </p>
          </div>
          <button
            onClick={() => connect()}
            disabled={connecting}
            className="flex items-center gap-2 px-5 py-2.5 rounded-md bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            <Plug className="h-4 w-4" />
            {connecting ? "Connecting…" : "Connect Google Business"}
          </button>
        </div>
      )}

      {activeConfig && summary && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="border border-border rounded-lg bg-card p-6 flex items-center gap-6">
              <div className="text-center">
                <p className="text-5xl font-bold tracking-tight">
                  {summary.average_rating?.toFixed(1) ?? "—"}
                </p>
                <div className="flex justify-center mt-1">
                  <StarRating rating={summary.average_rating ? Math.round(summary.average_rating) : null} />
                </div>
                <p className="text-xs text-muted-foreground mt-1">{summary.total_review_count} reviews</p>
              </div>
              <div className="flex-1 space-y-1.5">
                <StarBar label="5★" count={summary.five_star} total={totalStars} />
                <StarBar label="4★" count={summary.four_star} total={totalStars} />
                <StarBar label="3★" count={summary.three_star} total={totalStars} />
                <StarBar label="2★" count={summary.two_star} total={totalStars} />
                <StarBar label="1★" count={summary.one_star} total={totalStars} />
              </div>
            </div>

            <div className="border border-border rounded-lg bg-card p-6 space-y-3">
              <h3 className="text-sm font-semibold">Connection</h3>
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Account</span>
                  <span className="font-medium truncate max-w-[180px]">
                    {activeConfig.account_name ?? "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last synced</span>
                  <span className="font-medium">
                    {activeConfig.last_synced_at
                      ? format(parseISO(activeConfig.last_synced_at), "MMM d, h:mm a")
                      : "Never"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Status</span>
                  <span className="flex items-center gap-1 text-green-500 font-medium">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500 inline-block" />
                    Active
                  </span>
                </div>
              </div>
            </div>

            <LocationPin
              locationId={activeConfig.location_id}
              accountName={activeConfig.account_name}
              locationName={activeConfig.location_name}
            />
          </div>

          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Recent Reviews
            </h2>
            {reviewsData?.data && reviewsData.data.length > 0 ? (
              <div className="space-y-3">
                {reviewsData.data.map((r) => (
                  <ReviewCard key={r.id} review={r} />
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-sm text-muted-foreground border border-border rounded-lg bg-card">
                No reviews yet. Click &quot;Sync Now&quot; to import from Google Business.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function ReviewsPage() {
  return (
    <Suspense>
      <ReviewsContent />
    </Suspense>
  );
}
