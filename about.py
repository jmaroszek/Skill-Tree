"""What Settings > About reports: the build, the data, and where to get help.

diagnostics() is the text a bug report needs. It gets pasted into public
issues, so it names folders relative to the home folder (~) rather than by
the user's name.
"""
import platform
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlencode

import config
import database
from app_paths import get_log_dir, resource_path
from version import __version__

REPO_URL = "https://github.com/jmaroszek/Skill-Tree"
ISSUES_NEW_URL = f"{REPO_URL}/issues/new"
RELEASES_URL = f"{REPO_URL}/releases"
# The README's tour, until the website has its own help pages (P7.4).
HELP_URL = f"{REPO_URL}#readme"


def notices_path():
    """The third-party notices bundled with this build, or None in a checkout
    that hasn't generated them (packaging/third_party_notices.py)."""
    path = resource_path("THIRD_PARTY_NOTICES.txt")
    return path if path.is_file() else None


def _home_relative(path) -> str:
    """The path with the home folder shown as ~."""
    text = str(path)
    home = str(Path.home())
    if home and text.lower().startswith(home.lower()):
        return "~" + text[len(home):]
    return text


def _database_summary() -> str:
    conn = database.get_connection()
    try:
        schema = conn.execute("PRAGMA user_version").fetchone()[0]
        counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("Nodes", "Edges", "Events")]
    finally:
        conn.close()
    return "schema {}, {} nodes, {} edges, {} events".format(schema, *counts)


def diagnostics() -> str:
    import dash
    build = config.ENVIRONMENT + (", packaged" if getattr(sys, "frozen", False) else "")
    lines = [
        f"Skill Tree {__version__} ({build})",
        f"OS: {platform.platform()}",
        f"Python {platform.python_version()}, SQLite {sqlite3.sqlite_version}, "
        f"Dash {dash.__version__}",
    ]
    try:
        lines.append(f"Data: {_home_relative(database.get_db_path())} "
                     f"({_database_summary()})")
    except Exception as exc:  # the report is most wanted when things are broken
        lines.append(f"Data: {_home_relative(database.get_db_path())} (unreadable: {exc})")
    lines.append(f"Logs: {_home_relative(get_log_dir())}")
    return "\n".join(lines)


def report_url(diagnostics_text: str) -> str:
    """GitHub's bug form, with the diagnostics field already filled in."""
    return ISSUES_NEW_URL + "?" + urlencode(
        {"template": "bug_report.yml", "diagnostics": diagnostics_text})
