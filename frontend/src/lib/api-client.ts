import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/lib/auth-store";

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "",
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

// Auto-refresh on 401
let refreshing = false;
apiClient.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && !original._retry && !refreshing) {
      original._retry = true;
      refreshing = true;
      try {
        const refreshToken = useAuthStore.getState().refreshToken;
        if (!refreshToken) throw new Error("No refresh token");

        const { data } = await axios.post(`${process.env.NEXT_PUBLIC_API_URL ?? ""}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const { access_token, refresh_token } = data.data;
        useAuthStore.getState().setTokens(access_token, refresh_token);
        original.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(original);
      } catch {
        useAuthStore.getState().clearTokens();
        window.location.href = "/login";
      } finally {
        refreshing = false;
      }
    }
    return Promise.reject(error);
  }
);
