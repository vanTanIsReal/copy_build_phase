# Orbit deployment

The production shape is intentionally one backend process, one user SPA, and one admin SPA.
Do not scale the backend horizontally: WebSocket connections and APScheduler jobs are currently
process-local.

## Backend (Render)

1. Apply `render.yaml` and set every `sync: false` value in the Render dashboard.
2. Use a PostgreSQL `DATABASE_URL`; production configuration rejects SQLite.
3. Set `CORS_ORIGINS` to both exact Vercel origins, comma-separated and without `*`.
4. Add `RENDER_DEPLOY_HOOK_URL` as a GitHub secret and `RENDER_URL` as a GitHub variable.
5. Run the `Deploy backend` workflow once manually. Later main-branch deployments run only after CI succeeds.

The container runs `alembic upgrade head` before Uvicorn and exposes `/health` for rollout checks.

## Frontends (Vercel)

Create two Vercel projects from the same repository:

| Project | Root directory | Dev port |
|---|---|---:|
| Orbit User | `Frontend/user` | 5173 |
| Orbit Admin | `Frontend/admin` | 5174 |

For each project, set `VITE_API_BASE_URL=https://<backend>/api/v1`. Set
`VITE_WS_BASE_URL=wss://<backend>/api/v1/ws` for the user project. Each app's `vercel.json`
preserves client-side routes on refresh.

## Release checks

- Run `ruff check src tests` and `pytest tests -q`.
- Run `npm run build` from `Frontend`.
- Verify login, a real WebSocket exchange, one AI turn, one confirmed reminder, admin usage/audit,
  and a direct refresh of a nested route.
- Confirm repeated failed login and chat bursts return HTTP 429.

Google Calendar also needs the credentials/token strategy documented in `.env.example`; do not
deploy local secret files into the image.

## Google Calendar for real users (not just yourself)

The app code has no allowlist - any Google account can connect once OAuth is configured
correctly. What actually gates "anyone can connect" is entirely in Google Cloud Console, not code:

1. **Authorized origins/redirect URIs** - in
   [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials),
   on the *Calendar* OAuth client, add the production callback to Authorized redirect URIs:
   `https://<backend-domain>/api/v1/calendar/oauth/callback` (must match `GOOGLE_CALENDAR_REDIRECT_URI`
   exactly, HTTPS). On the separate *Sign-In* OAuth client, add the production frontend origin to
   Authorized JavaScript origins. Leftover `localhost` values here are the #1 cause of "works for
   me, fails for everyone else" - `src/config.py`'s production validator now rejects a `localhost`
   `GOOGLE_CALENDAR_REDIRECT_URI`/`FRONTEND_ORIGIN` at boot so this fails loud instead of silently.
2. **OAuth consent screen publishing status** - under *OAuth consent screen*, a new client starts
   in **Testing**, which only lets manually-added test users (max ~100) sign in; everyone else
   gets `Error 403: access_denied`. Click **Publish App** to move it to **In production**.
3. **Verification warning** - `https://www.googleapis.com/auth/calendar` (full read/write) is a
   Google *sensitive* scope. In production without completing Google's app verification, users
   still see a one-time "Google hasn't verified this app" interstitial and must click
   Advanced → "Go to <app> (unsafe)" to continue - functional, just unpolished. Removing that
   warning requires submitting for verification (needs a live Privacy Policy URL, app homepage on
   an authorized domain, and a scope-justification review) - budget days to a few weeks, and start
   it before it's urgent.
