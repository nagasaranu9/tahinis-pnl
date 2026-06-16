"use client";

import { MapPin, ChevronDown } from "lucide-react";
import { useLocations } from "@/hooks/use-locations";

export function LocationSelector() {
  const { locations, selectedLocationId, setLocation, isLoading } = useLocations();

  const selected = locations.find((l) => l.id === selectedLocationId);

  if (isLoading) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-2 py-1.5">
        <MapPin className="h-3.5 w-3.5" />
        <span>Loading…</span>
      </div>
    );
  }

  if (locations.length === 0) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-2 py-1.5">
        <MapPin className="h-3.5 w-3.5" />
        <span>No locations</span>
      </div>
    );
  }

  if (locations.length === 1) {
    const loc = selected ?? locations[0];
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-2 py-1.5">
        <MapPin className="h-3.5 w-3.5 text-primary" />
        <span className="font-medium text-foreground">
          {loc.store_id ? `#${loc.store_id} · ${loc.name}` : loc.name}
        </span>
      </div>
    );
  }

  return (
    <div className="relative">
      <select
        value={selectedLocationId ?? ""}
        onChange={(e) => setLocation(e.target.value || null)}
        className="appearance-none flex items-center gap-1.5 text-xs pl-7 pr-6 py-1.5 bg-card border border-border rounded-md text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer hover:bg-muted/50 transition-colors"
      >
        {locations.map((loc) => (
          <option key={loc.id} value={loc.id}>
            {loc.store_id ? `#${loc.store_id} · ${loc.name}` : loc.name}
          </option>
        ))}
      </select>
      <MapPin className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-primary pointer-events-none" />
      <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
    </div>
  );
}
