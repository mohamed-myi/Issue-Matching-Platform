"""
Service for fetching and processing GitHub profile data for recommendations.
Extracts languages, topics, and repo descriptions from starred and contributed repos.

For async processing via Cloud Tasks:
  - initiate_github_fetch() validates connection and enqueues task; returns immediately
  - execute_github_fetch() does the actual fetching and embedding (called by worker)
  - fetch_github_profile() is the synchronous version for testing or fallback
"""

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from gim_database.models.profiles import UserProfile
from sqlmodel.ext.asyncio.session import AsyncSession

from gim_backend.ingestion.github_client import (
    GitHubAuthError,
    GitHubGraphQLClient,
)
from gim_backend.services.cloud_tasks_service import enqueue_github_task
from gim_backend.services.linked_account_service import (
    LinkedAccountNotFoundError,
    LinkedAccountRevokedError,
    get_valid_access_token,
)
from gim_backend.services.onboarding_service import mark_onboarding_in_progress
from gim_backend.services.profile_access import get_or_create_profile_record as _get_or_create_profile
from gim_backend.services.profile_embedding_service import (
    calculate_combined_vector,
    finalize_profile_recalculation,
    mark_profile_recalculation_started,
    reset_profile_recalculation,
)
from gim_backend.services.vector_generation import generate_github_vector_with_retry

logger = logging.getLogger(__name__)


from gim_backend.core.errors import GitHubNotConnectedError, RefreshRateLimitError  # noqa: E402

REFRESH_COOLDOWN_SECONDS = 3600  # 1 hour


STARRED_REPOS_QUERY = """
query StarredRepos($login: String!, $first: Int!, $after: String) {
  user(login: $login) {
    starredRepositories(first: $first, after: $after) {
      totalCount
      nodes {
        name
        primaryLanguage { name }
        languages(first: 10) { nodes { name } }
        repositoryTopics(first: 10) { nodes { topic { name } } }
        description
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

CONTRIBUTED_REPOS_QUERY = """
query ContributedRepos($login: String!, $first: Int!) {
  user(login: $login) {
    repositoriesContributedTo(first: $first, contributionTypes: [COMMIT]) {
      totalCount
      nodes {
        name
        primaryLanguage { name }
        languages(first: 10) { nodes { name } }
        repositoryTopics(first: 10) { nodes { topic { name } } }
        description
      }
    }
  }
}
"""


async def _fetch_starred_repos(
    client: GitHubGraphQLClient,
    username: str,
    max_repos: int = 100,
) -> tuple[int, list[dict]]:
    """Fetches starred repos with pagination; returns (total_count, repos)."""
    repos = []
    cursor = None
    page_size = min(50, max_repos)

    while len(repos) < max_repos:
        variables = {
            "login": username,
            "first": page_size,
            "after": cursor,
        }

        data = await client.execute_query(
            STARRED_REPOS_QUERY,
            variables=variables,
            estimated_cost=1,
        )

        user_data = data.get("user")
        if not user_data:
            break

        starred = user_data.get("starredRepositories", {})
        _ = starred.get("totalCount", 0)
        nodes = starred.get("nodes", [])

        repos.extend(nodes)

        page_info = starred.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return (data.get("user", {}).get("starredRepositories", {}).get("totalCount", len(repos)), repos[:max_repos])


async def _fetch_contributed_repos(
    client: GitHubGraphQLClient,
    username: str,
    max_repos: int = 50,
) -> tuple[int, list[dict]]:
    """Fetches repos where user has commits; returns (total_count, repos)."""
    variables = {
        "login": username,
        "first": min(50, max_repos),
    }

    data = await client.execute_query(
        CONTRIBUTED_REPOS_QUERY,
        variables=variables,
        estimated_cost=1,
    )

    user_data = data.get("user")
    if not user_data:
        return 0, []

    contributed = user_data.get("repositoriesContributedTo", {})
    total_count = contributed.get("totalCount", 0)
    nodes = contributed.get("nodes", [])

    return total_count, nodes[:max_repos]


def _extract_languages_from_repos(repos: list[dict]) -> list[str]:
    """Extracts all languages from repo nodes."""
    languages = []
    for repo in repos:
        if not repo:
            continue
        primary = repo.get("primaryLanguage")
        if primary and primary.get("name"):
            languages.append(primary["name"])

        languages_data = repo.get("languages")
        if languages_data is None:
            continue
        lang_nodes = languages_data.get("nodes") or []
        for lang in lang_nodes:
            if lang and lang.get("name"):
                languages.append(lang["name"])

    return languages


def _extract_topics_from_repos(repos: list[dict]) -> list[str]:
    """Extracts all topics from repo nodes."""
    topics = []
    for repo in repos:
        if not repo:
            continue
        topics_data = repo.get("repositoryTopics")
        if topics_data is None:
            continue
        topic_nodes = topics_data.get("nodes") or []
        for topic_node in topic_nodes:
            if not topic_node:
                continue
            topic = topic_node.get("topic")
            if topic and topic.get("name"):
                topics.append(topic["name"])

    return topics


def _extract_descriptions_from_repos(repos: list[dict], max_count: int = 5) -> list[str]:
    """Extracts non-empty descriptions from repos."""
    descriptions = []
    for repo in repos:
        if not repo:
            continue
        desc = repo.get("description")
        if desc and desc.strip():
            descriptions.append(desc.strip())
            if len(descriptions) >= max_count:
                break
    return descriptions


def extract_languages(
    starred_repos: list[dict],
    contributed_repos: list[dict],
) -> list[str]:
    """
    Merges languages from starred and contributed repos.
    Contributed repos are weighted 2x to reflect active engagement.
    Returns deduplicated list sorted by frequency.
    """
    counter: Counter = Counter()

    starred_langs = _extract_languages_from_repos(starred_repos)
    for lang in starred_langs:
        counter[lang] += 1

    contributed_langs = _extract_languages_from_repos(contributed_repos)
    for lang in contributed_langs:
        counter[lang] += 2

    sorted_langs = sorted(counter.keys(), key=lambda x: (-counter[x], x))
    return sorted_langs


def extract_topics(
    starred_repos: list[dict],
    contributed_repos: list[dict],
) -> list[str]:
    """
    Merges topics from starred and contributed repos.
    Returns deduplicated list sorted by frequency.
    """
    counter: Counter = Counter()

    starred_topics = _extract_topics_from_repos(starred_repos)
    for topic in starred_topics:
        counter[topic] += 1

    contributed_topics = _extract_topics_from_repos(contributed_repos)
    for topic in contributed_topics:
        counter[topic] += 2  # 2x weight

    sorted_topics = sorted(counter.keys(), key=lambda x: (-counter[x], x))
    return sorted_topics


def format_github_text(
    languages: list[str],
    topics: list[str],
    descriptions: list[str],
) -> str:
    """
    Formats GitHub data into text for embedding.
    Format: "{languages}. {topics}. {descriptions}"
    """
    parts = []

    if languages:
        parts.append(", ".join(languages[:10]))

    if topics:
        parts.append(", ".join(topics[:15]))

    if descriptions:
        parts.append(" ".join(descriptions[:5]))

    return ". ".join(parts)


def check_minimal_data(
    starred_count: int,
    contributed_count: int,
) -> str | None:
    """
    Returns warning message if data is below threshold per PROFILE.md lines 229 to 236.
    Threshold: fewer than 3 public repos AND fewer than 5 starred repos.
    """
    if contributed_count < 3 and starred_count < 5:
        return (
            "We found limited public activity on your GitHub profile. "
            "For better recommendations, consider adding manual input."
        )
    return None


def check_refresh_allowed(
    last_fetched_at: datetime | None,
) -> int | None:
    """
    Returns None if refresh is allowed; seconds remaining otherwise.
    """
    if last_fetched_at is None:
        return None

    now = datetime.now(UTC)
    if last_fetched_at.tzinfo is None:
        last_fetched_at = last_fetched_at.replace(tzinfo=UTC)

    elapsed = (now - last_fetched_at).total_seconds()
    if elapsed >= REFRESH_COOLDOWN_SECONDS:
        return None

    return int(REFRESH_COOLDOWN_SECONDS - elapsed)


async def generate_github_vector(
    languages: list[str],
    topics: list[str],
    descriptions: list[str],
) -> list[float] | None:
    """Generates 768-dim embedding from GitHub profile data with retry support."""
    text = format_github_text(languages, topics, descriptions)

    if not text:
        logger.warning("Cannot generate GitHub vector: no text content")
        return None

    logger.info(f"Generating GitHub vector for text length {len(text)}")
    vector = await generate_github_vector_with_retry(text)

    if vector is None:
        logger.warning("GitHub vector generation failed after retries")
        return None

    return vector


async def initiate_github_fetch(
    db: AsyncSession,
    user_id: UUID,
    is_refresh: bool = False,
) -> dict:
    """
    Validates GitHub connection and enqueues Cloud Task for async processing.
    Returns immediately with job_id and status 'processing'.
    """
    profile = await _get_or_create_profile(db, user_id)

    if is_refresh and profile.github_fetched_at:
        seconds_remaining = check_refresh_allowed(profile.github_fetched_at)
        if seconds_remaining is not None:
            raise RefreshRateLimitError(seconds_remaining)

    try:
        await get_valid_access_token(db, user_id, "github")
    except LinkedAccountNotFoundError:
        raise GitHubNotConnectedError(
            "No GitHub account connected. Please connect GitHub first at /auth/connect/github"
        )
    except LinkedAccountRevokedError:
        raise GitHubNotConnectedError("Please reconnect your GitHub account")

    await mark_onboarding_in_progress(db, profile)

    mark_profile_recalculation_started(profile)
    await db.commit()

    try:
        job_id = await enqueue_github_task(user_id)
    except Exception:
        reset_profile_recalculation(profile)
        await db.commit()
        raise

    logger.info(f"GitHub fetch initiated for user {user_id}, job_id {job_id}")

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "GitHub profile fetch started. Processing in background.",
    }


@dataclass
class GitHubFetchPipelineData:
    username: str
    starred_count: int
    contributed_count: int
    languages: list[str]
    topics: list[str]
    descriptions: list[str]
    minimal_warning: str | None
    starred_repo_names: list[str]
    contributed_repo_names: list[str]


async def _reset_github_recalculation_and_commit(
    db: AsyncSession,
    profile: UserProfile,
    *,
    enabled: bool,
) -> None:
    if not enabled:
        return
    reset_profile_recalculation(profile)
    await db.commit()


def _build_github_profile_response(profile: UserProfile, data: GitHubFetchPipelineData) -> dict:
    return {
        "status": "ready",
        "username": data.username,
        "starred_count": data.starred_count,
        "contributed_repos": data.contributed_count,
        "languages": profile.github_languages or [],
        "topics": profile.github_topics or [],
        "vector_status": "ready" if profile.github_vector else None,
        "fetched_at": profile.github_fetched_at.isoformat() if profile.github_fetched_at else None,
        "minimal_data_warning": data.minimal_warning,
    }


def _store_github_profile_data(profile: UserProfile, data: GitHubFetchPipelineData) -> None:
    profile.github_username = data.username
    profile.github_languages = data.languages[:20] if data.languages else []
    profile.github_topics = data.topics[:30] if data.topics else []
    profile.github_data = {
        "starred_count": data.starred_count,
        "contributed_count": data.contributed_count,
        "starred_repos": data.starred_repo_names,
        "contributed_repos": data.contributed_repo_names,
    }
    profile.github_fetched_at = datetime.now(UTC)


async def _fetch_github_pipeline_data(
    db: AsyncSession,
    profile: UserProfile,
    user_id: UUID,
    *,
    cleanup_on_connect_error: bool,
    missing_account_message: str | None,
    revoked_account_message: str | None,
    auth_error_message: str,
    username_missing_message: str,
) -> GitHubFetchPipelineData:
    try:
        access_token = await get_valid_access_token(db, user_id, "github")
    except LinkedAccountNotFoundError as exc:
        await _reset_github_recalculation_and_commit(db, profile, enabled=cleanup_on_connect_error)
        raise GitHubNotConnectedError(missing_account_message or str(exc)) from exc
    except LinkedAccountRevokedError as exc:
        await _reset_github_recalculation_and_commit(db, profile, enabled=cleanup_on_connect_error)
        raise GitHubNotConnectedError(revoked_account_message or str(exc)) from exc

    async with GitHubGraphQLClient(access_token) as client:
        try:
            username = await client.verify_authentication()
        except GitHubAuthError as exc:
            await _reset_github_recalculation_and_commit(db, profile, enabled=cleanup_on_connect_error)
            raise GitHubNotConnectedError(auth_error_message) from exc

        if not username:
            await _reset_github_recalculation_and_commit(db, profile, enabled=cleanup_on_connect_error)
            raise GitHubNotConnectedError(username_missing_message)

        starred_count, starred_repos = await _fetch_starred_repos(client, username)
        contributed_count, contributed_repos = await _fetch_contributed_repos(client, username)

    languages = extract_languages(starred_repos, contributed_repos)
    topics = extract_topics(starred_repos, contributed_repos)

    descriptions = _extract_descriptions_from_repos(contributed_repos, max_count=3)
    descriptions.extend(_extract_descriptions_from_repos(starred_repos, max_count=2))

    return GitHubFetchPipelineData(
        username=username,
        starred_count=starred_count,
        contributed_count=contributed_count,
        languages=languages,
        topics=topics,
        descriptions=descriptions,
        minimal_warning=check_minimal_data(starred_count, contributed_count),
        starred_repo_names=[r.get("name") for r in starred_repos[:20] if r],
        contributed_repo_names=[r.get("name") for r in contributed_repos[:20] if r],
    )


async def _run_github_fetch_pipeline(
    db: AsyncSession,
    profile: UserProfile,
    user_id: UUID,
    *,
    mark_onboarding: bool,
    start_recalculation: bool,
    cleanup_on_connect_error: bool,
    missing_account_message: str | None,
    revoked_account_message: str | None,
    auth_error_message: str,
    username_missing_message: str,
) -> dict:
    if mark_onboarding:
        await mark_onboarding_in_progress(db, profile)

    data = await _fetch_github_pipeline_data(
        db,
        profile,
        user_id,
        cleanup_on_connect_error=cleanup_on_connect_error,
        missing_account_message=missing_account_message,
        revoked_account_message=revoked_account_message,
        auth_error_message=auth_error_message,
        username_missing_message=username_missing_message,
    )

    _store_github_profile_data(profile, data)
    if start_recalculation:
        mark_profile_recalculation_started(profile)
    await db.commit()

    try:
        logger.info(f"Generating GitHub vector for user {user_id}")
        github_vector = await generate_github_vector(data.languages, data.topics, data.descriptions)
        profile.github_vector = github_vector

        await finalize_profile_recalculation(
            profile,
            calculate_combined_vector_fn=calculate_combined_vector,
        )
        logger.info(f"GitHub vector generated for user {user_id}")
    finally:
        if profile.is_calculating:
            reset_profile_recalculation(profile)

    await db.commit()
    await db.refresh(profile)
    return _build_github_profile_response(profile, data)


async def execute_github_fetch(
    db: AsyncSession,
    user_id: UUID,
) -> dict:
    """
    Executes full GitHub fetch and embedding. Called by worker.
    Does not check refresh rate limit (already validated in initiate).
    """
    profile = await _get_or_create_profile(db, user_id)
    return await _run_github_fetch_pipeline(
        db,
        profile,
        user_id,
        mark_onboarding=False,
        start_recalculation=False,
        cleanup_on_connect_error=True,
        missing_account_message=None,
        revoked_account_message=None,
        auth_error_message="Please reconnect your GitHub account",
        username_missing_message="Could not retrieve GitHub username",
    )


async def fetch_github_profile(
    db: AsyncSession,
    user_id: UUID,
    is_refresh: bool = False,
) -> dict:
    """
    Synchronous version: Full GitHub fetch and embedding in one call.
    Used for testing or as fallback when Cloud Tasks is unavailable.
    """
    profile = await _get_or_create_profile(db, user_id)

    if is_refresh and profile.github_fetched_at:
        seconds_remaining = check_refresh_allowed(profile.github_fetched_at)
        if seconds_remaining is not None:
            raise RefreshRateLimitError(seconds_remaining)

    return await _run_github_fetch_pipeline(
        db,
        profile,
        user_id,
        mark_onboarding=True,
        start_recalculation=True,
        cleanup_on_connect_error=False,
        missing_account_message="No GitHub account connected. Please connect GitHub first at /auth/connect/github",
        revoked_account_message="Please reconnect your GitHub account",
        auth_error_message="Please reconnect your GitHub account",
        username_missing_message="Could not retrieve GitHub username. Please reconnect.",
    )


async def get_github_data(
    db: AsyncSession,
    user_id: UUID,
) -> dict | None:
    """Returns stored GitHub profile data or None if not populated."""
    profile = await _get_or_create_profile(db, user_id)

    if profile.github_username is None:
        return None

    github_data = profile.github_data or {}

    return {
        "status": "ready",
        "username": profile.github_username,
        "starred_count": github_data.get("starred_count", 0),
        "contributed_repos": github_data.get("contributed_count", 0),
        "languages": profile.github_languages or [],
        "topics": profile.github_topics or [],
        "vector_status": "ready" if profile.github_vector else None,
        "fetched_at": profile.github_fetched_at.isoformat() if profile.github_fetched_at else None,
    }


async def delete_github(
    db: AsyncSession,
    user_id: UUID,
) -> bool:
    """Clears GitHub data and recalculates combined vector."""
    profile = await _get_or_create_profile(db, user_id)

    if profile.github_username is None:
        return False

    mark_profile_recalculation_started(profile)
    await db.commit()

    try:
        profile.github_username = None
        profile.github_languages = None
        profile.github_topics = None
        profile.github_data = None
        profile.github_fetched_at = None
        profile.github_vector = None

        logger.info(f"Recalculating combined vector after GitHub deletion for user {user_id}")
        await finalize_profile_recalculation(
            profile,
            calculate_combined_vector_fn=calculate_combined_vector,
        )
    finally:
        if profile.is_calculating:
            reset_profile_recalculation(profile)

    await db.commit()
    await db.refresh(profile)
    return True


__all__ = [
    "REFRESH_COOLDOWN_SECONDS",
    "extract_languages",
    "extract_topics",
    "format_github_text",
    "check_minimal_data",
    "check_refresh_allowed",
    "generate_github_vector",
    "initiate_github_fetch",
    "execute_github_fetch",
    "fetch_github_profile",
    "get_github_data",
    "delete_github",
]
