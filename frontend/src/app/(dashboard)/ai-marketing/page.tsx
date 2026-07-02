'use client';

import { useState } from 'react';
import { useLocations } from '@/hooks/use-locations';
import { useCompetitorIntel, type CompetitorRow } from '@/hooks/use-ai-marketing';
import { Tile, TileHeader } from '@/components/ui/tile';
import {
  Sparkles,
  Shield,
  Target,
  Star,
  Megaphone,
  Tag,
  Lightbulb,
  TrendingUp,
  AlertCircle,
  Globe,
  MapPin,
} from 'lucide-react';

const RADII = [1, 3, 5, 10];

function scoreColor(v: number): string {
  if (v >= 67) return 'text-red-500';
  if (v >= 34) return 'text-amber-500';
  return 'text-emerald-500';
}
function scoreBg(v: number): string {
  if (v >= 67) return 'bg-red-500';
  if (v >= 34) return 'bg-amber-500';
  return 'bg-emerald-500';
}

function ScoreRing({ label, value, invert }: { label: string; value: number; invert?: boolean }) {
  // invert=true for Opportunity (high = good = green).
  const shown = invert ? 100 - value : value;
  const color = scoreColor(shown);
  const bg = scoreBg(shown);
  return (
    <Tile>
      <TileHeader label={label} icon={invert ? Target : Shield} />
      <div className="mt-3 flex items-end gap-2">
        <span className={`text-4xl font-bold tabular-nums ${color}`}>{value}</span>
        <span className="text-sm text-muted-foreground mb-1">/ 100</span>
      </div>
      <div className="mt-3 h-2 w-full rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${bg} transition-all`} style={{ width: `${value}%` }} />
      </div>
    </Tile>
  );
}

function CompetitorCard({ c }: { c: CompetitorRow }) {
  return (
    <div className="p-4 rounded-lg border border-border bg-card space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate">{c.name ?? 'Unknown'}</p>
          <p className="text-xs text-muted-foreground truncate flex items-center gap-1">
            <MapPin className="h-3 w-3 shrink-0" />
            {c.distance_m != null ? `${(c.distance_m / 1000).toFixed(1)} km` : '—'}
            {c.primary_type ? ` · ${c.primary_type}` : ''}
            {c.price_level ? ` · ${c.price_level.replace('PRICE_LEVEL_', '').toLowerCase()}` : ''}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="flex items-center gap-1 text-sm font-medium">
            <Star className="h-3.5 w-3.5 text-yellow-400 fill-yellow-400" />
            {c.rating?.toFixed(1) ?? '—'}
          </div>
          <p className="text-[11px] text-muted-foreground">{c.review_count.toLocaleString()} reviews</p>
        </div>
      </div>
      <div className="flex items-center gap-4 pt-1">
        <div className="flex-1">
          <div className="flex justify-between text-[11px] mb-0.5">
            <span className="text-muted-foreground">Threat</span>
            <span className={scoreColor(c.threat_score)}>{c.threat_score}</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div className={`h-full ${scoreBg(c.threat_score)}`} style={{ width: `${c.threat_score}%` }} />
          </div>
        </div>
        <div className="flex-1">
          <div className="flex justify-between text-[11px] mb-0.5">
            <span className="text-muted-foreground">Opportunity</span>
            <span className={scoreColor(100 - c.opportunity_score)}>{c.opportunity_score}</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div className={`h-full ${scoreBg(100 - c.opportunity_score)}`} style={{ width: `${c.opportunity_score}%` }} />
          </div>
        </div>
        {c.website && (
          <a
            href={c.website}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground shrink-0"
            aria-label="Competitor website"
          >
            <Globe className="h-4 w-4" />
          </a>
        )}
      </div>
    </div>
  );
}

function Empty({ reason }: { reason?: string }) {
  const msg: Record<string, string> = {
    no_api_key: 'Google Places API key not configured on the server.',
    no_location: 'No location found for this account.',
    no_place_id: 'Set this location’s Google Place ID (Settings) to enable competitor intel.',
    no_coordinates: 'Could not resolve coordinates for this location.',
  };
  return (
    <div className="border border-border rounded-lg bg-card p-12 flex flex-col items-center gap-3 text-center">
      <div className="h-14 w-14 rounded-full bg-muted flex items-center justify-center">
        <AlertCircle className="h-7 w-7 text-muted-foreground" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">Competitor intel unavailable</h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-md">
          {(reason && msg[reason]) ?? msg[reason ?? ''] ?? 'Unable to load competitor data right now.'}
        </p>
      </div>
    </div>
  );
}

export default function AIMarketingPage() {
  const { selectedLocationId } = useLocations();
  const [radius, setRadius] = useState(5);
  const { data, isLoading, isError } = useCompetitorIntel(selectedLocationId ?? undefined, radius);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Sparkles className="h-7 w-7 text-violet-500" />
            AI Marketing
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Competitive intelligence on restaurants near you — threats, openings, and a suggested play.
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-md border border-border p-0.5">
          {RADII.map((r) => (
            <button
              key={r}
              onClick={() => setRadius(r)}
              className={`px-3 py-1.5 text-sm rounded cursor-pointer transition-colors ${
                radius === r ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {r} km
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-28 rounded-2xl bg-muted/40 animate-pulse" />
          ))}
        </div>
      )}

      {isError && <Empty reason="error" />}

      {!isLoading && data && !data.available && <Empty reason={data.reason} />}

      {!isLoading && data && data.available && (
        <>
          {/* Score row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <ScoreRing label="Market Threat" value={data.threat_score} />
            <ScoreRing label="Opportunity" value={data.opportunity_score} invert />
            <Tile>
              <TileHeader label="Your Rating" icon={Star} />
              <div className="mt-3 flex items-end gap-2">
                <span className="text-4xl font-bold tabular-nums">{data.own_rating?.toFixed(1) ?? '—'}</span>
                <span className="text-sm text-muted-foreground mb-1">
                  {data.own_review_count.toLocaleString()} reviews
                </span>
              </div>
            </Tile>
            <Tile>
              <TileHeader label="Competitors" icon={Target} />
              <p className="text-4xl font-bold tabular-nums mt-3">{data.competitor_count}</p>
              <p className="text-xs text-muted-foreground mt-1">within {data.radius_km} km</p>
            </Tile>
          </div>

          {/* AI briefing */}
          {data.ai_available ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Tile>
                <TileHeader label="Advertising Summary" icon={Megaphone} />
                <p className="text-sm text-muted-foreground mt-3 leading-relaxed">{data.advertising_summary}</p>
              </Tile>
              <Tile>
                <TileHeader label="Promotion Summary" icon={Tag} />
                <p className="text-sm text-muted-foreground mt-3 leading-relaxed">{data.promotion_summary}</p>
              </Tile>

              <Tile className="lg:col-span-2 border-violet-500/30 bg-violet-500/[0.04]">
                <TileHeader label="Suggested Campaign" icon={Lightbulb} />
                <p className="text-sm mt-3 leading-relaxed">{data.suggested_campaign}</p>
                {data.suggested_headlines.length > 0 && (
                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                      Suggested Google Ads headlines
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {data.suggested_headlines.map((h, i) => (
                        <span
                          key={i}
                          className="text-xs px-2.5 py-1 rounded-full border border-border bg-card"
                        >
                          {h}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </Tile>

              <Tile className="lg:col-span-2 border-emerald-500/30 bg-emerald-500/[0.04]">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <TileHeader label="Estimated Monthly Opportunity" icon={TrendingUp} />
                    <p className="text-3xl font-bold tabular-nums text-emerald-500 mt-2">
                      {data.estimated_monthly_opportunity || '—'}
                    </p>
                  </div>
                  <span className="text-xs px-2 py-1 rounded-full bg-muted text-muted-foreground self-start">
                    AI estimate · {Math.round(data.ai_confidence * 100)}% confidence
                  </span>
                </div>
                {data.ai_explanation && (
                  <p className="text-xs text-muted-foreground mt-3 leading-relaxed">{data.ai_explanation}</p>
                )}
              </Tile>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground border border-border rounded-lg bg-card p-4">
              AI strategy briefing unavailable right now. Competitor scores above are from live Google Places data.
            </div>
          )}

          {/* Competitor grid */}
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Nearby competitors
            </h2>
            {data.competitors.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {data.competitors.map((c) => (
                  <CompetitorCard key={c.place_id} c={c} />
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-sm text-muted-foreground border border-border rounded-lg bg-card">
                No competitors found within {data.radius_km} km.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
