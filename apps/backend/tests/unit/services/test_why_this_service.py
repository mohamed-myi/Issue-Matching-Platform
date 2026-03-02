from gim_backend.services.why_this_service import compute_why_this


class _Profile:
    def __init__(self):
        self.preferred_languages = ["Python"]
        self.github_languages = ["Rust"]
        self.intent_stack_areas = ["backend"]
        self.resume_skills = ["FastAPI", "NotInTaxonomy"]
        self.resume_job_titles = ["Software Engineer"]
        self.preferred_topics = ["docker"]
        self.github_topics = ["kubernetes"]


def test_compute_why_this_deterministic_top3_and_sorted():
    profile = _Profile()
    why = compute_why_this(
        profile=profile,
        issue_title="FastAPI error in Python service",
        issue_body_preview="asyncio traceback",
        issue_labels=["python", "fastapi", "bug"],
        repo_primary_language="Python",
        repo_topics=["fastapi", "docker"],
        top_k=3,
    )

    assert len(why) == 3

    # Deterministic ordering: score desc then entity asc.
    assert all(why[i].score >= why[i + 1].score for i in range(len(why) - 1))
    if why[0].score == why[1].score:
        assert why[0].entity.lower() <= why[1].entity.lower()


def test_compute_why_this_whitelist_filters_unknown_resume_skill():
    profile = _Profile()
    why = compute_why_this(
        profile=profile,
        issue_title="NotInTaxonomy appears in text",
        issue_body_preview="NotInTaxonomy",
        issue_labels=["notintaxonomy"],
        repo_primary_language="Python",
        repo_topics=[],
        top_k=10,
    )
    entities = {w.entity for w in why}
    assert "NotInTaxonomy" not in entities


def test_compute_why_this_empty_when_no_profile_entities():
    profile = type("P", (), {})()
    why = compute_why_this(
        profile=profile,
        issue_title="x",
        issue_body_preview="y",
        issue_labels=[],
        repo_primary_language=None,
        repo_topics=[],
        top_k=3,
    )
    assert why == []
