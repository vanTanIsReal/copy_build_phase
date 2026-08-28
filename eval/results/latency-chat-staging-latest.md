# Staging Chat Latency and Cost

- Run: `2026-08-28T14:14:48.199Z`
- Target: `POST https://orbit-backend-xkgq.onrender.com/api/v1/chat`
- Runtime model: `openai/gpt-4.1-mini` (verified from Render service environment)
- Requests: **10**, sequential
- Success: **10/10**
- Streaming: **No**; TTFB is not true first-token latency.

| Metric | TTFB | Total |
|---|---:|---:|
| P50 | 1763.266 ms | 1764.217 ms |
| P95 | 5240.914 ms | 5242.076 ms |
| P99 | 7368.594 ms | 7369.926 ms |
| Max | 7900.514 ms | 7901.889 ms |

## Usage delta

- Prompt tokens: **0**
- Completion tokens: **0**
- Total tokens: **0**
- Provider requests logged: **0**
- Estimated cost: **UNAVAILABLE**, not `$0`: the staging usage endpoint recorded no delta for these 10 successful requests.
- Unpriced tokens: **0**

The configured list prices are $0.40/input and $1.60/output per 1M tokens. They cannot be applied
until the deployed backend records prompt/completion usage for the requests.
