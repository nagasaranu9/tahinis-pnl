"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Building2,
  MapPin,
  Loader2,
  Check,
  Hash,
  Phone,
  Mail,
  User,
  Clock,
  DollarSign,
  ChevronDown,
  ChevronUp,
  UtensilsCrossed,
  Search,
  AlertCircle,
} from "lucide-react";
import { useLocations } from "@/hooks/use-locations";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";
import { useQueryClient } from "@tanstack/react-query";
import type { Location, LocationContacts, BusinessHours } from "@/types/location";

// ─── Constants ────────────────────────────────────────────────────────────────

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;
const DAY_LABELS: Record<string, string> = {
  monday: "Mon", tuesday: "Tue", wednesday: "Wed", thursday: "Thu",
  friday: "Fri", saturday: "Sat", sunday: "Sun",
};

const CA_TIMEZONES = [
  { label: "Eastern (Toronto)", value: "America/Toronto" },
  { label: "Central (Winnipeg)", value: "America/Winnipeg" },
  { label: "Mountain (Calgary)", value: "America/Edmonton" },
  { label: "Pacific (Vancouver)", value: "America/Vancouver" },
  { label: "Atlantic (Halifax)", value: "America/Halifax" },
  { label: "Newfoundland (St. John's)", value: "America/St_Johns" },
];

const DEFAULT_CONTACTS: LocationContacts = {
  owner_1: { name: "", email: "", phone: "" },
  owner_2: { name: "", email: "", phone: "" },
  manager_1: { name: "", email: "", phone: "" },
  manager_2: { name: "", email: "", phone: "" },
};

const DEFAULT_HOURS: BusinessHours = Object.fromEntries(
  DAYS.map((d) => [d, { open: "09:00", close: "22:00", closed: false }])
);

// ─── Live clock ───────────────────────────────────────────────────────────────

function LiveClock({ timezone }: { timezone: string }) {
  const [time, setTime] = useState("");

  useEffect(() => {
    function tick() {
      try {
        setTime(
          new Intl.DateTimeFormat("en-CA", {
            timeZone: timezone,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: true,
          }).format(new Date())
        );
      } catch {
        setTime("—");
      }
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [timezone]);

  return <span className="font-mono tabular-nums text-foreground">{time || "—"}</span>;
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string;
  description?: string;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-5 py-4 border-b border-border bg-card flex items-start gap-3">
        {Icon && (
          <div className="h-8 w-8 rounded-md bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
            <Icon className="h-4 w-4 text-primary" />
          </div>
        )}
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
        </div>
      </div>
      <div className="p-5 bg-card">{children}</div>
    </div>
  );
}

// ─── Field ────────────────────────────────────────────────────────────────────

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        {label}
      </label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Input({
  value,
  onChange,
  placeholder,
  type = "text",
  mono = false,
  icon: Icon,
  readOnly,
}: {
  value: string;
  onChange?: (v: string) => void;
  placeholder?: string;
  type?: string;
  mono?: boolean;
  icon?: React.ComponentType<{ className?: string }>;
  readOnly?: boolean;
}) {
  return (
    <div className="relative">
      {Icon && (
        <Icon className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
      )}
      <input
        type={type}
        value={value}
        onChange={onChange ? (e) => onChange(e.target.value) : undefined}
        placeholder={placeholder}
        readOnly={readOnly}
        className={`w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary transition-colors ${
          Icon ? "pl-9" : ""
        } ${mono ? "font-mono" : ""} ${readOnly ? "cursor-not-allowed opacity-60" : ""}`}
      />
    </div>
  );
}

// ─── Contact Tile ─────────────────────────────────────────────────────────────

function ContactTile({
  title,
  contact,
  onChange,
}: {
  title: string;
  contact: { name: string; email: string; phone: string };
  onChange: (field: "name" | "email" | "phone", value: string) => void;
}) {
  return (
    <div className="border border-border rounded-lg p-4 space-y-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
        <User className="h-3 w-3" />
        {title}
      </p>
      <Input
        value={contact.name}
        onChange={(v) => onChange("name", v)}
        placeholder="Full name"
        icon={User}
      />
      <Input
        value={contact.email}
        onChange={(v) => onChange("email", v)}
        placeholder="email@example.com"
        type="email"
        icon={Mail}
      />
      <Input
        value={contact.phone}
        onChange={(v) => onChange("phone", v)}
        placeholder="+1 (416) 555-0100"
        type="tel"
        icon={Phone}
      />
    </div>
  );
}

// ─── Business Hours editor ────────────────────────────────────────────────────

function HoursEditor({
  hours,
  onChange,
}: {
  hours: BusinessHours;
  onChange: (h: BusinessHours) => void;
}) {
  return (
    <div className="space-y-2">
      {DAYS.map((day) => {
        const h = hours[day] ?? { open: "09:00", close: "22:00", closed: false };
        return (
          <div key={day} className="flex items-center gap-3">
            <span className="text-xs font-semibold text-muted-foreground w-8">{DAY_LABELS[day]}</span>
            <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
              <input
                type="checkbox"
                checked={h.closed}
                onChange={(e) =>
                  onChange({ ...hours, [day]: { ...h, closed: e.target.checked } })
                }
                className="h-3.5 w-3.5 rounded accent-primary"
              />
              <span className="text-xs text-muted-foreground">Closed</span>
            </label>
            {!h.closed && (
              <>
                <input
                  type="time"
                  value={h.open}
                  onChange={(e) => onChange({ ...hours, [day]: { ...h, open: e.target.value } })}
                  className="text-xs border border-input rounded px-2 py-1 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary w-28"
                />
                <span className="text-xs text-muted-foreground">–</span>
                <input
                  type="time"
                  value={h.close}
                  onChange={(e) => onChange({ ...hours, [day]: { ...h, close: e.target.value } })}
                  className="text-xs border border-input rounded px-2 py-1 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary w-28"
                />
              </>
            )}
            {h.closed && <span className="text-xs text-muted-foreground italic">Closed all day</span>}
          </div>
        );
      })}
    </div>
  );
}

// ─── Location Card ────────────────────────────────────────────────────────────

function LocationCard({ loc }: { loc: Location }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Basic fields
  const [name, setName] = useState(loc.name);
  const [address, setAddress] = useState(loc.address ?? "");
  // Invited locations default to "UTC" in the DB; coerce to Eastern so the live clock
  // and the dropdown agree (and saving persists a real IANA zone instead of UTC).
  const [timezone, setTimezone] = useState(
    loc.timezone && loc.timezone !== "UTC" ? loc.timezone : "America/Toronto"
  );
  const [storeId, setStoreId] = useState(loc.store_id ?? "");
  const [toastId, setToastId] = useState(loc.toast_location_id ?? "");
  const [rentMonthly, setRentMonthly] = useState(loc.rent_monthly_incl_hst ?? "");
  const [googlePlaceId, setGooglePlaceId] = useState(loc.google_place_id ?? "");

  // Complex fields
  const [hours, setHours] = useState<BusinessHours>(
    loc.business_hours ?? { ...DEFAULT_HOURS }
  );
  const [contacts, setContacts] = useState<LocationContacts>(
    loc.contacts
      ? {
          owner_1: loc.contacts.owner_1 ?? DEFAULT_CONTACTS.owner_1,
          owner_2: loc.contacts.owner_2 ?? DEFAULT_CONTACTS.owner_2,
          manager_1: loc.contacts.manager_1 ?? DEFAULT_CONTACTS.manager_1,
          manager_2: loc.contacts.manager_2 ?? DEFAULT_CONTACTS.manager_2,
        }
      : { ...DEFAULT_CONTACTS }
  );

  // Google Places Autocomplete (new API — PlaceAutocompleteElement)
  const autocompleteContainerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const autocompleteElementRef = useRef<any>(null);

  useEffect(() => {
    const GMAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!GMAPS_KEY) return;

    let mounted = true;

    async function initAutocomplete() {
      const container = autocompleteContainerRef.current;
      if (!container || autocompleteElementRef.current) return;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const g = (window as any).google;
      if (!g?.maps?.importLibrary) return;
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const { PlaceAutocompleteElement } = await g.maps.importLibrary("places") as any;
        if (!mounted || !autocompleteContainerRef.current) return;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const element = new PlaceAutocompleteElement({ componentRestrictions: { country: "ca" } }) as any;
        autocompleteElementRef.current = element;
        autocompleteContainerRef.current.appendChild(element);

        // New Places API (weekly) fires "gmp-select" with event.placePrediction
        element.addEventListener("gmp-select", async (event: any) => {
          if (!event.placePrediction) return;
          const place = event.placePrediction.toPlace();
          if (!place) return;

          try {
            await place.fetchFields({ fields: ["formattedAddress", "id", "utcOffsetMinutes"] });
          } catch { /* ignore */ }

          if (place.formattedAddress) setAddress(place.formattedAddress);
          if (place.id) setGooglePlaceId(place.id);

          if (typeof place.utcOffsetMinutes === "number") {
            const offset = place.utcOffsetMinutes;
            if (offset === -150) setTimezone("America/St_Johns");
            else if (offset === -180) setTimezone("America/Halifax");
            else if (offset === -240) setTimezone("America/Toronto");
            else if (offset === -300) setTimezone("America/Winnipeg");
            else if (offset === -360) setTimezone("America/Edmonton");
            else if (offset === -420) setTimezone("America/Vancouver");
          }

          // Opening hours — fetch separately, failures don't block address update
          try {
            await place.fetchFields({ fields: ["regularOpeningHours"] });
            if (place.regularOpeningHours?.periods) {
              const dayMap = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
              const newHours: BusinessHours = { ...DEFAULT_HOURS };
              DAYS.forEach((d) => { newHours[d] = { open: "09:00", close: "22:00", closed: true }; });
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              place.regularOpeningHours.periods.forEach((period: any) => {
                const dayName = dayMap[period.open?.day ?? 0];
                if (!dayName) return;
                const openStr = period.open?.hour != null
                  ? `${String(period.open.hour).padStart(2, "0")}:${String(period.open.minute ?? 0).padStart(2, "0")}`
                  : "09:00";
                const closeStr = period.close?.hour != null
                  ? `${String(period.close.hour).padStart(2, "0")}:${String(period.close.minute ?? 0).padStart(2, "0")}`
                  : "22:00";
                newHours[dayName] = { open: openStr, close: closeStr, closed: false };
              });
              setHours(newHours);
            }
          } catch { /* opening hours unavailable */ }
        });
      } catch { /* fallback to manual input */ }
    }

    initAutocomplete();
    const interval = setInterval(() => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if ((window as any).google?.maps?.importLibrary) {
        initAutocomplete();
        clearInterval(interval);
      }
    }, 300);
    return () => {
      mounted = false;
      clearInterval(interval);
      if (autocompleteElementRef.current && autocompleteContainerRef.current) {
        try { autocompleteContainerRef.current.removeChild(autocompleteElementRef.current); } catch { /* already removed */ }
        autocompleteElementRef.current = null;
      }
    };
  }, []);

  function updateContact(
    role: keyof LocationContacts,
    field: "name" | "email" | "phone",
    value: string
  ) {
    setContacts((prev) => ({
      ...prev,
      [role]: { ...prev[role], [field]: value },
    }));
  }

  async function handleSave() {
    if (storeId && !/^\d{4,5}$/.test(storeId)) {
      setError("Store ID must be 4-5 digits");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await apiClient.patch(`/api/v1/locations/${loc.id}`, {
        name: name || undefined,
        address: address || null,
        timezone,
        store_id: storeId || null,
        toast_location_id: toastId || null,
        google_place_id: googlePlaceId || null,
        business_hours: hours,
        rent_monthly_incl_hst: rentMonthly ? String(rentMonthly) : null,
        contacts,
      });
      await qc.invalidateQueries({ queryKey: ["locations"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      setError("Save failed — please try again");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      {/* Card header */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 bg-card hover:bg-accent/30 transition-colors cursor-pointer"
      >
        <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
          <MapPin className="h-4.5 w-4.5 text-primary" />
        </div>
        <div className="flex-1 text-left">
          <p className="text-sm font-semibold text-foreground">{loc.name}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {loc.address ?? "No address set"} · <LiveClock timezone={timezone} />
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
            loc.is_active ? "bg-green-500/10 text-green-500" : "bg-muted text-muted-foreground"
          }`}>
            {loc.is_active ? "Active" : "Inactive"}
          </span>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-border divide-y divide-border">

          {/* ── Identity ── */}
          <div className="p-5 space-y-4">
            <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Identity</p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Location Name">
                <Input value={name} onChange={setName} placeholder="e.g. King Street West" />
              </Field>
              <Field label="Store ID" hint="4-5 digits. Staff use this to log in.">
                <Input value={storeId} onChange={(v) => setStoreId(v.replace(/\D/g, "").slice(0, 5))} placeholder="e.g. 10001" mono />
              </Field>
            </div>

            <Field label="Address" hint="Search Google Maps to autofill address, timezone, and business hours.">
              <Input value={address} onChange={(v) => setAddress(v)} placeholder="123 King St W, Toronto, ON" />
              {process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY && (
                <div className="mt-2">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <Search className="h-3 w-3" /> Search Google Maps to autofill
                  </p>
                  <div ref={autocompleteContainerRef} className="gmp-autocomplete-container" />
                </div>
              )}
            </Field>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Timezone">
                <select
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
                >
                  {CA_TIMEZONES.map((tz) => (
                    <option key={tz.value} value={tz.value}>{tz.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="Current Local Time">
                <div className="flex items-center gap-2 h-9 px-3 py-2 border border-input rounded-md bg-muted/40 text-sm">
                  <Clock className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <LiveClock timezone={timezone} />
                </div>
              </Field>
            </div>

            <Field label="Monthly Rent (incl. HST)" hint="Used for P&L — not shared externally.">
              <div className="relative">
                <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={String(rentMonthly)}
                  onChange={(e) => setRentMonthly(e.target.value)}
                  placeholder="e.g. 8500.00"
                  className="w-full pl-9 pr-3 py-2 text-sm border border-input rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                />
              </div>
            </Field>
          </div>

          {/* ── Platform IDs ── */}
          <div className="p-5 space-y-4">
            <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Platform Integration IDs</p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Toast POS ID">
                <Input value={toastId} onChange={setToastId} placeholder="Toast restaurant GUID" icon={Hash} mono />
              </Field>
              {googlePlaceId && (
                <Field label="Google Place ID" hint="Auto-filled from address search.">
                  <Input value={googlePlaceId} readOnly mono />
                </Field>
              )}
            </div>
          </div>

          {/* ── Business Hours ── */}
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Business Hours</p>
              {!process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY && (
                <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" />
                  Add Google Maps key to auto-fill from address
                </span>
              )}
            </div>
            <HoursEditor hours={hours} onChange={setHours} />
          </div>

          {/* ── Contacts ── */}
          <div className="p-5 space-y-4">
            <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Contacts</p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <ContactTile
                title="Owner 1"
                contact={contacts.owner_1}
                onChange={(f, v) => updateContact("owner_1", f, v)}
              />
              <ContactTile
                title="Owner 2"
                contact={contacts.owner_2}
                onChange={(f, v) => updateContact("owner_2", f, v)}
              />
              <ContactTile
                title="Manager 1"
                contact={contacts.manager_1}
                onChange={(f, v) => updateContact("manager_1", f, v)}
              />
              <ContactTile
                title="Manager 2"
                contact={contacts.manager_2}
                onChange={(f, v) => updateContact("manager_2", f, v)}
              />
            </div>
          </div>

          {/* ── Save bar ── */}
          <div className="px-5 py-4 flex items-center justify-between gap-3 bg-muted/30">
            {error && (
              <p className="text-xs text-destructive flex items-center gap-1.5">
                <AlertCircle className="h-3.5 w-3.5" /> {error}
              </p>
            )}
            {!error && saved && (
              <p className="text-xs text-green-500 flex items-center gap-1.5">
                <Check className="h-3.5 w-3.5" /> Saved successfully
              </p>
            )}
            {!error && !saved && <div />}
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground text-sm font-semibold rounded-md hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer"
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {saved ? <><Check className="h-3.5 w-3.5" /> Saved</> : saving ? "Saving…" : "Save Location"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { locations, isLoading: locLoading } = useLocations();
  const { accessToken } = useAuthStore();
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [addSaving, setAddSaving] = useState(false);
  const [addSaved, setAddSaved] = useState(false);

  const tenantId = (() => {
    if (!accessToken) return "—";
    try {
      const payload = JSON.parse(atob(accessToken.split(".")[1]));
      return payload.tenant_id ?? "—";
    } catch {
      return "—";
    }
  })();

  async function handleAddLocation(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const storeId = fd.get("store_id") as string;
    if (storeId && !/^\d{4,5}$/.test(storeId)) return;
    setAddSaving(true);
    try {
      await apiClient.post("/api/v1/locations", {
        name: fd.get("name"),
        address: (fd.get("address") as string) || null,
        timezone: (fd.get("timezone") as string) || "America/Toronto",
        store_id: storeId || null,
      });
      await qc.invalidateQueries({ queryKey: ["locations"] });
      setAddSaved(true);
      setTimeout(() => { setAddSaved(false); setAddOpen(false); }, 1500);
      (e.target as HTMLFormElement).reset();
    } finally {
      setAddSaving(false);
    }
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage tenant profile, locations, integrations, and contacts
        </p>
      </div>

      {/* Tenant */}
      <Section title="Organization" description="Your tenant profile" icon={Building2}>
        <div className="flex items-center gap-4">
          <div className="h-12 w-12 rounded-xl bg-primary/15 flex items-center justify-center shrink-0">
            <Building2 className="h-6 w-6 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold">Tahinis Restaurant Group</p>
            <p className="text-xs text-muted-foreground">Owner</p>
          </div>
        </div>
        <div className="mt-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1.5 font-semibold">Tenant ID</p>
          <p className="text-sm font-mono bg-muted px-3 py-2 rounded-md text-foreground break-all select-all">
            {tenantId}
          </p>
        </div>
      </Section>

      {/* Locations */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">Locations</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Configure each restaurant location — IDs, hours, contacts, and rent.
            </p>
          </div>
          <button
            onClick={() => setAddOpen(!addOpen)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold border border-primary/30 text-primary rounded-md hover:bg-primary/10 transition-colors cursor-pointer"
          >
            + Add Location
          </button>
        </div>

        {locLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-6">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading locations…
          </div>
        ) : locations.length === 0 ? (
          <div className="border border-dashed border-border rounded-xl p-8 text-center text-sm text-muted-foreground">
            No locations yet. Add your first location below.
          </div>
        ) : (
          <div className="space-y-3">
            {locations.map((loc) => (
              <LocationCard key={loc.id} loc={loc} />
            ))}
          </div>
        )}

        {/* Add location form */}
        {addOpen && (
          <form
            onSubmit={handleAddLocation}
            className="border border-border rounded-xl p-5 space-y-4 bg-card"
          >
            <p className="text-sm font-semibold">New Location</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 block">Name *</label>
                <input
                  name="name"
                  required
                  placeholder="e.g. King Street West"
                  className="w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 block">Store ID</label>
                <input
                  name="store_id"
                  placeholder="10001"
                  maxLength={5}
                  inputMode="numeric"
                  className="w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 block">Address</label>
                <input
                  name="address"
                  placeholder="123 King St W, Toronto"
                  className="w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 block">Timezone</label>
                <select
                  name="timezone"
                  defaultValue="America/Toronto"
                  className="w-full px-3 py-2 text-sm border border-input rounded-md bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
                >
                  {CA_TIMEZONES.map((tz) => (
                    <option key={tz.value} value={tz.value}>{tz.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex items-center gap-2 justify-end">
              <button
                type="button"
                onClick={() => setAddOpen(false)}
                className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={addSaving}
                className="flex items-center gap-2 px-4 py-1.5 bg-primary text-primary-foreground text-sm font-semibold rounded-md hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {addSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : addSaved ? <Check className="h-3.5 w-3.5" /> : null}
                {addSaved ? "Added!" : addSaving ? "Adding…" : "Add Location"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
