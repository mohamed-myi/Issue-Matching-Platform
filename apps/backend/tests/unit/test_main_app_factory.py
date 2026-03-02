"""Unit tests for lazy app factory behavior in gim_backend.main."""

import gim_backend.main as main_module


def test_get_app_caches_created_app(monkeypatch):
    main_module.reset_app_for_testing()

    created = object()
    calls = {"count": 0}

    def fake_create_app():
        calls["count"] += 1
        return created

    monkeypatch.setattr(main_module, "create_app", fake_create_app)

    assert main_module.get_app() is created
    assert main_module.get_app() is created
    assert calls["count"] == 1


def test_module_app_attribute_uses_lazy_getattr(monkeypatch):
    main_module.reset_app_for_testing()

    created = object()
    monkeypatch.setattr(main_module, "create_app", lambda: created)

    assert getattr(main_module, "app") is created
