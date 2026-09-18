"""Filesystem locations for Skill Tree's persistent application files."""

import os
from pathlib import Path


APP_DIR_NAME = "Skill Tree"


def get_app_root() -> Path:
    """Return the per-user application directory.

    LOCALAPPDATA is Windows' standard location for machine-local application
    state.  The fallback keeps imports and tests usable in environments that
    do not expose the Windows variable.
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME


def get_data_dir() -> Path:
    return get_app_root() / "Data"


def get_log_dir() -> Path:
    return get_app_root() / "Logs"

