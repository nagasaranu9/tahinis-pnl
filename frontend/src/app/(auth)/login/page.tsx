"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { apiClient } from "@/lib/api-client";
import type { JWTPayload, TokenResponse } from "@/types/auth";

export default function LoginPage() {
  const router = useRouter();
  const { setTokens } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [storeId, setStoreId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { data } = await apiClient.post<{ data: TokenResponse }>(
        "/api/v1/auth/login",
        { email, password, store_id: storeId }
      );
      setTokens(data.data.access_token, data.data.refresh_token);
      const payload = JSON.parse(
        atob(data.data.access_token.split(".")[1])
      ) as JWTPayload;
      router.push(payload.location_id ? "/dashboard" : "/locations");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed. Check credentials.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

        .login-page {
          font-family: 'IBM Plex Sans', system-ui, sans-serif;
          min-height: 100dvh;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          background: #1e2d6b;
          background-image:
            radial-gradient(ellipse 80% 50% at 50% 0%, rgba(40,60,140,0.6) 0%, transparent 70%),
            radial-gradient(ellipse 60% 40% at 50% 100%, rgba(15,25,80,0.5) 0%, transparent 70%);
          padding: 2rem 1.5rem;
        }

        .logo-flame {
          /* no animation — clean static logo */
        }

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        .anim { animation: fadeIn 0.55s ease both; }
        .d1 { animation-delay: 0.1s; }
        .d2 { animation-delay: 0.2s; }
        .d3 { animation-delay: 0.28s; }
        .d4 { animation-delay: 0.36s; }
        .d5 { animation-delay: 0.44s; }
        .d6 { animation-delay: 0.52s; }

        @media (prefers-reduced-motion: reduce) {
          .anim { animation: none; }
        }

        .subtitle {
          letter-spacing: 0.25em;
          text-transform: uppercase;
          font-size: 11px;
          font-weight: 400;
          color: rgba(255,255,255,0.45);
        }

        .divider {
          width: 40px;
          height: 1px;
          background: rgba(255,255,255,0.15);
          margin: 0 auto;
        }

        .field-label {
          display: block;
          font-size: 10px;
          font-weight: 500;
          letter-spacing: 0.2em;
          text-transform: uppercase;
          color: rgba(255,255,255,0.4);
          margin-bottom: 8px;
        }

        .field-input {
          width: 100%;
          padding: 12px 16px;
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.12);
          border-radius: 10px;
          color: #fff;
          font-size: 14px;
          font-family: inherit;
          outline: none;
          transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
          box-sizing: border-box;
        }
        .field-input::placeholder { color: rgba(255,255,255,0.2); }
        .field-input:hover { border-color: rgba(255,255,255,0.22); }
        .field-input:focus {
          border-color: rgba(212,43,43,0.6);
          background: rgba(255,255,255,0.09);
          box-shadow: 0 0 0 3px rgba(212,43,43,0.15);
        }

        .signin-btn {
          width: 100%;
          padding: 13px 20px;
          background: #d42b2b;
          color: #fff;
          font-size: 13px;
          font-weight: 600;
          font-family: inherit;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          border: none;
          border-radius: 10px;
          cursor: pointer;
          transition: background 0.15s, box-shadow 0.15s, transform 0.1s;
        }
        .signin-btn:hover:not(:disabled) {
          background: #b82424;
          box-shadow: 0 6px 24px rgba(212,43,43,0.4);
        }
        .signin-btn:active:not(:disabled) { transform: scale(0.99); }
        .signin-btn:disabled { opacity: 0.45; cursor: not-allowed; }
        .signin-btn:focus-visible { outline: 2px solid rgba(255,255,255,0.5); outline-offset: 3px; }

        .error-box {
          background: rgba(212,43,43,0.15);
          border: 1px solid rgba(212,43,43,0.3);
          border-radius: 8px;
          padding: 10px 14px;
          font-size: 13px;
          color: #fca5a5;
        }
      `}</style>

      <div className="login-page">
        <div style={{ width: "100%", maxWidth: 360 }}>

          {/* Logo */}
          <div className="anim d1" style={{ textAlign: "center", marginBottom: "12px" }}>
            <Image
              src="/tahinis-logo.png"
              alt="Tahini's Mediterranean Fusion"
              width={220}
              height={72}
              className="logo-flame"
              style={{ objectFit: "contain", display: "inline-block" }}
              priority
            />
          </div>

          {/* Subtitle */}
          <div className="anim d2" style={{ textAlign: "center", marginBottom: "32px" }}>
            <p className="subtitle">Operations Dashboard</p>
          </div>

          {/* Divider */}
          <div className="anim d2 divider" style={{ marginBottom: "32px" }} />

          {/* Form */}
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "18px" }}>

            <div className="anim d3">
              <label htmlFor="storeId" className="field-label">Store ID</label>
              <input
                id="storeId"
                type="text"
                value={storeId}
                onChange={(e) => setStoreId(e.target.value.replace(/\D/g, "").slice(0, 5))}
                placeholder="e.g. 10042"
                required
                maxLength={5}
                inputMode="numeric"
                className="field-input"
              />
            </div>

            <div className="anim d4">
              <label htmlFor="email" className="field-label">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@restaurant.com"
                required
                className="field-input"
              />
            </div>

            <div className="anim d5">
              <label htmlFor="password" className="field-label">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="field-input"
              />
            </div>

            {error && (
              <div className="error-box" role="alert">{error}</div>
            )}

            <div className="anim d6">
              <button type="submit" disabled={loading} className="signin-btn">
                {loading ? "Signing in…" : "Sign in"}
              </button>
            </div>

          </form>

          {/* Footer */}
          <p
            className="anim d6"
            style={{
              textAlign: "center",
              marginTop: "28px",
              fontSize: "11px",
              color: "rgba(255,255,255,0.18)",
              letterSpacing: "0.05em",
            }}
          >
            Tahini&apos;s Mediterranean Fusion &copy; {new Date().getFullYear()}
          </p>
        </div>
      </div>
    </>
  );
}
