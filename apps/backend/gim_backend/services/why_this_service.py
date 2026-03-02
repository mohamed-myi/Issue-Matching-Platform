import re
from typing import Any

from gim_shared.constants import (
    DEFAULT_TECH_KEYWORDS,
    PROFILE_LANGUAGES,
    STACK_AREAS,
    TECH_KEYWORDS_BY_LANGUAGE,
    normalize_skill,
)
from pydantic import BaseModel

_TOKEN_RE = re.compile(r"[a-z0-9\+\#\.]+")


class WhyThisItem(BaseModel):
    entity: str
    score: float
    model_config = {"frozen": True}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _extract_profile_entities(profile: Any) -> set[str]:
    entities: set[str] = set()

    for lang in getattr(profile, "preferred_languages", None) or []:
        if lang in PROFILE_LANGUAGES:
            entities.add(lang)
    for lang in getattr(profile, "github_languages", None) or []:
        if lang in PROFILE_LANGUAGES:
            entities.add(lang)

    for area in getattr(profile, "intent_stack_areas", None) or []:
        if area in STACK_AREAS:
            entities.add(area)

    for raw in getattr(profile, "preferred_topics", None) or []:
        canon = normalize_skill(raw)
        if canon:
            entities.add(canon)
    for raw in getattr(profile, "github_topics", None) or []:
        canon = normalize_skill(raw)
        if canon:
            entities.add(canon)

    for raw in getattr(profile, "resume_skills", None) or []:
        canon = normalize_skill(raw)
        if canon:
            entities.add(canon)
    for raw in getattr(profile, "resume_job_titles", None) or []:
        canon = normalize_skill(raw)
        if canon:
            entities.add(canon)

    return entities


def compute_why_this(
    *,
    profile: Any,
    issue_title: str,
    issue_body_preview: str,
    issue_labels: list[str],
    repo_primary_language: str | None,
    repo_topics: list[str],
    top_k: int = 3,
) -> list[WhyThisItem]:
    """
    Computes deterministic why_this explanations using whitelisted profile entities only.
    Returns sorted top_k items by score desc then entity asc.
    """
    entities = _extract_profile_entities(profile)
    if not entities:
        return []

    label_norms = {_norm(x) for x in (issue_labels or []) if x}

    topic_norms: set[str] = set()
    for t in repo_topics or []:
        if not t:
            continue
        canon = normalize_skill(t) or t
        topic_norms.add(_norm(canon))

    lang_norm = _norm(repo_primary_language) if repo_primary_language else ""

    text = f"{issue_title}\n{issue_body_preview}".lower()
    tokens = set(_TOKEN_RE.findall(text))
    token_norms = {_norm(t) for t in tokens}

    tech_norms: set[str] = set()
    if repo_primary_language and repo_primary_language in TECH_KEYWORDS_BY_LANGUAGE:
        tech_norms = {_norm(x) for x in TECH_KEYWORDS_BY_LANGUAGE[repo_primary_language]}
    else:
        tech_norms = {_norm(x) for x in DEFAULT_TECH_KEYWORDS}

    scores: dict[str, float] = {}

    for ent in entities:
        ent_norm = _norm(ent)
        if not ent_norm:
            continue

        score = 0.0

        if ent_norm and ent_norm in label_norms:
            score += 3.0

        if lang_norm and ent_norm == lang_norm:
            score += 2.5

        if ent_norm and ent_norm in topic_norms:
            score += 2.0

        if ent_norm and (ent_norm in token_norms or ent_norm in tech_norms or ent.lower() in text):
            score += 1.0

        if score > 0:
            scores[ent] = score

    ranked = sorted(
        (WhyThisItem(entity=k, score=v) for k, v in scores.items()),
        key=lambda x: (-x.score, x.entity.lower()),
    )
    return ranked[: max(0, top_k)]


__all__ = ["WhyThisItem", "compute_why_this"]
