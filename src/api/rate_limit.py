"""Rate limiting (slowapi) - request burst/abuse protection, separate axis from
`usage_service.is_over_budget()` (which caps $ cost across the whole app per day). In-memory
storage is correct here: the app runs as a single uvicorn worker on a single Render instance
(see Dockerfile CMD - no `--workers` flag), so there's no cross-process state to share and no
need for Redis (consistent with the rest of the project - see ROADMAP.md).

Limits are applied per-route via `@limiter.limit(...)` decorators (auth endpoints, /chat) - see
ROADMAP.md for the concrete tiers and rationale. Routes with neither a decorator nor
`Depends(crud_rate_limit)` (health check, /chat/resume, /status) are never limited.

NOT using slowapi's `Limiter(default_limits=[...])` + `SlowAPIMiddleware` auto-detection for the
generic CRUD tier, even though that's slowapi's documented shortcut for "apply to everything else
without decorating each route": on the FastAPI version this project pins (see requirements.txt),
`app.include_router(...)` no longer flattens routes into `app.routes`, so `SlowAPIMiddleware`'s
route-handler lookup (which walks `app.routes` directly) can't find any route registered through
an included router and silently treats it as exempt - verified empirically, not a guess. The
`crud_rate_limit` dependency below sidesteps that by using slowapi's per-call check (the same one
`.limit(...)` uses internally) triggered through FastAPI's own `Depends()` resolution instead of
middleware route lookup, which works regardless of that internal routing change.
"""

import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from src.auth.security import decode_access_token
from src.config import get_settings

settings = get_settings()


def user_or_ip_key(request: Request) -> str:
    """Rate-limit key: the authenticated user's id when a valid Bearer token is present,
    otherwise the client IP. Per-user keying matters for authenticated routes (/chat, CRUD) so
    multiple legitimate users sharing an IP - NAT, same wifi, e.g. a group demo - don't share one
    bucket; per-IP is the only option for unauthenticated routes (login/register/google), which is
    exactly what this falls back to since they never carry a Bearer token.

    Decodes the JWT directly instead of depending on `get_current_user` - slowapi resolves the
    rate-limit key in middleware, before FastAPI's own `Depends()` chain runs for the route, and
    this is a cheap in-memory decode (no DB hit). An invalid/expired token here just falls back to
    IP-keying; `get_current_user` still runs afterwards and 401s it as usual - this function only
    ever chooses a bucket, it never authenticates anyone.

    Real client IP is already correct behind Render's proxy: the Dockerfile CMD sets
    `--proxy-headers --forwarded-allow-ips='*'` on uvicorn, which rewrites the ASGI scope's client
    from X-Forwarded-For before the request reaches Starlette - get_remote_address needs no extra
    configuration to see the real caller, not Render's edge IP.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        try:
            return f"user:{decode_access_token(token)}"
        except jwt.PyJWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=user_or_ip_key, enabled=settings.rate_limit_enabled)


@limiter.limit(settings.rate_limit_crud)
async def crud_rate_limit(request: Request) -> None:
    """Shared 'everything else' safety-net tier (see module docstring for why this is a
    dependency instead of Limiter's usual default_limits). Add `Depends(crud_rate_limit)` to a
    router's `dependencies=[...]` to cover every route in it with one line, no per-route
    decoration needed - see reminder_routes.py/memory_routes.py/etc. for the pattern.

    Do NOT add this to a router that also has its own per-route `@limiter.limit(...)` (e.g.
    auth_routes.py's /register, /login, /google): slowapi marks a request as
    "already rate-limited" the first time any check runs on it (`request.state.
    _rate_limiting_complete`), so a router-level dependency would silently swallow a more specific
    route decorator's own (different, usually stricter) limit if it ran first.
    """
    return None
