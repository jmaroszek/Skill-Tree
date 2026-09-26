"""What changes when the server runs as a frozen (PyInstaller) build (P3.8)."""
import sys
from pathlib import Path

import pytest

import app_paths
import callback_helpers
import resource_links

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def frozen(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "assets").mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    return bundle


def test_files_shipped_with_the_app_resolve_beside_the_code():
    assert app_paths.resource_path("assets") == ROOT / "assets"


def test_files_shipped_with_the_app_resolve_inside_a_frozen_bundle(frozen):
    assert app_paths.resource_path("assets") == frozen / "assets"


def test_the_app_serves_assets_from_the_resource_path(monkeypatch):
    import app as app_module
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    dash_app = app_module.create_app(app_module.AppSettings(
        environment="sandbox", configure_logging=False))
    assert Path(dash_app.config.assets_folder) == app_paths.resource_path("assets")


def test_the_tkinter_picker_is_off_in_a_frozen_build(frozen, monkeypatch):
    """sys.executable is the Skill Tree server there: '-c <script>' would start
    another server, and its output would come back as the picked path."""
    def must_not_run(*args, **kwargs):
        raise AssertionError("spawned the frozen server as a file picker")
    monkeypatch.setattr("subprocess.run", must_not_run)
    assert callback_helpers.spawn_local_file_picker("", "Select file", []) == ""


@pytest.fixture
def launched(monkeypatch):
    calls = []

    def popen(args, **kwargs):
        calls.append((args, kwargs.get("env")))
    monkeypatch.setattr(resource_links.subprocess, "Popen", popen)
    monkeypatch.setattr(resource_links.sys, "platform", "linux")
    return calls


def test_a_frozen_linux_build_launches_apps_with_the_systems_libraries(
        frozen, launched, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", str(frozen))
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")

    resource_links.open_path("/home/me/notes.pdf")

    (args, env), = launched
    assert args == ["xdg-open", "/home/me/notes.pdf"]
    assert env["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in env


def test_without_an_original_the_bundle_path_is_dropped(frozen, launched, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", str(frozen))
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    resource_links.open_path("/home/me/notes.pdf")
    (_args, env), = launched
    assert "LD_LIBRARY_PATH" not in env


def test_a_frozen_linux_build_opens_web_pages_through_xdg_open(frozen, launched, monkeypatch):
    """webbrowser can't be given an environment, and its browser would load
    the bundle's libraries."""
    monkeypatch.setattr(resource_links.webbrowser, "open_new_tab",
                        lambda url: pytest.fail("used webbrowser in a frozen Linux build"))
    resource_links.open_resource("https://example.com", {"kind": "mixed", "root_path": ""})
    (args, _env), = launched
    assert args == ["xdg-open", "https://example.com"]


def test_unfrozen_builds_keep_their_environment(launched, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/lib")
    resource_links.open_path("/home/me/notes.pdf")
    (_args, env), = launched
    assert env is None  # inherit, as before
