import logging
import os
import time

from gim_database.session import async_session_factory
from gim_backend.services.recommendation_event_service import (
    flush_recommendation_event_queue_once,
)


logger = logging.getLogger(__name__)


async def run_reco_flush_job() -> dict:
    max_seconds = int(os.getenv("RECO_FLUSH_MAX_SECONDS", "60"))
    batch_size = int(os.getenv("RECO_EVENTS_FLUSH_BATCH_SIZE", "1000"))

    start = time.time()
    total_popped = 0
    total_inserted = 0
    loops = 0

    async with async_session_factory() as db:
        while True:
            loops += 1
            result = await flush_recommendation_event_queue_once(
                db=db,
                batch_size=batch_size,
            )
            total_popped += result.get("popped", 0)
            total_inserted += result.get("inserted", 0)

            if result.get("popped", 0) == 0:
                break

            if (time.time() - start) >= max_seconds:
                break

    return {
        "loops": loops,
        "popped": total_popped,
        "inserted": total_inserted,
        "max_seconds": max_seconds,
        "batch_size": batch_size,
    }
