"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";

interface StepStatus {
  profile: boolean;
  toast: boolean;
  gmail: boolean;
  google: boolean;
}

interface OnboardingStatus {
  location_id: string;
  steps: StepStatus;
  completed: boolean;
  completed_at: string | null;
}

type StepKey = keyof StepStatus;

const STEP_META: { key: StepKey; title: string; desc: string }[] = [
  { key: "profile", title: "Location profile", desc: "Address, timezone & business hours." },
  { key: "toast", title: "Toast POS", desc: "Connect sales & labor data." },
  { key: "gmail", title: "Gmail", desc: "Import invoices & receipts from email." },
  { key: "google", title: "Google", desc: "Reviews & ratings via Google Place ID." },
];

export default function OnboardingPage() {
  const router = useRouter();
  const locationId = useAuthStore((s) => s.getLocationId());
  const accessToken = useAuthStore((s) => s.accessToken);

  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);

  // Toast inline form
  const [toastForm, setToastForm] = useState({ guid: "", clientId: "", clientSecret: "" });
  const [toastBusy, setToastBusy] = useState(false);
  const [toastErr, setToastErr] = useState<string | null>(null);
  const [toastOk, setToastOk] = useState(false);
  const [gmailBusy, setGmailBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!locationId) return;
    try {
      const { data } = await apiClient.get<{ data: OnboardingStatus }>(
        `/api/v1/locations/${locationId}/onboarding`
      );
      setStatus(data.data);
    } catch {
      setLoadError("Could not load onboarding status.");
    }
  }, [locationId]);

  useEffect(() => {
    if (!accessToken) {
      router.replace("/login");
      return;
    }
    if (!locationId) {
      router.replace("/locations");
      return;
    }
    refresh();
  }, [accessToken, locationId, router, refresh]);

  async function connectToast(e: React.FormEvent) {
    e.preventDefault();
    setToastErr(null);
    setToastOk(false);
    setToastBusy(true);
    try {
      await apiClient.post(`/api/v1/integrations/toast/connect`, {
        location_id: locationId,
        client_id: toastForm.clientId,
        client_secret: toastForm.clientSecret,
        toast_restaurant_guid: toastForm.guid,
      });
      setToastForm({ guid: "", clientId: "", clientSecret: "" });
      setToastOk(true);
      await refresh();
    } catch (err: unknown) {
      setToastErr(extractError(err) ?? "Could not connect Toast. Check the credentials.");
    } finally {
      setToastBusy(false);
    }
  }

  async function connectGmail() {
    setGmailBusy(true);
    try {
      const { data } = await apiClient.get<{ data: { url: string } }>(
        `/api/v1/integrations/email/gmail/auth-url`
      );
      window.location.href = data.data.url;
    } catch {
      setGmailBusy(false);
    }
  }

  async function finish() {
    if (!locationId) return;
    setFinishing(true);
    try {
      await apiClient.post(`/api/v1/locations/${locationId}/onboarding/complete`);
      router.push("/dashboard");
    } catch {
      setFinishing(false);
    }
  }

  const steps = status?.steps;
  const doneCount = steps ? Object.values(steps).filter(Boolean).length : 0;
  const pct = Math.round((doneCount / STEP_META.length) * 100);

  return (
    <div className="min-h-screen bg-muted/20 py-10 px-4">
      <div className="mx-auto w-full max-w-2xl">
        <div className="flex items-center gap-3 mb-6">
          <Image src="/tahinis-logo.png" alt="Tahini's" width={44} height={44} className="object-contain" priority />
          <div>
            <h1 className="text-lg font-semibold text-foreground">Set up your location</h1>
            <p className="text-sm text-muted-foreground">Connect your integrations to start pulling data.</p>
          </div>
        </div>

        {/* Progress */}
        <div className="mb-6">
          <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
            <span>{doneCount} of {STEP_META.length} connected</span>
            <span>{pct}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-border overflow-hidden">
            <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>

        {loadError && <p className="text-sm text-destructive mb-4">{loadError}</p>}

        <div className="space-y-3">
          {STEP_META.map((meta) => {
            const done = steps?.[meta.key] ?? false;
            return (
              <div key={meta.key} className="bg-card border border-border rounded-lg p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <span
                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                        done ? "bg-green-600 text-white" : "bg-border text-muted-foreground"
                      }`}
                    >
                      {done ? "✓" : ""}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-foreground">{meta.title}</p>
                      <p className="text-xs text-muted-foreground">{meta.desc}</p>
                    </div>
                  </div>
                  {done ? (
                    <span className="text-xs font-medium text-green-600">Connected</span>
                  ) : (
                    <StepAction
                      stepKey={meta.key}
                      gmailBusy={gmailBusy}
                      onGmail={connectGmail}
                      onSettings={() => router.push("/settings")}
                    />
                  )}
                </div>

                {/* Inline Toast form */}
                {meta.key === "toast" && !done && (
                  <form onSubmit={connectToast} className="mt-3 space-y-2 border-t border-border pt-3">
                    <Input placeholder="Toast restaurant GUID" value={toastForm.guid}
                      onChange={(v) => setToastForm((f) => ({ ...f, guid: v }))} />
                    <Input placeholder="Client ID" value={toastForm.clientId}
                      onChange={(v) => setToastForm((f) => ({ ...f, clientId: v }))} />
                    <Input placeholder="Client secret" type="password" value={toastForm.clientSecret}
                      onChange={(v) => setToastForm((f) => ({ ...f, clientSecret: v }))} />
                    {toastErr && <p className="text-xs text-destructive">{toastErr}</p>}
                    {toastOk && (
                      <p className="text-xs font-medium text-green-600">
                        ✓ Toast connected — historical import started.
                      </p>
                    )}
                    <button type="submit" disabled={toastBusy}
                      className="text-xs font-medium bg-primary text-primary-foreground px-3 py-1.5 rounded-md hover:opacity-90 disabled:opacity-50">
                      {toastBusy ? "Connecting…" : "Connect Toast"}
                    </button>
                  </form>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-6 flex items-center justify-between">
          <button onClick={refresh} className="text-xs text-muted-foreground hover:text-foreground">
            Refresh status
          </button>
          <button onClick={finish} disabled={finishing}
            className="text-sm font-medium bg-primary text-primary-foreground px-5 py-2.5 rounded-md hover:opacity-90 disabled:opacity-50">
            {finishing ? "Finishing…" : doneCount === STEP_META.length ? "Finish setup" : "Skip & finish later"}
          </button>
        </div>
      </div>
    </div>
  );
}

function StepAction({
  stepKey, gmailBusy, onGmail, onSettings,
}: {
  stepKey: StepKey;
  gmailBusy: boolean;
  onGmail: () => void;
  onSettings: () => void;
}) {
  if (stepKey === "gmail") {
    return (
      <button onClick={onGmail} disabled={gmailBusy}
        className="text-xs font-medium border border-border px-3 py-1.5 rounded-md hover:bg-muted disabled:opacity-50">
        {gmailBusy ? "Opening…" : "Connect"}
      </button>
    );
  }
  if (stepKey === "toast") return null; // inline form below
  return (
    <button onClick={onSettings}
      className="text-xs font-medium border border-border px-3 py-1.5 rounded-md hover:bg-muted">
      Set up
    </button>
  );
}

function Input({
  value, onChange, placeholder, type = "text",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  type?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
    />
  );
}

function extractError(err: unknown): string | null {
  if (
    typeof err === "object" && err !== null && "response" in err &&
    typeof (err as { response?: unknown }).response === "object"
  ) {
    const resp = (err as { response?: { data?: { errors?: { message?: string }[] } } }).response;
    return resp?.data?.errors?.[0]?.message ?? null;
  }
  return null;
}
