"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { format } from "date-fns";
import { CheckCircle, RefreshCw, Unplug, Plug, AlertCircle, ArrowRight, Upload, Users } from "lucide-react";
import {
  useGmailStatus, useGmailAuthUrl, useGmailSync, useGmailDisconnect,
  useOutlookStatus, useOutlookAuthUrl, useOutlookSync, useOutlookDisconnect,
} from "@/hooks/use-email-integrations";
import { useImportPushOpsCsv } from "@/hooks/use-pushops-integration";
import { PipeboardIntegration } from "@/components/pipeboard-integration";
import { useLocations } from "@/hooks/use-locations";
import type { EmailSyncConfig } from "@/types/email-sync";

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
    <div className="border border-border rounded-lg p-6 bg-card space-y-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center">
            <Users className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h3 className="font-semibold">PushOperations Payroll</h3>
            <p className="text-xs text-muted-foreground">
              Upload a payroll CSV — or a screenshot/PDF — to import labor cost into your P&amp;L
            </p>
          </div>
        </div>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors"
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

      <p className="text-xs text-muted-foreground">
        Export the Payroll Summary report as CSV if your tier allows it. No CSV? Upload
        a clear screenshot or PDF instead — it&apos;s read via OCR. Re-importing the same
        file is safe — duplicates are skipped.
      </p>

      {data && (
        <div className="border-t border-border pt-4 text-sm space-y-1">
          <div className="flex items-center gap-2 text-green-400">
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
        <div className="border-t border-border pt-4 flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {errMsg}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Integration card
// ---------------------------------------------------------------------------

interface IntegrationCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  accounts: EmailSyncConfig[];
  isLoading: boolean;
  onConnect: () => void;
  onSync: (id: string) => void;
  onDisconnect: (id: string) => void;
  connecting: boolean;
  syncing: boolean;
  disconnecting: boolean;
}

function IntegrationCard({
  title, description, icon, accounts, isLoading,
  onConnect, onSync, onDisconnect,
  connecting, syncing, disconnecting,
}: IntegrationCardProps) {
  const connected = accounts.filter((a) => a.is_active);

  return (
    <div className="border border-border rounded-lg p-6 bg-card space-y-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center text-xl">
            {icon}
          </div>
          <div>
            <h3 className="font-semibold">{title}</h3>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
        </div>
        <button
          onClick={onConnect}
          disabled={connecting}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <Plug className="h-3.5 w-3.5" />
          {connecting ? "Connecting…" : "Connect"}
        </button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {connected.length > 0 && (
        <div className="space-y-2 border-t border-border pt-4">
          {connected.map((account) => (
            <div key={account.id} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-400 shrink-0" />
                <div>
                  <p className="font-medium">{account.email_address ?? "Connected"}</p>
                  <p className="text-xs text-muted-foreground">
                    Last sync: {account.last_synced_at
                      ? format(new Date(account.last_synced_at), "MMM d, HH:mm")
                      : "Never"}
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => onSync(account.id)}
                  disabled={syncing}
                  className="flex items-center gap-1 px-2 py-1 text-xs border border-border rounded-md hover:bg-muted/50 disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={`h-3 w-3 ${syncing ? "animate-spin" : ""}`} />
                  Sync
                </button>
                <button
                  onClick={() => onDisconnect(account.id)}
                  disabled={disconnecting}
                  className="flex items-center gap-1 px-2 py-1 text-xs border border-destructive text-destructive rounded hover:bg-destructive/10 disabled:opacity-50"
                >
                  <Unplug className="h-3 w-3" />
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function IntegrationsPage() {
  const params = useSearchParams();
  const connected = params.get("connected");
  const error = params.get("error");

  const { data: gmailAccounts = [], isLoading: gmailLoading } = useGmailStatus();
  const { data: outlookAccounts = [], isLoading: outlookLoading } = useOutlookStatus();
  const { mutate: connectGmail, isPending: connectingGmail } = useGmailAuthUrl();
  const { mutate: syncGmail, isPending: syncingGmail } = useGmailSync();
  const { mutate: disconnectGmail, isPending: disconnectingGmail } = useGmailDisconnect();

  const { mutate: connectOutlook, isPending: connectingOutlook } = useOutlookAuthUrl();
  const { mutate: syncOutlook, isPending: syncingOutlook } = useOutlookSync();
  const { mutate: disconnectOutlook, isPending: disconnectingOutlook } = useOutlookDisconnect();

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Integrations</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Connect Toast POS, email, and cloud storage to sync sales data and import financial documents.
        </p>
      </div>

      {connected && (
        <div className="flex items-center gap-2 text-sm text-green-400 bg-green-500/10 border border-green-500/20 rounded-md px-4 py-2">
          <CheckCircle className="h-4 w-4 shrink-0" />
          Successfully connected {connected === "gmail" ? "Gmail" : "Outlook"}.
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/5 border border-destructive/20 rounded-md px-4 py-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Connection failed. Please try again.
        </div>
      )}

      <div className="space-y-4">
        {/* Toast POS — dedicated page */}
        <Link href="/integrations/toast" className="block group">
          <div className="border border-border rounded-lg p-6 bg-card hover:border-primary/50 hover:bg-primary/5 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center text-xl">
                  🍞
                </div>
                <div>
                  <h3 className="font-semibold">Toast POS</h3>
                  <p className="text-xs text-muted-foreground">
                    Sync sales, orders, labor, and menu data from Toast
                  </p>
                </div>
              </div>
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md font-semibold group-hover:bg-primary/90 transition-colors">
                Configure
                <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </div>
          </div>
        </Link>

        <IntegrationCard
          title="Gmail"
          description="Import invoices and receipts from Gmail attachments"
          icon="✉️"
          accounts={gmailAccounts}
          isLoading={gmailLoading}
          onConnect={() => connectGmail()}
          onSync={syncGmail}
          onDisconnect={disconnectGmail}
          connecting={connectingGmail}
          syncing={syncingGmail}
          disconnecting={disconnectingGmail}
        />

        <IntegrationCard
          title="Outlook / Microsoft 365"
          description="Import invoices and receipts from Outlook attachments"
          icon="📧"
          accounts={outlookAccounts}
          isLoading={outlookLoading}
          onConnect={() => connectOutlook()}
          onSync={syncOutlook}
          onDisconnect={disconnectOutlook}
          connecting={connectingOutlook}
          syncing={syncingOutlook}
          disconnecting={disconnectingOutlook}
        />

        <PushOpsCard />

        {/* Google Ads via Pipeboard — connect, sync, job history */}
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center text-xl">📣</div>
            <div>
              <h3 className="font-semibold">Google Ads (Pipeboard)</h3>
              <p className="text-xs text-muted-foreground">
                Connect Pipeboard to sync Google Ads spend & performance into your P&amp;L marketing line
              </p>
            </div>
          </div>
          <PipeboardIntegration />
        </div>

      </div>
    </div>
  );
}
