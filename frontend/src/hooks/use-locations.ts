"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";
import { useLocationStore } from "@/lib/location-store";
import type { Location } from "@/types/location";

export function useLocations() {
  const { accessToken } = useAuthStore();
  const { selectedLocationId, setLocation } = useLocationStore();

  const query = useQuery<{ data: Location[] }>({
    queryKey: ["locations"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: Location[] }>("/api/v1/locations");
      return data;
    },
    enabled: !!accessToken,
  });

  // Auto-select first location, and clear stale IDs that no longer exist
  useEffect(() => {
    const locs = query.data?.data;
    if (!locs?.length) return;
    const ids = new Set(locs.map((l) => l.id));
    if (!selectedLocationId || !ids.has(selectedLocationId)) {
      setLocation(locs[0].id);
    }
  }, [query.data, selectedLocationId, setLocation]);

  return {
    ...query,
    locations: query.data?.data ?? [],
    selectedLocationId,
    setLocation,
  };
}
