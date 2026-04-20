"""Smoke test: the app module imports cleanly and registers its callbacks."""

import importlib
import sys

import pytest


@pytest.fixture
def isolated_app_import(monkeypatch):
    """Force a fresh `import app` inside a test, with browser/timer side effects neutralized."""
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")

    import threading
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **kw: None)

    class _NoopTimer:
        def __init__(self, *a, **kw): pass
        def start(self): pass
        def cancel(self): pass

    monkeypatch.setattr(threading, "Timer", _NoopTimer)

    for modname in ("app",):
        sys.modules.pop(modname, None)

    import app as app_module
    importlib.reload(app_module)
    return app_module


def test_app_module_imports_without_side_effects(isolated_app_import):
    app_module = isolated_app_import
    assert app_module.app is not None
    assert app_module.app.layout is not None


def test_app_callback_map_has_many_callbacks(isolated_app_import):
    app_module = isolated_app_import
    assert len(app_module.app.callback_map) >= 40, (
        f"expected >=40 registered callbacks, got {len(app_module.app.callback_map)}"
    )


def test_app_title_reflects_environment(isolated_app_import):
    app_module = isolated_app_import
    assert app_module.app.title in {"Skill Tree", "Skill Tree (Sandbox)"}
