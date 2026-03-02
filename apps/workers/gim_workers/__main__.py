"""
Single entrypoint for IssueIndex worker jobs.

Usage:
    JOB_TYPE=collector python -m gim_workers    # Scout + Gather -> staging table
    JOB_TYPE=collector_then_embedder python -m gim_workers  # Explicit orchestration: collector -> embedder
    JOB_TYPE=embedder python -m gim_workers     # staging table -> Nomic MoE -> DB
    JOB_TYPE=janitor python -m gim_workers      # Prune low-survival issues
    JOB_TYPE=reco_flush python -m gim_workers   # Flush recommendation events to analytics

Embedder job needs 8GB+ memory for the Nomic model.
"""

import asyncio
import logging
import os
import signal
import sys


from gim_workers.logging_config import setup_logging
from gim_backend.ingestion.nomic_moe_embedder import NomicMoEEmbedder


async def run_worker_task(
    job_type: str, embedder: NomicMoEEmbedder | None = None
) -> dict:
    """Run the specified worker job."""

    match job_type:
        case "collector":
            from gim_workers.jobs.collector_job import run_collector_job

            return await run_collector_job()

        case "collector_then_embedder":
            if not embedder:
                raise ValueError("collector_then_embedder job requires embedder instance")
            from gim_workers.jobs.collector_job import run_collector_job
            from gim_workers.jobs.embedder_job import run_embedder_job

            collector_result = await run_collector_job()
            pending_count = collector_result.get("pending_count", 0)
            if pending_count <= 0:
                return {**collector_result, "embedder_result": {}}

            logger = logging.getLogger(__name__)
            logger.info(
                "Running explicit collector->embedder workflow",
                extra={"pending_count": pending_count},
            )
            embedder_result = await run_embedder_job(embedder)
            return {**collector_result, "embedder_result": embedder_result}

        case "embedder":
            if not embedder:
                raise ValueError("Embedder job requires embedder instance")
            from gim_workers.jobs.embedder_job import run_embedder_job

            return await run_embedder_job(embedder)

        case "janitor":
            from gim_workers.jobs.janitor_job import run_janitor_job

            return await run_janitor_job()

        case "reco_flush":
            from gim_workers.jobs.reco_flush_job import run_reco_flush_job

            return await run_reco_flush_job()

        case _:
            raise ValueError(f"Unknown job type: {job_type}")


async def main() -> None:
    job_id = setup_logging()
    logger = logging.getLogger(__name__)

    job_type = os.getenv("JOB_TYPE", "collector").lower()

    logger.info(
        "Starting job",
        extra={"job_type": job_type, "job_id": job_id},
    )

    embedder: NomicMoEEmbedder | None = None

    loop = asyncio.get_running_loop()
    def _log_shutdown_signal(signum: int) -> None:
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: _log_shutdown_signal(s))

    try:
        if job_type in {"embedder", "collector_then_embedder"}:
            logger.info("Initializing shared NomicMoEEmbedder")
            embedder = NomicMoEEmbedder(max_workers=2)
            embedder.warmup()

            result = await run_worker_task(job_type, embedder)
        else:
            result = await run_worker_task(job_type)

        logger.info(
            "Job completed successfully",
            extra={"job_type": job_type, "result": result},
        )

    except* Exception as eg:
        for exc in eg.exceptions:
            logger.exception(
                f"Job failed: {exc}",
                extra={"job_type": job_type},
            )
        sys.exit(1)

    finally:
        if embedder:
            logger.info("Cleaning up shared embedder")
            embedder.close()


if __name__ == "__main__":
    asyncio.run(main())
