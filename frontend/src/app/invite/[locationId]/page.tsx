"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import axios from "axios";

interface InviteLocation {
  name: string;
  store_id: string | null;
}

export default function AcceptInvitePage() {
  const params = useParams<{ locationId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token") ?? "";

  const [location, setLocation] = useState<InviteLocation | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";

  useEffect(() => {
    if (!token) {
      setLoadError("Missing invite token.");
      return;
    }
    axios
      .get(`${apiBase}/api/v1/locations/invite/${params.locationId}`, { params: { token } })
      .then((res) => setLocation(res.data.data))
      .catch(() => setLoadError("This invite link is invalid or has expired."));
  }, [apiBase, params.locationId, token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    if (password !== confirm) {
      setSubmitError("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(
        `${apiBase}/api/v1/locations/invite/${params.locationId}/accept`,
        { token, password }
      );
      setDone(true);
    } catch (err: unknown) {
      const msg =
        axios.isAxiosError(err) && err.response?.data?.errors?.[0]?.message
          ? err.response.data.errors[0].message
          : "Could not complete setup. The link may have expired.";
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/20 p-4">
      <div className="w-full max-w-sm bg-card border border-border rounded-lg shadow-sm p-7">
        <div className="flex justify-center mb-5">
          <Image
            src="/tahinis-logo.png"
            alt="Tahini's Mediterranean Fusion"
            width={56}
            height={56}
            className="object-contain"
            priority
          />
        </div>

        {done ? (
          <div className="text-center">
            <h1 className="text-base font-semibold text-foreground mb-2">You&apos;re all set</h1>
            <p className="text-sm text-muted-foreground mb-5">
              Your account is active. Sign in to finish setting up your location&apos;s details in
              Settings.
            </p>
            <button
              onClick={() => router.push("/login")}
              className="w-full text-sm font-medium bg-primary text-primary-foreground py-2.5 rounded-md hover:opacity-90 transition-opacity cursor-pointer"
            >
              Go to login
            </button>
          </div>
        ) : loadError ? (
          <p className="text-sm text-destructive text-center">{loadError}</p>
        ) : !location ? (
          <p className="text-sm text-muted-foreground text-center">Loading invite…</p>
        ) : (
          <form onSubmit={handleSubmit}>
            <h1 className="text-base font-semibold text-foreground mb-1">
              Set up {location.store_id ? `#${location.store_id} - ` : ""}
              {location.name}
            </h1>
            <p className="text-sm text-muted-foreground mb-5">
              Create a password to activate your owner account. You&apos;ll fill out the rest of
              your location details in Settings after signing in.
            </p>
            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Confirm password
                </label>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  minLength={8}
                  className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              {submitError && <p className="text-xs text-destructive">{submitError}</p>}
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full mt-5 text-sm font-medium bg-primary text-primary-foreground py-2.5 rounded-md hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50"
            >
              {submitting ? "Activating…" : "Activate account"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
