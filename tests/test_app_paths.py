from pathlib import Path

import app_paths


def test_paths_use_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setattr(app_paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    root = tmp_path / "Skill Tree"
    assert app_paths.get_app_root() == root
    assert app_paths.get_data_dir() == root / "Data"
    assert app_paths.get_log_dir() == root / "Logs"


def test_paths_have_a_deterministic_fallback(monkeypatch):
    monkeypatch.setattr(app_paths.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert app_paths.get_app_root() == (
        Path.home() / "AppData" / "Local" / "Skill Tree"
    )


def test_macos_application_support(monkeypatch, tmp_path):
    monkeypatch.setattr(app_paths.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert app_paths.get_app_root() == tmp_path / "Library" / "Application Support" / "Skill Tree"


def test_linux_xdg_or_default(monkeypatch, tmp_path):
    monkeypatch.setattr(app_paths.sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert app_paths.get_app_root() == tmp_path / "xdg" / "Skill Tree"
    monkeypatch.setenv("XDG_DATA_HOME", "relative")
    assert app_paths.get_app_root() == tmp_path / ".local" / "share" / "Skill Tree"
