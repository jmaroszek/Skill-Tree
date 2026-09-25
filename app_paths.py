"""Filesystem locations for Skill Tree's persistent application files."""

import os
import sys
from pathlib import Path


APP_DIR_NAME = "Skill Tree"


def get_app_root() -> Path:
    """Return the platform's per-user application data directory."""
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        return (Path(local_app_data) if local_app_data else
                Path.home() / "AppData" / "Local") / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    xdg_home = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg_home) if xdg_home and Path(xdg_home).is_absolute() else Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def get_data_dir() -> Path:
    return get_app_root() / "Data"


def get_log_dir() -> Path:
    return get_app_root() / "Logs"

