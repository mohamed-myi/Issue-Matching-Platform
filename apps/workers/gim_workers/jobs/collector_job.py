"""
Collector job: Scout repositories and gather issues to staging table.

This is Job 1 of the two-phase ingestion pipeline:
1. Discover top repositories
2. Filter for workload sharding
3. Stream issues with Q-Score filtering
4. Write to staging.pending_issue for async embedding

The Embedder job (Job 2) processes pending issues and generates embeddings.
"""

import logging
import time

from gim_backend.core.config import get_settings
from gim_backend.ingestion.gatherer import Gatherer
from gim_backend.ingestion.github_client import GitHubGraphQLClient
from gim_backend.ingestion.persistence import StreamingPersistence
from gim_backend.ingestion.staging_persistence import StagingPersistence
from gim_backend.ingestion.scout import Scout
from gim_database.session import async_session_factory

logger = logging.getLogger(__name__)


async def run_collector_job() -> dict:
    """
    Executes the collection pipeline:
    1. Discover top repositories
    2. Filter via dynamic sharding
    3. Stream issues with Q-Score filtering
    4. Write issues to staging table for async embedding

    Returns stats dict with repos_discovered and issues_staged.
    """
    job_start = time.monotonic()
    settings = get_settings()

    if not settings.git_token:
        raise ValueError("GIT_TOKEN environment variable is required")

    logger.info(
        "Collector config",
        extra={
            "gatherer_concurrency": settings.gatherer_concurrency,
            "max_issues_per_repo": settings.max_issues_per_repo,
        },
    )

    async with GitHubGraphQLClient(settings.git_token) as client:
        scout_start = time.monotonic()
        logger.info("Starting Scout - discovering repositories")
        scout = Scout(client)
        all_repos = await scout.discover_repositories()


        from binascii import crc32
        from datetime import UTC, datetime

        current_shard = datetime.now(UTC).hour
        repos = []

        for repo in all_repos:
            shard_id = crc32(repo.node_id.encode("utf-8")) % 24
            if shard_id == current_shard:
                repos.append(repo)

        scout_elapsed = time.monotonic() - scout_start

        logger.info(
            f"Scout complete in {scout_elapsed:.1f}s - "
            f"Selected {len(repos)}/{len(all_repos)} repositories for shard {current_shard}",
            extra={
                "repos_discovered": len(all_repos),
                "repos_selected": len(repos),
                "shard_id": current_shard,
                "scout_duration_s": round(scout_elapsed, 1),
            },
        )

        if not repos:
            logger.warning(
                f"No repositories selected for shard {current_shard}; skipping collection"
            )
            return {"repos_discovered": len(all_repos), "issues_staged": 0}

        persist_start = time.monotonic()
        async with async_session_factory() as session:
            persistence = StreamingPersistence(session)
            repos_upserted = await persistence.upsert_repositories(repos)
        persist_elapsed = time.monotonic() - persist_start

        logger.info(
            f"Repositories upserted in {persist_elapsed:.1f}s: {repos_upserted}",
            extra={
                "repos_upserted": repos_upserted,
                "persist_duration_s": round(persist_elapsed, 1),
            },
        )

        gather_start = time.monotonic()

        logger.info(
            f"Starting Gather with concurrency={settings.gatherer_concurrency}",
            extra={"concurrency": settings.gatherer_concurrency},
        )

        gatherer = Gatherer(
            client,
            max_issues_per_repo=settings.max_issues_per_repo,
            concurrency=settings.gatherer_concurrency,
        )

        issues_collected = []
        async for issue in gatherer.harvest_issues(repos):
            issues_collected.append(issue)

            if len(issues_collected) >= 100:
                async with async_session_factory() as session:
                    staging = StagingPersistence(session)
                    await staging.insert_pending_issues(issues_collected)
                issues_collected = []

        if issues_collected:
            async with async_session_factory() as session:
                staging = StagingPersistence(session)
                await staging.insert_pending_issues(issues_collected)

        gather_elapsed = time.monotonic() - gather_start

        async with async_session_factory() as session:
            staging = StagingPersistence(session)
            pending_count = await staging.get_pending_count()

        logger.info(
            f"Gather + Stage complete in {gather_elapsed:.1f}s",
            extra={
                "gather_duration_s": round(gather_elapsed, 1),
                "pending_count": pending_count,
            },
        )

        job_elapsed = time.monotonic() - job_start
        logger.info(
            f"Collector job complete in {job_elapsed:.1f}s",
            extra={
                "total_duration_s": round(job_elapsed, 1),
                "scout_duration_s": round(scout_elapsed, 1),
                "gather_duration_s": round(gather_elapsed, 1),
                "repos_discovered": len(repos),
                "pending_count": pending_count,
            },
        )

        # Collector stops at staging. Any collector->embedder orchestration is
        # handled explicitly by the entrypoint/scheduler layer.
        return {
            "repos_discovered": len(repos),
            "pending_count": pending_count,
            "duration_s": round(job_elapsed, 1),
        }
