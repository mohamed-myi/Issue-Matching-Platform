import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.redis import get_redis

logger = logging.getLogger(__name__)

REC_CONTEXT_PREFIX = "recctx:"
RECO_EVENTS_QUEUE_KEY = "recoevents:queue"
RECO_EVENTS_PROCESSING_QUEUE_KEY = "recoevents:processing"
RECO_EVENTS_DEDUPE_PREFIX = "recoevents:dedupe:"

REC_CONTEXT_TTL_SECONDS_DEFAULT = 60 * 60 * 24
RECO_EVENTS_DEDUPE_TTL_SECONDS_DEFAULT = 60 * 60 * 24


@dataclass(frozen=True)
class RecommendationBatchContext:
    recommendation_batch_id: UUID
    issue_node_ids: list[str]
    page: int
    page_size: int
    is_personalized: bool
    served_at: datetime


@dataclass(frozen=True)
class RecommendationEvent:
    event_id: UUID
    recommendation_batch_id: UUID
    event_type: str
    issue_node_id: str
    position: int
    surface: str
    created_at: datetime
    metadata: dict[str, Any] | None = None


def generate_recommendation_batch_id() -> UUID:
    return uuid4()


def _context_key(batch_id: UUID) -> str:
    return f"{REC_CONTEXT_PREFIX}{batch_id}"


async def store_recommendation_batch_context(
    *,
    recommendation_batch_id: UUID,
    issue_node_ids: list[str],
    page: int,
    page_size: int,
    is_personalized: bool,
    served_at: datetime,
    ttl_seconds: int = REC_CONTEXT_TTL_SECONDS_DEFAULT,
) -> bool:
    redis = await get_redis()
    if redis is None:
        return False

    payload = {
        "issue_node_ids": issue_node_ids,
        "page": int(page),
        "page_size": int(page_size),
        "is_personalized": bool(is_personalized),
        "served_at": served_at.isoformat(),
    }

    try:
        await redis.setex(_context_key(recommendation_batch_id), ttl_seconds, json.dumps(payload))
        return True
    except Exception as e:
        logger.warning(f"Recommendation batch context write error: {e}")
        return False


async def get_recommendation_batch_context(
    recommendation_batch_id: UUID,
) -> RecommendationBatchContext | None:
    redis = await get_redis()
    if redis is None:
        return None

    try:
        raw = await redis.get(_context_key(recommendation_batch_id))
        if not raw:
            return None
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None

        issue_node_ids = parsed.get("issue_node_ids")
        page = parsed.get("page")
        page_size = parsed.get("page_size")
        is_personalized = parsed.get("is_personalized")
        served_at_raw = parsed.get("served_at")

        if not isinstance(issue_node_ids, list) or not all(isinstance(x, str) for x in issue_node_ids):
            return None
        if not isinstance(page, int) or page < 1:
            return None
        if not isinstance(page_size, int) or page_size < 1:
            return None
        if not isinstance(is_personalized, bool):
            return None
        if not isinstance(served_at_raw, str):
            return None

        served_at = datetime.fromisoformat(served_at_raw)
        if served_at.tzinfo is None:
            served_at = served_at.replace(tzinfo=UTC)

        return RecommendationBatchContext(
            recommendation_batch_id=recommendation_batch_id,
            issue_node_ids=issue_node_ids,
            page=page,
            page_size=page_size,
            is_personalized=is_personalized,
            served_at=served_at,
        )
    except Exception as e:
        logger.warning(f"Recommendation batch context read error: {e}")
        return None


def validate_event_against_context(
    *,
    context: RecommendationBatchContext,
    issue_node_id: str,
    position: int,
) -> bool:
    if position < 1:
        return False
    idx = position - 1
    if idx >= len(context.issue_node_ids):
        return False
    return context.issue_node_ids[idx] == issue_node_id


async def enqueue_recommendation_events(
    *,
    user_id: UUID,
    context: RecommendationBatchContext,
    events: list[RecommendationEvent],
    dedupe_ttl_seconds: int = RECO_EVENTS_DEDUPE_TTL_SECONDS_DEFAULT,
) -> tuple[int, int]:
    redis = await get_redis()
    if redis is None:
        raise RuntimeError("Redis unavailable")

    queued = 0
    deduped = 0

    for ev in events:
        if not validate_event_against_context(
            context=context,
            issue_node_id=ev.issue_node_id,
            position=ev.position,
        ):
            raise ValueError("Invalid event for batch context")

        dedupe_key = f"{RECO_EVENTS_DEDUPE_PREFIX}{ev.event_id}"

        try:
            is_new = await redis.set(dedupe_key, "1", ex=dedupe_ttl_seconds, nx=True)
        except TypeError:
            is_new = await redis.set(dedupe_key, "1")
            if is_new:
                await redis.expire(dedupe_key, dedupe_ttl_seconds)

        if not is_new:
            deduped += 1
            continue

        payload = {
            "event_id": str(ev.event_id),
            "user_id": str(user_id),
            "recommendation_batch_id": str(ev.recommendation_batch_id),
            "event_type": ev.event_type,
            "issue_node_id": ev.issue_node_id,
            "position": int(ev.position),
            "surface": ev.surface,
            "is_personalized": bool(context.is_personalized),
            "created_at": ev.created_at.isoformat(),
            "metadata": ev.metadata,
        }
        await redis.rpush(RECO_EVENTS_QUEUE_KEY, json.dumps(payload))
        queued += 1

    return queued, deduped


async def flush_recommendation_event_queue_once(
    *,
    db: AsyncSession,
    batch_size: int = 1000,
) -> dict[str, int]:
    redis = await get_redis()
    if redis is None:
        raise RuntimeError("Redis unavailable")

    items = await _move_batch_to_processing(redis, batch_size)
    if not items:
        return {"popped": 0, "inserted": 0}

    parsed: list[dict[str, Any]] = []
    for raw in items:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                parsed.append(obj)
        except Exception:
            continue

    if not parsed:
        await _ack_processing_items(redis, items)
        return {"popped": len(items), "inserted": 0}

    insert_sql = text("""
        INSERT INTO analytics.recommendation_events
        (event_id, user_id, recommendation_batch_id, event_type, issue_node_id, position, surface, is_personalized, created_at, metadata)
        VALUES
        (:event_id, :user_id, :recommendation_batch_id, :event_type, :issue_node_id, :position, :surface, :is_personalized, :created_at, CAST(:metadata AS jsonb))
        ON CONFLICT DO NOTHING
    """)

    params: list[dict[str, Any]] = []
    for obj in parsed:
        metadata = obj.get("metadata")
        params.append(
            {
                "event_id": obj.get("event_id"),
                "user_id": obj.get("user_id"),
                "recommendation_batch_id": obj.get("recommendation_batch_id"),
                "event_type": obj.get("event_type"),
                "issue_node_id": obj.get("issue_node_id"),
                "position": obj.get("position"),
                "surface": obj.get("surface"),
                "is_personalized": obj.get("is_personalized"),
                "created_at": obj.get("created_at"),
                "metadata": json.dumps(metadata) if metadata is not None else None,
            }
        )

    try:
        result = await db.execute(insert_sql, params)
        await db.commit()
    except Exception:
        rollback = getattr(db, "rollback", None)
        if callable(rollback):
            await rollback()
        await _requeue_processing_items(redis, items)
        raise

    inserted = result.rowcount or 0
    await _ack_processing_items(redis, items)
    return {"popped": len(items), "inserted": inserted}


async def _move_batch_to_processing(redis, batch_size: int) -> list[str]:
    items: list[str] = []

    for _ in range(batch_size):
        raw = None
        if hasattr(redis, "lmove"):
            try:
                raw = await redis.lmove(
                    RECO_EVENTS_QUEUE_KEY,
                    RECO_EVENTS_PROCESSING_QUEUE_KEY,
                    "LEFT",
                    "RIGHT",
                )
            except TypeError:
                raw = await redis.lmove(RECO_EVENTS_QUEUE_KEY, RECO_EVENTS_PROCESSING_QUEUE_KEY)
        elif hasattr(redis, "rpoplpush"):
            raw = await redis.rpoplpush(RECO_EVENTS_QUEUE_KEY, RECO_EVENTS_PROCESSING_QUEUE_KEY)
        else:
            # Last-resort compatibility path for simple test doubles.
            raw = await redis.lpop(RECO_EVENTS_QUEUE_KEY)
            if raw is not None:
                await redis.rpush(RECO_EVENTS_PROCESSING_QUEUE_KEY, raw)

        if raw is None:
            break
        items.append(raw)

    return items


async def _ack_processing_items(redis, items: list[str]) -> None:
    if not items:
        return
    for raw in items:
        await redis.lrem(RECO_EVENTS_PROCESSING_QUEUE_KEY, 1, raw)


async def _requeue_processing_items(redis, items: list[str]) -> None:
    if not items:
        return
    # Restore original order by pushing back in reverse.
    for raw in reversed(items):
        await redis.lpush(RECO_EVENTS_QUEUE_KEY, raw)
        await redis.lrem(RECO_EVENTS_PROCESSING_QUEUE_KEY, 1, raw)


__all__ = [
    "RecommendationBatchContext",
    "RecommendationEvent",
    "generate_recommendation_batch_id",
    "store_recommendation_batch_context",
    "get_recommendation_batch_context",
    "enqueue_recommendation_events",
    "flush_recommendation_event_queue_once",
    "validate_event_against_context",
    "REC_CONTEXT_PREFIX",
    "RECO_EVENTS_QUEUE_KEY",
    "RECO_EVENTS_PROCESSING_QUEUE_KEY",
]
