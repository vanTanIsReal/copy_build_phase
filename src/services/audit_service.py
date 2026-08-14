from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AuditLog, User

# An audit entry is an activity trail, not a content log - if a caller accidentally passes actual
# message/memory text as metadata (e.g. copy-pasting a dict that still has the field in it), fail
# loudly instead of silently persisting user content into a table meant to hold none.
_SENSITIVE_METADATA_KEYS = {"content", "message", "memory", "token", "secret"}


async def record_audit_event(
    db: AsyncSession,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one entry to the Audit Log (Admin > Audit Log page). Caller is responsible for
    `db.commit()` - this only `flush()`es, so it can be called as part of the same transaction as
    the action it's recording (see admin_routes.py call sites) without an extra round trip.

    Every current call site is an admin-only endpoint (src/api/admin_routes.py, gated by
    require_admin), so actor is always a real admin user in practice - actor=None (actor_type
    "system") is supported for a future scheduler/background-job caller, not used yet."""
    metadata = metadata or {}
    if _SENSITIVE_METADATA_KEYS.intersection(metadata):
        raise ValueError("Audit metadata contains sensitive content")
    record = AuditLog(
        actor_user_id=actor.id if actor is not None else None,
        actor_type="admin" if actor is not None else "system",
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_json=metadata,
    )
    db.add(record)
    await db.flush()
    return record
