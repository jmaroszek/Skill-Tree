from pathlib import Path

import app_paths


def test_paths_use_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    root = tmp_path / "Skill Tree"
    assert app_paths.get_app_root() == root
    assert app_paths.get_data_dir() == root / "Data"
    assert app_paths.get_log_dir() == root / "Logs"


def test_paths_have_a_deterministic_fallback(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert app_paths.get_app_root() == (
        Path.home() / "AppData" / "Local" / "Skill Tree"
    )
