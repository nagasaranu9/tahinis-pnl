"use client";

import Link from "next/link";
import { useRef, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { format } from "date-fns";
import {
  CheckCircle, RefreshCw, Unplug, Plug, AlertCircle, ArrowRight, Upload,
  Users, Megaphone, Store, MoreHorizontal, ChevronDown, ShieldCheck, Clock,
} from "lucide-react";
import {
  useGmailStatus, useGmailAuthUrl, useGmailSync, useGmailDisconnect,
  useOutlookStatus, useOutlookAuthUrl, useOutlookSync, useOutlookDisconnect,
} from "@/hooks/use-email-integrations";
import { useImportPushOpsCsv } from "@/hooks/use-pushops-integration";
import { PipeboardIntegration } from "@/components/pipeboard-integration";
import { useLocations } from "@/hooks/use-locations";
import type { EmailSyncConfig } from "@/types/email-sync";

// ---------------------------------------------------------------------------
// Brand logo — official mark via Simple Icons CDN, graceful icon fallback
// ---------------------------------------------------------------------------

// Logo resolution is a 3-tier fallback chain because Simple Icons has dropped
// several brand marks (Microsoft, Toast) over trademark policy, so a fixed slug
// can 404. Tier 1: Simple Icons (crisp SVG). Tier 2: Google favicon service by
// domain (always resolves, colored). Tier 3: the provided icon.
function BrandLogo({ slug, domain, fallback }: {
  slug?: string;
  domain?: string;
  fallback: React.ReactNode;
}) {
  const [tier, setTier] = useState<0 | 1 | 2>(0);

  const src =
    tier === 0 && slug
      ? `https://cdn.simpleicons.org/${slug}`
      : tier <= 1 && domain
        ? `https://www.google.com/s2/favicons?domain=${domain}&sz=64`
        : null;

  return (
    <div className="h-10 w-10 rounded-lg bg-muted/60 flex items-center justify-center shrink-0 overflow-hidden">
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          width={20}
          height={20}
          className="h-5 w-5"
          onError={() => setTier((t) => (t === 0 ? (domain ? 1 : 2) : 2))}
        />
      ) : (
        fallback
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Confirm dialog — modal overlay for dangerous actions
// ---------------------------------------------------------------------------

function ConfirmDialog({
  open, title, message, confirmLabel, onConfirm, onCancel, pending,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onCancel} />
      <div className="relative w-full max-w-sm rounded-xl border border-border bg-card p-5 shadow-xl space-y-4">
        <div className="flex items-start gap-3">
          <div className="h-9 w-9 rounded-lg bg-destructive/10 flex items-center justify-center shrink-0">
            <AlertCircle className="h-4.5 w-4.5 text-destructive" />
          </div>
          <div>
            <h3 className="font-semibold text-sm">{title}</h3>
            <p className="text-xs text-muted-foreground mt-1">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={pending}
            className="px-3 py-1.5 text-sm rounded-md border border-border hover:bg-muted/50 transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={pending}
            className="px-3 py-1.5 text-sm rounded-md bg-destructive text-destructive-foreground font-semibold hover:bg-destructive/90 transition-colors cursor-pointer disabled:opacity-50"
          >
            {pending ? "Removing…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overflow menu — houses dangerous actions (never inline on card)
// ---------------------------------------------------------------------------

function OverflowMenu({ children }: { children: (close: () => void) => React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="h-8 w-8 flex items-center justify-center rounded-md border border-border hover:bg-muted/50 transition-colors cursor-pointer"
        aria-label="More options"
      >
        <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 rounded-md border border-border bg-card shadow-lg z-20 py-1">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PushOperations payroll CSV import card
// ---------------------------------------------------------------------------

function PushOpsCard() {
  const { selectedLocationId } = useLocations();
  const { mutate, isPending, data, error, reset } = useImportPushOpsCsv();
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    reset();
    mutate({ file, location_id: selectedLocationId ?? undefined });
    e.target.value = ""; // allow re-selecting the same file
  }

  const errMsg =
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
    (error ? "Import failed. Check the file format." : null);

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <BrandLogo fallback={<Users className="h-5 w-5 text-primary" />} />
          <div>
            <h3 className="font-semibold text-sm">PushOperations Payroll</h3>
            <p className="text-xs text-muted-foreground">
              Upload a payroll CSV — or a screenshot/PDF — to import labor cost into your P&amp;L
            </p>
          </div>
        </div>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer shrink-0"
        >
          <Upload className="h-3.5 w-3.5" />
          {isPending ? "Importing…" : "Upload CSV / Image"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv,image/png,image/jpeg,image/tiff,image/webp,application/pdf,.pdf"
          className="hidden"
          onChange={onFile}
        />
      </div>

      {data && (
        <div className="border-t border-border pt-3 text-sm space-y-1">
          <div className="flex items-center gap-2 text-green-500">
            <CheckCircle className="h-4 w-4 shrink-0" />
            <span className="font-medium">
              Imported {data.expenses_created} payroll line
              {data.expenses_created === 1 ? "" : "s"}
              {fileName ? ` from ${fileName}` : ""}
            </span>
          </div>
          <p className="text-xs text-muted-foreground pl-6">
            {data.currency_code} {Number(data.total_amount).toLocaleString()} total labor ·{" "}
            {data.duplicates_skipped} duplicate{data.duplicates_skipped === 1 ? "" : "s"} skipped ·{" "}
            {data.rows_parsed} rows parsed
          </p>
        </div>
      )}

      {errMsg && (
        <div className="border-t border-border pt-3 flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {errMsg}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Connected integration row — compact, green accent, expandable details.
// Sync inline; dangerous actions live only in the overflow menu.
// ---------------------------------------------------------------------------

function ConnectedRow({
  account, syncing, disconnecting, onSync, onDisconnect,
}: {
  account: EmailSyncConfig;
  syncing: boolean;
  disconnecting: boolean;
  onSync: (id: string) => void;
  onDisconnect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const lastMs = account.last_synced_at ? new Date(account.last_synced_at).getTime() : 0;
  // Auto-sync runs every 6h; flag stale if no successful sync in >12h.
  const stale = !account.last_synced_at || Date.now() - lastMs > 12 * 60 * 60 * 1000;
  const lastLabel = account.last_synced_at
    ? format(new Date(account.last_synced_at), "MMM d, HH:mm")
    : "Never";

  return (
    <div className="rounded-lg border border-green-500/30 bg-green-500/[0.04] overflow-hidden">
      <div className="flex items-center justify-between gap-3 p-3">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-2 min-w-0 text-left cursor-pointer"
        >
          <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
          <div className="min-w-0">
            <p className="font-medium text-sm truncate">{account.email_address ?? "Connected"}</p>
            <p className="text-xs text-muted-foreground">Last sync: {lastLabel}</p>
          </div>
          <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => onSync(account.id)}
            disabled={syncing}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-border rounded-md bg-card hover:bg-muted/50 disabled:opacity-50 transition-colors cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
            Sync now
          </button>
          <OverflowMenu>
            {(close) => (
              <button
                onClick={() => { close(); setConfirmOpen(true); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
              >
                <Unplug className="h-3.5 w-3.5" />
                Disconnect
              </button>
            )}
          </OverflowMenu>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-green-500/20 px-3 py-3 space-y-2 text-xs">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <p className="text-muted-foreground">Account</p>
              <p className="font-medium">{account.email_address ?? "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Sync frequency</p>
              <p className="font-medium">Every 6 hours</p>
            </div>
            <div>
              <p className="text-muted-foreground">Last successful sync</p>
              <p className="font-medium">{lastLabel}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Status</p>
              <p className={`font-medium ${stale ? "text-amber-500" : "text-green-500"}`}>
                {stale ? "Attention needed" : "Healthy"}
              </p>
            </div>
          </div>
          {stale && (
            <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-md px-2.5 py-1.5">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              <span>
                No successful sync in over 12h. Auto-sync runs every 6h — click Sync now to retry. If it keeps failing, disconnect and reconnect (token may have expired).
              </span>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Disconnect account?"
        message={`This removes ${account.email_address ?? "this account"} and stops syncing. Imported data is kept. You can reconnect anytime.`}
        confirmLabel="Disconnect"
        pending={disconnecting}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => { onDisconnect(account.id); setConfirmOpen(false); }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Available integration card — higher contrast, single primary Connect button
// ---------------------------------------------------------------------------

function AvailableCard({
  title, description, slug, domain, fallbackIcon, onConnect, connecting,
}: {
  title: string;
  description: string;
  slug?: string;
  domain?: string;
  fallbackIcon: React.ReactNode;
  onConnect: () => void;
  connecting: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 hover:border-primary/40 transition-colors">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <BrandLogo slug={slug} domain={domain} fallback={fallbackIcon} />
          <div>
            <h3 className="font-semibold text-sm">{title}</h3>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
        </div>
        <button
          onClick={onConnect}
          disabled={connecting}
          className="flex items-center gap-1.5 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer shrink-0"
        >
          <Plug className="h-3.5 w-3.5" />
          {connecting ? "Connecting…" : "Connect"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Email integration — renders connected rows OR an available card
// ---------------------------------------------------------------------------

function EmailIntegration({
  title, description, slug, domain, fallbackIcon, accounts, isLoading,
  onConnect, onSync, onDisconnect, connecting, syncing, disconnecting,
  defaultCollapsed = false,
}: {
  title: string;
  description: string;
  slug?: string;
  domain?: string;
  fallbackIcon: React.ReactNode;
  accounts: EmailSyncConfig[];
  isLoading: boolean;
  onConnect: () => void;
  onSync: (id: string) => void;
  onDisconnect: (id: string) => void;
  connecting: boolean;
  syncing: boolean;
  disconnecting: boolean;
  defaultCollapsed?: boolean;
}) {
  const connected = accounts.filter((a) => a.is_active);
  const [open, setOpen] = useState(!defaultCollapsed);

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
        Loading {title}…
      </div>
    );
  }

  if (connected.length === 0) {
    return (
      <AvailableCard
        title={title}
        description={description}
        slug={slug}
        domain={domain}
        fallbackIcon={fallbackIcon}
        onConnect={onConnect}
        connecting={connecting}
      />
    );
  }

  return (
    <div className="rounded-lg border border-green-500/30 bg-green-500/[0.04] p-4 space-y-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 text-left cursor-pointer"
      >
        <BrandLogo slug={slug} domain={domain} fallback={fallbackIcon} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
            <h3 className="font-semibold text-sm">{title}</h3>
          </div>
          <p className="text-xs text-muted-foreground truncate">
            {connected.length} account{connected.length === 1 ? "" : "s"} connected · {description}
          </p>
        </div>
        <ChevronDown className={`h-4 w-4 text-muted-foreground shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="space-y-2">
          {connected.map((account) => (
            <ConnectedRow
              key={account.id}
              account={account}
              syncing={syncing}
              disconnecting={disconnecting}
              onSync={onSync}
              onDisconnect={onDisconnect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Google Ads (Pipeboard) — collapsible, minimized by default
// ---------------------------------------------------------------------------

function PipeboardCard() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-green-500/30 bg-green-500/[0.04] p-4 space-y-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 text-left cursor-pointer"
      >
        <BrandLogo slug="googleads" domain="ads.google.com" fallback={<Megaphone className="h-5 w-5 text-primary" />} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
            <h3 className="font-semibold text-sm">Google Ads (Pipeboard)</h3>
          </div>
          <p className="text-xs text-muted-foreground truncate">
            Sync Google Ads spend &amp; performance into your P&amp;L marketing line
          </p>
        </div>
        <ChevronDown className={`h-4 w-4 text-muted-foreground shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <PipeboardIntegration />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Coming soon row
// ---------------------------------------------------------------------------

function ComingSoonRow({ title, description, slug, domain, fallbackIcon }: {
  title: string;
  description: string;
  slug?: string;
  domain?: string;
  fallbackIcon: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card/50 p-4">
      <div className="flex items-center gap-3">
        <BrandLogo slug={slug} domain={domain} fallback={fallbackIcon} />
        <div>
          <h3 className="font-semibold text-sm">{title}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <span className="px-3 py-1.5 text-xs font-medium rounded-md bg-muted text-muted-foreground shrink-0">
        Coming soon
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section header with count
// ---------------------------------------------------------------------------

function SectionHeader({ dot, title, count, subtitle, action }: {
  dot: string;
  title: string;
  count: number;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${dot}`} />
          <h2 className="font-semibold text-sm">{title}</h2>
          <span className="text-sm text-muted-foreground">({count})</span>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COMING_SOON = [
  { title: "Dropbox", description: "Import files from Dropbox", slug: "dropbox", domain: "dropbox.com" },
  { title: "QuickBooks Online", description: "Sync financial data and transactions", slug: "quickbooks", domain: "quickbooks.intuit.com" },
  { title: "Google Drive", description: "Import files from Google Drive", slug: "googledrive", domain: "drive.google.com" },
];

export default function IntegrationsPage() {
  const params = useSearchParams();
  const connectedParam = params.get("connected");
  const error = params.get("error");
  const errorReason = params.get("reason");

  const { data: gmailAccounts = [], isLoading: gmailLoading } = useGmailStatus();
  const { data: outlookAccounts = [], isLoading: outlookLoading } = useOutlookStatus();
  const { mutate: connectGmail, isPending: connectingGmail } = useGmailAuthUrl();
  const { mutate: syncGmail, isPending: syncingGmail } = useGmailSync();
  const { mutate: disconnectGmail, isPending: disconnectingGmail } = useGmailDisconnect();

  const { mutate: connectOutlook, isPending: connectingOutlook } = useOutlookAuthUrl();
  const { mutate: syncOutlook, isPending: syncingOutlook } = useOutlookSync();
  const { mutate: disconnectOutlook, isPending: disconnectingOutlook } = useOutlookDisconnect();

  const gmailConnected = gmailAccounts.filter((a) => a.is_active).length > 0;
  const outlookConnected = outlookAccounts.filter((a) => a.is_active).length > 0;
  // Toast + Pipeboard (Google Ads) are always-connected surfaces on this page.
  const connectedCount = 2 + (gmailConnected ? 1 : 0) + (outlookConnected ? 1 : 0);
  // PushOps is an upload (no persistent connection); count it under Not connected.
  const notConnectedCount = 1 + (gmailConnected ? 0 : 1) + (outlookConnected ? 0 : 1);
  const anyStale =
    [...gmailAccounts, ...outlookAccounts]
      .filter((a) => a.is_active)
      .some((a) => !a.last_synced_at || Date.now() - new Date(a.last_synced_at).getTime() > 12 * 60 * 60 * 1000);

  const gmailEl = (
    <EmailIntegration
      title="Gmail"
      description="Import invoices and receipts from Gmail attachments"
      slug="gmail"
      domain="gmail.com"
      fallbackIcon={<span className="text-sm font-bold text-primary">G</span>}
      accounts={gmailAccounts}
      isLoading={gmailLoading}
      onConnect={() => connectGmail()}
      onSync={syncGmail}
      onDisconnect={disconnectGmail}
      connecting={connectingGmail}
      syncing={syncingGmail}
      disconnecting={disconnectingGmail}
      defaultCollapsed
    />
  );

  const outlookEl = (
    <EmailIntegration
      title="Outlook / Microsoft 365"
      description="Import invoices and receipts from Outlook attachments"
      slug="microsoftoutlook"
      domain="outlook.com"
      fallbackIcon={<span className="text-sm font-bold text-primary">O</span>}
      accounts={outlookAccounts}
      isLoading={outlookLoading}
      onConnect={() => connectOutlook()}
      onSync={syncOutlook}
      onDisconnect={disconnectOutlook}
      connecting={connectingOutlook}
      syncing={syncingOutlook}
      disconnecting={disconnectingOutlook}
    />
  );

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Integrations</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Connect and sync your tools to keep sales and financial data in one place.
        </p>
      </div>

      {connectedParam && (
        <div className="flex items-center gap-2 text-sm text-green-500 bg-green-500/10 border border-green-500/20 rounded-md px-4 py-2">
          <CheckCircle className="h-4 w-4 shrink-0" />
          Successfully connected {connectedParam === "gmail" ? "Gmail" : "Outlook"}.
        </div>
      )}
      {error && (
        <div className="flex items-start gap-2 text-sm text-destructive bg-destructive/5 border border-destructive/20 rounded-md px-4 py-2">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            <div>Connection failed. Please try again.</div>
            {errorReason && (
              <div className="text-xs text-destructive/80 mt-1 break-words">{errorReason}</div>
            )}
          </div>
        </div>
      )}

      {/* ── Connected ── */}
      <section className="rounded-xl border border-border p-4 space-y-4">
        <SectionHeader
          dot="bg-green-500"
          title="Connected"
          count={connectedCount}
          subtitle="These integrations are active and syncing."
          action={
            <span className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border ${
              anyStale
                ? "text-amber-500 border-amber-500/30 bg-amber-500/10"
                : "text-green-500 border-green-500/30 bg-green-500/10"
            }`}>
              {anyStale ? <AlertCircle className="h-3.5 w-3.5" /> : <CheckCircle className="h-3.5 w-3.5" />}
              {anyStale ? "Attention needed" : "All systems operational"}
            </span>
          }
        />

        {/* Toast POS — dedicated config page */}
        <Link href="/integrations/toast" className="block group">
          <div className="rounded-lg border border-green-500/30 bg-green-500/[0.04] p-3 hover:bg-green-500/[0.07] transition-colors">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <BrandLogo slug="toasttab" domain="toasttab.com" fallback={<Store className="h-5 w-5 text-primary" />} />
                <div>
                  <h3 className="font-semibold text-sm">Toast POS</h3>
                  <p className="text-xs text-muted-foreground">Sales, orders, labor, and menu data</p>
                </div>
              </div>
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-border bg-card rounded-md font-medium group-hover:bg-muted/50 transition-colors shrink-0">
                Configure
                <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </div>
          </div>
        </Link>

        {gmailConnected && gmailEl}

        {outlookConnected && outlookEl}

        <PipeboardCard />
      </section>

      {/* ── Not connected ── */}
      <section className="rounded-xl border border-border p-4 space-y-4">
        <SectionHeader
          dot="bg-muted-foreground/50"
          title="Not connected"
          count={notConnectedCount}
          subtitle="Connect these to pull in more of your data."
        />

        {!gmailConnected && gmailEl}

        {!outlookConnected && outlookEl}

        <PushOpsCard />
      </section>

      {/* ── Coming soon ── */}
      <section className="rounded-xl border border-border p-4 space-y-4">
        <SectionHeader
          dot="bg-muted-foreground/50"
          title="Coming soon"
          count={COMING_SOON.length}
          subtitle="These integrations are on our roadmap."
        />
        <div className="space-y-2">
          {COMING_SOON.map((item) => (
            <ComingSoonRow
              key={item.title}
              title={item.title}
              description={item.description}
              slug={item.slug}
              domain={item.domain}
              fallbackIcon={<Clock className="h-5 w-5 text-muted-foreground" />}
            />
          ))}
        </div>
      </section>

      {/* ── Security footer ── */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <ShieldCheck className="h-4 w-4 shrink-0" />
        Your data is secure. We never delete or modify your original files.
      </div>
    </div>
  );
}
