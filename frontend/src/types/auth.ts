export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export type Role = "owner" | "manager" | "viewer";

export interface JWTPayload {
  sub: string;
  tenant_id: string;
  role: Role;
  location_id: string | null;
  exp: number;
  iat: number;
}
