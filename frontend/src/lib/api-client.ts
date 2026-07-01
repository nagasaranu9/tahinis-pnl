import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/lib/auth-store";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// Attach access token
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auto-refresh on 401. Concurrent 401s queue behind the in-flight refresh
// instead of failing outright, since a burst of parallel requests all hit
// 401 together when the access token expires.
let refreshPromise: Promise<string> | null = null;

async function doRefresh(): Promise<string> {
  const refreshToken = useAuthStore.getState().refreshToken;
  if (!refreshToken) throw new Error("No refresh token");
  const { data } = await axios.post(`${process.env.NEXT_PUBLIC_API_URL ?? ""}/api/v1/auth/refresh`, {
    refresh_token: refreshToken,
  });
  const { access_token, refresh_token } = data.data;
  useAuthStore.getState().setTokens(access_token, refresh_token);
  return access_token;
}

apiClient.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = doRefresh().finally(() => {
            refreshPromise = null;
          });
        }
        const access_token = await refreshPromise;
        original.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(original);
      } catch {
        useAuthStore.getState().clearTokens();
        window.location.href = "/login";
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  }
);
