"use client";

import { useState } from "react";
import Link from "next/link";
import { Megaphone, ArrowRight, Star, TrendingUp, BarChart3, CheckCircle, Unplug } from "lucide-react";
import ReviewsPage from "../reviews/page";
import { PipeboardIntegration } from "@/components/pipeboard-integration";
import {
  useMetaAdsStatus,
  useMetaAdsConnect,
  useMetaAdsDisconnect,
} from "@/hooks/use-external-platforms";

type MarketingTab = "reviews" | "googleAds" | "metaAds" | "spendAnalytics";

const TABS: { key: MarketingTab; label: string; icon: typeof Star }[] = [
  { key: "reviews", label: "Reviews", icon: Star },
  { key: "googleAds", label: "Google Ads", icon: Megaphone },
  { key: "metaAds", label: "Meta Ads", icon: TrendingUp },
  { key: "spendAnalytics", label: "Spend Analytics", icon: BarChart3 },
];

function ComingSoon({ title, description }: { title: string; description: string }) {
  return (
    <div className="border border-border rounded-lg bg-card p-12 flex flex-col items-center gap-4 text-center">
      <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
        <Megaphone className="h-8 w-8 text-primary" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-md">{description}</p>
      </div>
      <Link
        href="/integrations"
        className="flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
      >
        Go to Integrations <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}


function MetaAdsConnector() {
  const { data: status, isLoading } = useMetaAdsStatus();
  const { mutate: connect, isPending: connecting, error } = useMetaAdsConnect();
  const { mutate: disconnect, isPending: disconnecting } = useMetaAdsDisconnect();
  const [adAccountId, setAdAccountId] = useState("");
  const [accessToken, setAccessToken] = useState("");

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  if (status?.connected) {
    return (
      <div className="border border-border rounded-lg bg-card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle className="h-4 w-4 text-green-400" />
            <span className="font-medium">Meta Ads connected</span>
            <span className="text-muted-foreground">— account {status.account_id}</span>
          </div>
          <button
            onClick={() => disconnect()}
            disabled={disconnecting}
            className="flex items-center gap-1 px-2 py-1 text-xs border border-destructive text-destructive rounded hover:bg-destructive/10 disabled:opacity-50"
          >
            <Unplug className="h-3 w-3" />
            Disconnect
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          Facebook + Instagram ad spend and performance sync daily into your P&L marketing line.
        </p>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg bg-card p-6 space-y-4">
      <div>
        <h3 className="font-semibold">Connect Meta Ads</h3>
        <p className="text-xs text-muted-foreground mt-1">
          From Meta Business Suite → Events Manager → System Users, grab your ad account ID and a long-lived access token with ads_read permission.
        </p>
      </div>
      <div className="grid gap-3 max-w-md">
        <input
          value={adAccountId}
          onChange={(e) => setAdAccountId(e.target.value)}
          placeholder="Ad account ID (e.g. act_1234567890)"
          className="px-3 py-2 text-sm rounded-md border border-border bg-background"
        />
        <input
          value={accessToken}
          onChange={(e) => setAccessToken(e.target.value)}
          placeholder="Access token"
          type="password"
          className="px-3 py-2 text-sm rounded-md border border-border bg-background"
        />
        {error && <p className="text-xs text-destructive">Connection failed. Check your credentials.</p>}
        <button
          onClick={() => connect({ ad_account_id: adAccountId, access_token: accessToken })}
          disabled={connecting || !adAccountId || !accessToken}
          className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:opacity-90 disabled:opacity-50 w-fit"
        >
          {connecting ? "Connecting…" : "Connect"}
        </button>
      </div>
    </div>
  );
}

export default function MarketingPage() {
  const [tab, setTab] = useState<MarketingTab>("reviews");

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Marketing</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Reviews, Google Ads, Meta Ads, and spend analytics.
        </p>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap shrink-0 ${
              tab === key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === "reviews" && <ReviewsPage />}
      {tab === "googleAds" && <PipeboardIntegration />}
      {tab === "metaAds" && <MetaAdsConnector />}
      {tab === "spendAnalytics" && (
        <ComingSoon
          title="Spend analytics coming soon"
          description="Cross-channel marketing spend trends and ROAS analysis, once ad platforms are connected."
        />
      )}
    </div>
  );
}
