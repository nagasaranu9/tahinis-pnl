import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { JWTPayload, Role } from "@/types/auth";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  setTokens: (accessToken: string, refreshToken: string) => void;
  clearTokens: () => void;
  getRole: () => Role | null;
  getTenantId: () => string | null;
  getUserId: () => string | null;
  getLocationId: () => string | null;
}

function parseJwt(token: string): JWTPayload | null {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload)) as JWTPayload;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,

      setTokens: (accessToken, refreshToken) =>
        set({ accessToken, refreshToken }),

      clearTokens: () => set({ accessToken: null, refreshToken: null }),

      getRole: () => {
        const token = get().accessToken;
        if (!token) return null;
        return parseJwt(token)?.role ?? null;
      },

      getTenantId: () => {
        const token = get().accessToken;
        if (!token) return null;
        return parseJwt(token)?.tenant_id ?? null;
      },

      getUserId: () => {
        const token = get().accessToken;
        if (!token) return null;
        return parseJwt(token)?.sub ?? null;
      },

      getLocationId: () => {
        const token = get().accessToken;
        if (!token) return null;
        return parseJwt(token)?.location_id ?? null;
      },
    }),
    { name: "tahinis-auth" }
  )
);
