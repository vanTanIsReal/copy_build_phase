# Staging Realtime / Load Evidence

- Run: `2026-08-28T14:19:24.133Z`
- Accounts: **2**
- WebSocket connections: **0** — handshake returned HTTP 403

## Results

- WebSocket delivery: **FAIL / not measurable** because no connection was accepted.
- Task create/list/update/delete: **201/200/200/204 — PASS**
- Reminder final state: **`fired` — PASS**; push event not received because WebSocket failed.
- Calendar connection/events: **200/409**; real Google OAuth excluded by user request.
- Load: **87/100** HTTP 2xx, concurrency **5**, P50 **306.369 ms**, P95 **1,203.014 ms**.
- Status counts: `{"200":87,"429":13}`
