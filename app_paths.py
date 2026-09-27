"""Filesystem locations for Skill Tree's persistent application files."""

import os
import sys
from pathlib import Path


APP_DIR_NAME = "Skill Tree"
# An absolute folder here replaces the per-user one on every OS: for tests and
# agents that must not touch real data, and for a portable install.
HOME_ENV = "SKILLTREE_HOME"


def get_app_root() -> Path:
    """Return the platform's per-user application data directory."""
    override = os.environ.get(HOME_ENV, "")
    if override and Path(override).is_absolute():
        return Path(override)
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        return (Path(local_app_data) if local_app_data else
                Path.home() / "AppData" / "Local") / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    xdg_home = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg_home) if xdg_home and Path(xdg_home).is_absolute() else Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def resource_path(*parts) -> Path:
    """A file shipped with the app: beside the code, or inside a frozen
    (PyInstaller) bundle, which unpacks to sys._MEIPASS."""
    base = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    return Path(base or Path(__file__).resolve().parent).joinpath(*parts)


def get_data_dir() -> Path:
    return get_app_root() / "Data"


def get_log_dir() -> Path:
    return get_app_root() / "Logs"

