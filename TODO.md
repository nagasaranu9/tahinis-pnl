# TODO

## Email — Path B: send invites to ANY recipient (production)

Current state (Path A): Resend works but in **sandbox mode** — only delivers to the
Resend account owner's email (`naga.saranu9@gmail.com`). Sender is the shared
`onboarding@resend.dev`. Inviting arbitrary owners (e.g. `tahinis175@gmail.com`)
returns `403 validation_error` and the UI falls back to a copyable invite link.

To send to any recipient:
1. resend.com/domains → Add Domain (a domain you own, e.g. `tahinis.app`).
2. Add the SPF/DKIM DNS records Resend shows, at your registrar.
3. Wait for Resend to mark the domain Verified.
4. Railway → set `SMTP_FROM_EMAIL=invites@<verified-domain>`.
5. Redeploy. Invites now deliver to anyone.

No code change required — only Resend domain verification + the `SMTP_FROM_EMAIL` env var.

## Frontend — Google address autocomplete on Railway/Vercel

Address search ("search Google Maps to autofill") only renders when
`NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is set in Vercel. Manual address entry already works.
To enable search:
1. Google Cloud → enable **Places API (New)** + **Maps JavaScript API**.
2. Create an API key, restrict to the Vercel domain.
3. Vercel → set `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=...` → redeploy (NEXT_PUBLIC_* bakes at build).

## Backend — Gmail OAuth env (Railway)

Gmail "Connect" gives Google `Error 400: invalid_request — Missing required parameter:
client_id` because `GOOGLE_OAUTH_CLIENT_ID` is empty on Railway. To enable:
1. Google Cloud → OAuth consent screen + create OAuth Client (Web application).
2. Authorized redirect URI = `<API_BASE_URL>/api/v1/integrations/gmail/callback`
   (API_BASE_URL must be the Railway backend URL, not localhost).
3. Railway → set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and
   `API_BASE_URL=https://tahinis-pnl-production.up.railway.app`.
4. Add scopes: `gmail.readonly`. Add test users while app unverified.
Until set, the endpoint now returns a clean error instead of a broken Google page.
