"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, LogOut, Mail, MoreHorizontal, Plus, Store } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";
import { useLocationStore } from "@/lib/location-store";
import type { Location } from "@/types/location";

const HQ_STORE_ID = "1000";

export default function LocationsHomePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { accessToken, getLocationId, clearTokens } = useAuthStore();
  const { setLocation } = useLocationStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Location | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Location | null>(null);

  useEffect(() => {
    if (accessToken && getLocationId() !== null) {
      router.replace("/dashboard");
    }
  }, [accessToken, getLocationId, router]);

  const { data, isLoading } = useQuery<{ data: Location[] }>({
    queryKey: ["locations"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: Location[] }>("/api/v1/locations");
      return data;
    },
    enabled: !!accessToken,
  });

  const tiles = (data?.data ?? []).filter((l) => l.store_id !== HQ_STORE_ID);

  function openLocation(loc: Location) {
    setLocation(loc.id);
    router.push("/dashboard");
  }

  async function toggleDisable(loc: Location) {
    await apiClient.patch(`/api/v1/locations/${loc.id}`, { is_active: !loc.is_active });
    queryClient.invalidateQueries({ queryKey: ["locations"] });
  }

  async function deleteLocation(loc: Location) {
    await apiClient.delete(`/api/v1/locations/${loc.id}`);
    queryClient.invalidateQueries({ queryKey: ["locations"] });
    setDeleteTarget(null);
  }

  function handleLogout() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen bg-muted/20">
      <header className="h-14 flex items-center justify-between px-6 border-b border-border bg-card">
        <div className="flex items-center gap-2.5">
          <Image
            src="/tahinis-logo.png"
            alt="Tahini's Mediterranean Fusion"
            width={26}
            height={26}
            className="object-contain rounded-md"
            priority
          />
          <span className="text-[15px] font-semibold text-foreground tracking-tight">
            Locations
          </span>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </button>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-xl font-semibold text-foreground">Your locations</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Select a location to view its dashboard, or add a new one.
            </p>
          </div>
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-2 text-sm font-medium bg-primary text-primary-foreground px-4 py-2.5 rounded-md hover:opacity-90 transition-opacity cursor-pointer"
          >
            <Plus className="h-4 w-4" />
            Add Location
          </button>
        </div>

        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading locations…</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {tiles.map((loc) => (
              <LocationTile
                key={loc.id}
                loc={loc}
                onOpen={() => loc.invite_status !== "pending" && loc.is_active && openLocation(loc)}
                onEdit={() => setEditTarget(loc)}
                onToggleDisable={() => toggleDisable(loc)}
                onDelete={() => setDeleteTarget(loc)}
              />
            ))}
          </div>
        )}
      </main>

      {modalOpen && (
        <AddLocationModal
          onClose={() => setModalOpen(false)}
          onCreated={() => {
            setModalOpen(false);
            queryClient.invalidateQueries({ queryKey: ["locations"] });
          }}
        />
      )}

      {editTarget && (
        <EditLocationModal
          loc={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => {
            setEditTarget(null);
            queryClient.invalidateQueries({ queryKey: ["locations"] });
          }}
        />
      )}

      {deleteTarget && (
        <ConfirmDeleteModal
          loc={deleteTarget}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteLocation(deleteTarget)}
        />
      )}
    </div>
  );
}

function LocationTile({
  loc,
  onOpen,
  onEdit,
  onToggleDisable,
  onDelete,
}: {
  loc: Location;
  onOpen: () => void;
  onEdit: () => void;
  onToggleDisable: () => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const clickable = loc.invite_status !== "pending" && loc.is_active;

  return (
    <div
      className={`relative p-5 rounded-lg border border-border bg-card transition-all ${
        clickable ? "hover:border-primary/50 hover:shadow-sm cursor-pointer" : "opacity-70 cursor-default"
      } ${!loc.is_active ? "opacity-50" : ""}`}
    >
      {/* Main clickable area */}
      <div onClick={onOpen} className="select-none">
        <div className="flex items-center justify-between mb-3">
          <div className="h-9 w-9 rounded-md bg-primary/10 flex items-center justify-center">
            <Store className="h-4 w-4 text-primary" />
          </div>
          <div className="flex items-center gap-2">
            {loc.invite_status === "pending" && (
              <span className="flex items-center gap-1 text-[11px] font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
                <Clock className="h-3 w-3" />
                Invite pending
              </span>
            )}
            {!loc.is_active && (
              <span className="text-[11px] font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                Disabled
              </span>
            )}
          </div>
        </div>
        <div className="font-medium text-foreground text-[15px]">
          {loc.store_id ? `#${loc.store_id} - ${loc.name}` : loc.name}
        </div>
        {loc.invite_status === "pending" && loc.invite_email && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1.5">
            <Mail className="h-3 w-3" />
            {loc.invite_email}
          </div>
        )}
        {loc.address && loc.invite_status !== "pending" && (
          <div className="text-xs text-muted-foreground mt-1.5 truncate">{loc.address}</div>
        )}
      </div>

      {/* ⋯ menu */}
      <div ref={menuRef} className="absolute top-3 right-3">
        <button
          onClick={(e) => { e.stopPropagation(); setMenuOpen((o) => !o); }}
          className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          aria-label="Location options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>

        {menuOpen && (
          <div className="absolute right-0 top-8 z-50 w-44 bg-card border border-border rounded-lg shadow-lg overflow-hidden">
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onEdit(); }}
              className="w-full text-left px-3.5 py-2.5 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Edit
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onToggleDisable(); }}
              className="w-full text-left px-3.5 py-2.5 text-sm text-foreground hover:bg-muted transition-colors"
            >
              {loc.is_active ? "Disable" : "Enable"}
            </button>
            <div className="border-t border-border" />
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onDelete(); }}
              className="w-full text-left px-3.5 py-2.5 text-sm text-destructive hover:bg-destructive/10 transition-colors"
            >
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function EditLocationModal({
  loc,
  onClose,
  onSaved,
}: {
  loc: Location;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(loc.name);
  const [address, setAddress] = useState(loc.address ?? "");
  const [timezone, setTimezone] = useState(loc.timezone ?? "America/Toronto");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await apiClient.patch(`/api/v1/locations/${loc.id}`, { name, address: address || null, timezone });
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { errors?: { message?: string }[] } } })?.response?.data
          ?.errors?.[0]?.message ?? "Could not save changes.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="bg-card rounded-lg shadow-xl border border-border w-full max-w-sm p-6">
        <h2 className="text-base font-semibold text-foreground mb-4">
          Edit {loc.store_id ? `#${loc.store_id}` : loc.name}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">Location name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">Address</label>
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="123 Main St, Toronto"
              className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">Timezone</label>
            <input
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              placeholder="America/Toronto"
              className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 text-sm font-medium border border-border py-2.5 rounded-md hover:bg-muted transition-colors cursor-pointer">
              Cancel
            </button>
            <button type="submit" disabled={loading}
              className="flex-1 text-sm font-medium bg-primary text-primary-foreground py-2.5 rounded-md hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50">
              {loading ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ConfirmDeleteModal({
  loc,
  onCancel,
  onConfirm,
}: {
  loc: Location;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="bg-card rounded-lg shadow-xl border border-border w-full max-w-sm p-6">
        <h2 className="text-base font-semibold text-foreground mb-2">Delete location?</h2>
        <p className="text-sm text-muted-foreground mb-5">
          <span className="font-medium text-foreground">
            {loc.store_id ? `#${loc.store_id} - ${loc.name}` : loc.name}
          </span>{" "}
          will be deactivated. This cannot be undone.
        </p>
        <div className="flex gap-2">
          <button onClick={onCancel}
            className="flex-1 text-sm font-medium border border-border py-2.5 rounded-md hover:bg-muted transition-colors cursor-pointer">
            Cancel
          </button>
          <button onClick={onConfirm}
            className="flex-1 text-sm font-medium bg-destructive text-white py-2.5 rounded-md hover:opacity-90 transition-opacity cursor-pointer">
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

function AddLocationModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [storeId, setStoreId] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { data } = await apiClient.post<{ data: { invite_url: string } }>(
        "/api/v1/locations/invite",
        { store_id: storeId, name, invite_email: email }
      );
      setInviteUrl(data.data.invite_url);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { errors?: { message?: string }[] } } })?.response?.data
          ?.errors?.[0]?.message ?? "Could not create location.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="bg-card rounded-lg shadow-xl border border-border w-full max-w-sm p-6">
        {inviteUrl ? (
          <div>
            <h2 className="text-base font-semibold text-foreground mb-2">Invite sent</h2>
            <p className="text-sm text-muted-foreground mb-3">
              Share this setup link with the new location&apos;s owner (also emailed if SMTP is
              configured):
            </p>
            <div className="text-xs bg-muted p-2.5 rounded-md break-all font-mono mb-4">
              {inviteUrl}
            </div>
            <button
              onClick={onCreated}
              className="w-full text-sm font-medium bg-primary text-primary-foreground py-2.5 rounded-md hover:opacity-90 transition-opacity cursor-pointer"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <h2 className="text-base font-semibold text-foreground mb-4">Add Location</h2>
            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Store number
                </label>
                <input
                  value={storeId}
                  onChange={(e) => setStoreId(e.target.value.replace(/\D/g, "").slice(0, 5))}
                  placeholder="e.g. 2104"
                  required
                  inputMode="numeric"
                  className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Location name
                </label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. King St West"
                  required
                  className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Owner email invite
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="owner@restaurant.com"
                  required
                  className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>
            <div className="flex gap-2 mt-5">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 text-sm font-medium border border-border py-2.5 rounded-md hover:bg-muted transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 text-sm font-medium bg-primary text-primary-foreground py-2.5 rounded-md hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50"
              >
                {loading ? "Sending…" : "Send invite"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
