'use client';

import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Megaphone, Zap, Facebook, Music2, MessageSquare, Mail } from 'lucide-react';
import { GoogleAdsPanel } from '@/components/growth/google-ads-panel';

type PlatformKey = 'google' | 'meta' | 'tiktok' | 'sms' | 'email';

interface Platform {
  key: PlatformKey;
  label: string;
  icon: typeof Zap;
  live: boolean;
}

const PLATFORMS: Platform[] = [
  { key: 'google', label: 'Google Ads', icon: Zap, live: true },
  { key: 'meta', label: 'Meta Ads', icon: Facebook, live: false },
  { key: 'tiktok', label: 'TikTok', icon: Music2, live: false },
  { key: 'sms', label: 'SMS', icon: MessageSquare, live: false },
  { key: 'email', label: 'Email', icon: Mail, live: false },
];

function ComingSoonPanel({ label }: { label: string }) {
  return (
    <div className="border border-border rounded-lg bg-card p-12 flex flex-col items-center gap-3 text-center">
      <div className="h-14 w-14 rounded-full bg-muted flex items-center justify-center">
        <Megaphone className="h-7 w-7 text-muted-foreground" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">{label} — coming soon</h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-md">
          {label} campaigns will plug into this same view. No navigation change needed
          when the integration lands.
        </p>
      </div>
    </div>
  );
}

function CampaignsContent() {
  const searchParams = useSearchParams();
  const initial = (searchParams.get('platform') as PlatformKey) || 'google';
  const [active, setActive] = useState<PlatformKey>(
    PLATFORMS.some((p) => p.key === initial) ? initial : 'google'
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <Megaphone className="h-7 w-7 text-primary" />
          Campaigns
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage paid and lifecycle campaigns across every channel in one place.
        </p>
      </div>

      {/* Platform tabs */}
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto">
        {PLATFORMS.map((p) => {
          const Icon = p.icon;
          const isActive = active === p.key;
          return (
            <button
              key={p.key}
              onClick={() => setActive(p.key)}
              className={`relative flex items-center gap-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors cursor-pointer ${
                isActive
                  ? 'text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon className="h-4 w-4" />
              {p.label}
              {!p.live && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                  Soon
                </span>
              )}
              {isActive && (
                <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-primary rounded-full" />
              )}
            </button>
          );
        })}
      </div>

      {active === 'google' ? (
        <GoogleAdsPanel />
      ) : (
        <ComingSoonPanel label={PLATFORMS.find((p) => p.key === active)?.label ?? 'This channel'} />
      )}
    </div>
  );
}

export default function CampaignsPage() {
  return (
    <Suspense>
      <CampaignsContent />
    </Suspense>
  );
}
