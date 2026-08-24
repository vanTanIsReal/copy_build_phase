from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import session as db_session
from src.db.models import Memory, MemoryEpisode

_WORD_RE = re.compile(r"[a-z0-9_]+")
_FORBIDDEN_MEMORY_RE = re.compile(
    r"\b(password|mat\s*khau|passcode|otp|api[_ -]?key|secret|access[_ -]?token|"
    r"refresh[_ -]?token|private[_ -]?key|cvv|so\s*the|cccd|cmnd|ho\s*chieu|"
    r"social\s*security|bank\s*account|tai\s*khoan\s*ngan\s*hang|sinh\s*trac|biometric|"
    r"ton\s*giao|religion|xu\s*huong\s*tinh\s*duc|sexual\s*orientation|"
    r"dang\s*phai|political\s*affiliation|chan\s*doan|diagnos(?:is|ed))\b"
)


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(_normalize_text(text)))


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def content_hash(title: str, detail: str) -> str:
    """Dedup key for a memory note - same normalized title+detail hashes the same, regardless of
    whether it arrived via the manual /memory page or an episode's consolidation candidate."""
    canonical = " ".join(f"{title}\n{detail}".lower().split())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_forbidden_sensitive_memory(text: str) -> bool:
    """Hard block on categories no consolidation candidate may ever write as a durable Memory,
    even if the LLM proposed it and guardrail_service's own check passed - credentials and a few
    protected personal-data categories never belong in long-term memory at all."""
    return bool(_FORBIDDEN_MEMORY_RE.search(_normalize_text(text)))


async def embed_text(text: str) -> tuple[list[float] | None, str | None]:
    """Best-effort embeddings for semantic recall. Returns (None, None) - never raises - when no
    embedding-capable provider key is configured or the call fails; retrieve_memories/
    retrieve_episodes fall back to lexical + recency + importance ranking in that case."""
    from src.config import get_settings

    settings = get_settings()
    if settings.app_env == "test":
        return None, None
    try:
        if settings.google_api_key:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            model = "models/gemini-embedding-001"
            vector = await GoogleGenerativeAIEmbeddings(model=model, google_api_key=settings.google_api_key).aembed_query(
                text
            )
            return list(vector), model
        if settings.openai_api_key:
            from langchain_openai import OpenAIEmbeddings

            model = "text-embedding-3-small"
            vector = await OpenAIEmbeddings(model=model, api_key=settings.openai_api_key).aembed_query(text)
            return list(vector), model
    except Exception:  # noqa: BLE001 - embedding is an enhancement; CRUD/chat must not fail when provider is down
        return None, None
    return None, None


def _cosine(left: list | None, right: list | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    norm = math.sqrt(sum(float(a) ** 2 for a in left)) * math.sqrt(sum(float(b) ** 2 for b in right))
    return dot / norm if norm else 0.0


def _relevance(
    query: str, text: str, vector: list | None, query_vector: list | None, importance: float, created_at: datetime
) -> float:
    query_words, text_words = _words(query), _words(text)
    lexical = len(query_words & text_words) / max(1, len(query_words))
    semantic = max(0.0, _cosine(vector, query_vector))
    age_days = max(0.0, (datetime.now(UTC) - created_at).total_seconds() / 86_400)
    recency = 1 / (1 + age_days / 30)
    return 0.45 * semantic + 0.30 * lexical + 0.15 * float(importance) + 0.10 * recency


async def list_memories_for_owner(
    owner_id: str | None, *, include_pending: bool = True, limit: int = 100
) -> list[Memory]:
    """All memory notes for a user, newest-updated first. Shared by memory_routes.py's
    `GET /memories` and the agent's `list_memories` tool (src/agents/tools/memory_tool.py).
    include_pending=True (the default, matching both existing callers) also returns
    status="pending_review" candidates written by memory_maintenance_service.py's consolidation -
    they're not hidden from the user, just not yet explicitly confirmed (Memory.user_confirmed)."""
    statuses = ["active", "pending_review"] if include_pending else ["active"]
    async with db_session.async_session_maker() as db:
        memories = (
            await db.execute(
                select(Memory)
                .where(
                    Memory.owner_id == owner_id,
                    Memory.status.in_(statuses),
                    or_(Memory.expires_at.is_(None), Memory.expires_at > datetime.now(UTC)),
                )
                .order_by(Memory.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    return list(memories)


async def supersede_exact_conflicts(db: AsyncSession, incoming: Memory) -> int:
    """Retire an explicitly replaced durable note without deleting its provenance.

    Two notes conflict only when the same user writes the same category/type/title again - an
    exact identity key, never an LLM inference. Callers invoke this only after an explicit user
    write or approval, so an automatic heartbeat candidate can never overwrite user memory.
    """
    await db.flush()
    conflicts = (
        await db.execute(
            select(Memory).where(
                Memory.owner_id == incoming.owner_id,
                Memory.category == incoming.category,
                Memory.memory_type == incoming.memory_type,
                Memory.title == incoming.title,
                Memory.id != incoming.id,
                Memory.status == "active",
            )
        )
    ).scalars().all()
    for existing in conflicts:
        existing.status = "superseded"
        provenance = dict(existing.provenance or {})
        provenance.update(
            {
                "superseded_by": incoming.id,
                "superseded_at": datetime.now(UTC).isoformat(),
                "supersession_reason": "explicit_user_write",
            }
        )
        existing.provenance = provenance
    return len(conflicts)


async def retrieve_memories(owner_id: str | None, query: str, *, limit: int = 6) -> list[Memory]:
    """Query-ranked recall for context_node.py - confirmed memories only (include_pending=False),
    since an unreviewed consolidation candidate shouldn't ground the planner's answers yet."""
    if not owner_id:
        return []
    memories = await list_memories_for_owner(owner_id, include_pending=False, limit=250)
    if not memories:
        return []
    query_vector, _ = await embed_text(query) if query.strip() else (None, None)
    ranked = sorted(
        memories,
        key=lambda m: _relevance(
            query, f"{m.category} {m.title} {m.detail}", m.embedding, query_vector, m.importance, m.updated_at or m.created_at
        ),
        reverse=True,
    )[:limit]
    # Access metadata is deliberately best effort and never affects the response transaction.
    async with db_session.async_session_maker() as db:
        now = datetime.now(UTC)
        for item in ranked:
            owned = await db.get(Memory, item.id)
            if owned:
                owned.access_count += 1
                owned.last_accessed_at = now
        await db.commit()
    return ranked


async def retrieve_episodes(owner_id: str | None, query: str, *, limit: int = 4) -> list[MemoryEpisode]:
    if not owner_id:
        return []
    now = datetime.now(UTC)
    async with db_session.async_session_maker() as db:
        rows = (
            await db.execute(
                select(MemoryEpisode)
                .where(MemoryEpisode.owner_id == owner_id, or_(MemoryEpisode.expires_at.is_(None), MemoryEpisode.expires_at > now))
                .order_by(MemoryEpisode.created_at.desc())
                .limit(100)
            )
        ).scalars().all()
    query_vector, _ = await embed_text(query) if query.strip() else (None, None)
    return sorted(
        rows,
        key=lambda e: _relevance(
            query,
            f"{e.summary} {' '.join(e.decisions or [])} {' '.join(e.open_loops or [])}",
            e.embedding,
            query_vector,
            e.importance,
            e.created_at,
        ),
        reverse=True,
    )[:limit]


async def prepare_embedding(memory: Memory) -> None:
    memory.content_hash = content_hash(memory.title, memory.detail or "")
    vector, model = await embed_text(f"{memory.category}: {memory.title}\n{memory.detail}")
    memory.embedding, memory.embedding_model = vector, model
