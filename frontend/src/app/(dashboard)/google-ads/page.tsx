'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/**
 * Google Ads now lives inside Campaigns (Growth → Campaigns → Google Ads tab).
 * Keep this route as a redirect so old links / bookmarks still resolve.
 */
export default function GoogleAdsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/campaigns?platform=google');
  }, [router]);
  return (
    <div className="flex items-center justify-center py-24 text-sm text-muted-foreground">
      Redirecting to Campaigns…
    </div>
  );
}
