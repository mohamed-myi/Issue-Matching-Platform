import inspect


def test_preview_enforces_open_state():
    from gim_backend.services import recommendation_preview_service as preview

    src_vector = inspect.getsource(preview._query_by_vector_similarity)
    src_trending = inspect.getsource(preview._query_trending_issues)

    assert "i.state = 'open'" in src_vector
    assert "i.state = 'open'" in src_trending
