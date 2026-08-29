# Evaluation Evidence — Orbit

Generated on `2026-08-28` from the current `hau` evaluation workspace and the independently deployed
backend, user and admin revisions listed in `CODEBASE_EVALUATION_2026-08-28.md`.

Missing evidence is never converted into a pass. `SKIP` is excluded by scope; `PENDING` has insufficient
evidence; `FAIL` was executed and did not meet its gate.

## Current evidence summary

| Evidence | Result | Status | Artifact |
|---|---:|---|---|
| Automated backend tests | 410/410 passed | PASS | `results/test-results.junit.xml` |
| Source coverage | 66.71% | PASS | `results/coverage-latest.json` |
| PostgreSQL memory harness | 9/9 passed | PASS | `results/memory-harness-postgres-latest.json` |
| Formal Agent acceptance | 5/17 passed | FAIL | `results/agent_acceptance_latest.json` |
| Chat staging | 10/10 success; total P95 5,242 ms | FAIL | `results/latency-chat-staging-latest.json` |
| Browser user/admin | login, chat and 14 routes rendered | PASS functional | `results/browser-e2e-staging-latest.json` |
| Staging task/reminder | CRUD passed; reminder reached `fired` | PASS | `results/realtime-load-staging-latest.json` |
| Staging WebSocket | handshake HTTP 403 | FAIL | `results/realtime-load-staging-latest.json` |
| API load | 87/100 HTTP 2xx; 13 HTTP 429 | FAIL | `results/realtime-load-staging-latest.json` |
| Authenticated accessibility | user 14/admin 11 serious-or-critical route findings | FAIL | `results/browser-e2e-staging-latest.json` |
| Lighthouse/Web Vitals | both LCP values above 2,500 ms | FAIL | `results/lighthouse-staging-latest.json` |
| Real Google OAuth/Calendar | excluded by user | SKIP | none |
| Real participant feedback | 0 participant | PENDING | `results/user-feedback-latest.json` |

## Important interpretation

- `/api/v1/chat` is non-streaming. Its measured TTFB is not true token-first latency.
- Render runtime configuration reports `openai/gpt-4.1-mini`, but the usage dashboard recorded no token or
  request delta after ten successful chat calls. Exact cost/run is therefore unavailable, not zero.
- The PostgreSQL memory run bypassed the repository SQLite fixture and created/dropped schema only in a
  disposable local PostgreSQL database.
- Backend, user and admin are not deployed from one commit. Functional E2E applies to the current mixed
  deployment, not to a synchronized release artifact.
- INP requires real-user monitoring or a controlled interaction benchmark and was not inferred from TBT.

## Reproduction

Detailed environment setup, safety constraints and exact commands are in
[`CODEBASE_EVALUATION_2026-08-28.md`](CODEBASE_EVALUATION_2026-08-28.md). Requirement mapping is in
[`TRACEABILITY_MATRIX.md`](TRACEABILITY_MATRIX.md).
