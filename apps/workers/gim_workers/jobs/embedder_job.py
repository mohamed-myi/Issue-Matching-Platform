"""
Embedder job: Process pending issues from staging table.

Reads from staging.pending_issue, generates embeddings, writes to ingestion.issue.
Designed to run as a Cloud Run Job, scheduled after the Collector.
"""

import logging
import time

from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.core.config import get_settings
from gim_backend.ingestion.persistence import StreamingPersistence
from gim_backend.ingestion.nomic_moe_embedder import NomicMoEEmbedder
from gim_backend.ingestion.staging_persistence import StagingPersistence
from gim_database.session import async_session_factory

logger = logging.getLogger(__name__)


async def run_embedder_job(embedder: NomicMoEEmbedder | None = None) -> dict:
    """
    Process pending issues from staging table.

    1. Claim batch of pending issues (atomic lock)
    2. Generate embeddings in batches
    3. Persist to ingestion.issue with survival score
    4. Mark staging records as completed

    Returns stats dict with issues_processed and issues_failed.
    """
    job_start = time.monotonic()
    settings = get_settings()
    batch_size = settings.embedder_batch_size

    logger.info(
        f"Embedder job starting with batch_size={batch_size}",
        extra={"batch_size": batch_size},
    )

    close_embedder = False
    if embedder is None:
        logger.info("Initializing NomicMoEEmbedder")
        embedder = NomicMoEEmbedder(max_workers=2)
        embedder.warmup()
        close_embedder = True

    total_processed = 0
    total_failed = 0

    try:
        while True:
            async with async_session_factory() as session:
                staging = StagingPersistence(session)
                pending_issues = await staging.claim_pending_batch(batch_size)

            if not pending_issues:
                logger.info("No pending issues to process")
                break

            logger.info(
                f"Processing batch of {len(pending_issues)} issues",
                extra={"batch_size": len(pending_issues)},
            )

            texts = [
                f"{issue['title']}\n{issue['body_text']}" for issue in pending_issues
            ]

            try:
                embeddings = await embedder.embed_documents(texts)
            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")
                async with async_session_factory() as session:
                    staging = StagingPersistence(session)
                    await staging.mark_failed([i["node_id"] for i in pending_issues])
                total_failed += len(pending_issues)
                continue

            if len(embeddings) != len(pending_issues):
                logger.error(
                    f"Embedding count mismatch: got {len(embeddings)}, expected {len(pending_issues)}"
                )
                async with async_session_factory() as session:
                    staging = StagingPersistence(session)
                    await staging.mark_failed([i["node_id"] for i in pending_issues])
                total_failed += len(pending_issues)
                continue

            succeeded_ids = []
            failed_ids = []

            async with async_session_factory() as session:
                for issue, embedding in zip(pending_issues, embeddings):
                    try:
                        await _persist_issue(session, issue, embedding)
                        succeeded_ids.append(issue["node_id"])
                    except Exception as e:
                        logger.warning(
                            f"Failed to persist issue {issue['node_id']}: {e}"
                        )
                        failed_ids.append(issue["node_id"])

                await session.commit()

            async with async_session_factory() as session:
                staging = StagingPersistence(session)
                if succeeded_ids:
                    await staging.mark_completed(succeeded_ids)
                if failed_ids:
                    await staging.mark_failed(failed_ids)

            total_processed += len(succeeded_ids)
            total_failed += len(failed_ids)

            logger.info(
                f"Batch complete: {len(succeeded_ids)} succeeded, {len(failed_ids)} failed",
                extra={
                    "batch_succeeded": len(succeeded_ids),
                    "batch_failed": len(failed_ids),
                    "total_processed": total_processed,
                },
            )

    finally:
        if close_embedder:
            embedder.close()

    staging_cleaned = 0
    try:
        async with async_session_factory() as session:
            staging = StagingPersistence(session)
            staging_cleaned = await staging.cleanup_completed(older_than_hours=24)
        if staging_cleaned > 0:
            logger.info(
                f"Staging cleanup: removed {staging_cleaned} completed rows",
                extra={"staging_cleaned": staging_cleaned},
            )
    except Exception as e:
        logger.warning(f"Staging cleanup failed (non-fatal): {e}")

    elapsed = time.monotonic() - job_start

    logger.info(
        f"Embedder job complete in {elapsed:.1f}s - {total_processed} processed, {total_failed} failed",
        extra={
            "total_processed": total_processed,
            "total_failed": total_failed,
            "duration_s": round(elapsed, 1),
        },
    )

    return {
        "issues_processed": total_processed,
        "issues_failed": total_failed,
        "staging_cleaned": staging_cleaned,
        "duration_s": round(elapsed, 1),
    }


async def _persist_issue(
    session: AsyncSession,
    issue: dict,
    embedding: list[float],
) -> None:
    """Persist single issue with embedding to ingestion.issue table."""
    persistence = StreamingPersistence(session)
    await persistence.upsert_staged_issue(issue, embedding)
