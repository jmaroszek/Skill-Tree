"""Named node resources and one platform-neutral opener."""

from __future__ import annotations

import json
import ntpath
import os
import re
import subprocess
import sys
import urllib.parse
import uuid
import webbrowser

import database

MAX_SECTIONS = 5
BUILTIN_IDS = ("obsidian", "drive", "website")
_WEB = re.compile(r"^https?://", re.IGNORECASE)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_DOMAIN = re.compile(r"^(?:www\.)?[^/\\\s]+\.[a-z]{2,}(?:[/:?#]|$)", re.IGNORECASE)
_FILE_SUFFIXES = {"txt", "md", "pdf", "png", "jpg", "jpeg", "gif", "webp",
                  "svg", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv",
                  "json", "yaml", "yml", "html", "htm", "py", "js", "zip"}


def parse_links(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if isinstance(item, str) and item.strip()]
    except (ValueError, TypeError):
        pass
    return [value] if isinstance(value, str) and value.strip() else []


def get_sections():
    snapshot = database.current_snapshot()
    if snapshot is not None:
        return [dict(row) for row in snapshot.resource_sections]
    with database.get_connection() as conn:
        conn.row_factory = database.sqlite3.Row
        return [dict(row) for row in conn.execute(
            "SELECT id, name, kind, root_path, enabled, position FROM ResourceSections ORDER BY position")]


def get_node_links(node_name):
    if not node_name:
        return {}
    snapshot = database.current_snapshot()
    if snapshot is not None:
        return {key: list(values) for key, values in snapshot.resource_links.get(node_name, {}).items()}
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT section_id, target FROM NodeResourceLinks WHERE node_name=? "
            "ORDER BY section_id, position", (node_name,)).fetchall()
    result = {}
    for section_id, target in rows:
        result.setdefault(section_id, []).append(target)
    return result


def section_has_links(section_id):
    with database.get_connection() as conn:
        return conn.execute("SELECT 1 FROM NodeResourceLinks WHERE section_id=? LIMIT 1",
                            (section_id,)).fetchone() is not None


def absolute_path(value):
    return os.path.isabs(value) or ntpath.isabs(value)


def store_path(value, root):
    """Use portable forward-slash relative paths only when safely inside root."""
    value = value.strip()
    root = (root or "").strip()
    if not root or not absolute_path(value) or not absolute_path(root):
        return value
    windows = bool(ntpath.splitdrive(value)[0] or ntpath.splitdrive(root)[0])
    pathmod = ntpath if windows else os.path
    try:
        relative = pathmod.relpath(pathmod.normpath(value), pathmod.normpath(root))
    except ValueError:  # different Windows drives
        return value
    if relative == ".":
        return relative
    if relative == ".." or relative.startswith(".." + pathmod.sep):
        return value
    return relative.replace("\\", "/")


def normalize_link(value, section):
    value = (value or "").strip()
    if not value or _WEB.match(value) or _SCHEME.match(value):
        return value
    return store_path(value, section.get("root_path", ""))


def resolve_target(value, section):
    """Return ('web'|'path'|'uri', target); never mistake a drive for a URI."""
    value = (value or "").strip()
    if not value:
        raise ValueError("No file path or URL set.")
    if _WEB.match(value):
        return "web", value
    if _SCHEME.match(value):
        return "uri", value
    root = (section.get("root_path") or "").strip()
    if section.get("kind") == "obsidian":
        path = value if absolute_path(value) else os.path.join(root, value)
        if not root and not absolute_path(value):
            raise ValueError("Set an Obsidian vault path in Settings.")
        return "uri", "obsidian://open?path=" + urllib.parse.quote(path, safe="")
    if absolute_path(value) or os.path.exists(value):
        return "path", value
    if root:
        return "path", os.path.join(root, value.replace("/", os.sep))
    suffix = value.rsplit('.', 1)[-1].lower() if '.' in value else ''
    if _DOMAIN.match(value) and suffix not in _FILE_SUFFIXES:
        return "web", "https://" + value
    raise ValueError("Use an absolute file path or set a root folder for relative paths.")


def open_path(target):
    """Ask the OS to open a file, folder, or registered custom URI."""
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target], shell=False)
    else:
        subprocess.Popen(["xdg-open", target], shell=False)


def open_resource(value, section):
    kind, target = resolve_target(value, section)
    if kind == "web":
        if not webbrowser.open_new_tab(target):
            raise OSError("No browser accepted the URL.")
    else:
        if kind == "path":
            if not absolute_path(target):
                target = os.path.abspath(target)
            if not os.path.exists(target):
                raise FileNotFoundError(target)
        open_path(target)


@database.atomic
def save_node_links(node_name, submitted):
    """Replace submitted sections only; hidden sections retain their links."""
    sections = {row["id"]: row for row in get_sections()}
    with database.get_connection() as conn:
        for section_id, values in submitted.items():
            section = sections.get(section_id)
            if section is None or not section["enabled"]:
                continue
            cleaned = [normalize_link(value, section) for value in values if value and value.strip()]
            conn.execute("DELETE FROM NodeResourceLinks WHERE node_name=? AND section_id=?",
                         (node_name, section_id))
            conn.executemany(
                "INSERT INTO NodeResourceLinks(node_name, section_id, position, target) VALUES (?, ?, ?, ?)",
                [(node_name, section_id, i, target) for i, target in enumerate(cleaned)])
            # Keep old columns as a compatibility mirror until every older
            # consumer has moved to the named-section model.
            column = {"obsidian": "obsidian_path", "drive": "google_drive_path",
                      "website": "website"}.get(section_id)
            if column:
                conn.execute(f"UPDATE Nodes SET {column}=? WHERE name=?",
                             (json.dumps(cleaned) if cleaned else None, node_name))


@database.atomic
def save_sections(rows):
    """Validate and save the complete ordered section list."""
    validate_sections(rows)
    ids = [row.get("id") for row in rows]
    names = [(row.get("name") or "").strip() for row in rows]
    with database.get_connection() as conn:
        current = {row[0]: row[1] for row in conn.execute(
            "SELECT id, kind FROM ResourceSections")}
        removed = set(current) - set(ids)
        for section_id in removed:
            conn.execute("DELETE FROM ResourceSections WHERE id=?", (section_id,))
        saved = []
        for i, row in enumerate(rows):
            section_id = row.get("id") or uuid.uuid4().hex
            kind = current.get(section_id, "mixed")
            conn.execute(
                "INSERT INTO ResourceSections(id, name, kind, root_path, enabled, position) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, root_path=excluded.root_path, "
                "enabled=excluded.enabled, position=excluded.position",
                (section_id, names[i], kind, (row.get("root_path") or "").strip(),
                 int(bool(row.get("enabled"))), i))
            saved.append({"id": section_id, "name": names[i], "kind": kind,
                          "root_path": (row.get("root_path") or "").strip(),
                          "enabled": int(bool(row.get("enabled"))), "position": i})
    return saved


def validate_sections(rows):
    """Reject invalid edits before an unrelated Settings save writes anything."""
    if not 1 <= len(rows) <= MAX_SECTIONS:
        raise ValueError("Keep between one and five Resource sections.")
    ids = [row.get("id") for row in rows]
    names = [(row.get("name") or "").strip() for row in rows]
    if (len(set(ids)) != len(ids) or any(not name for name in names) or
            len(set(name.casefold() for name in names)) != len(names)):
        raise ValueError("Resource section names must be nonempty and unique.")
    with database.get_connection() as conn:
        current = {row[0]: row[1] for row in conn.execute(
            "SELECT id, kind FROM ResourceSections")}
        removed = set(current) - set(ids)
        for section_id in removed:
            if section_id in BUILTIN_IDS or conn.execute(
                "SELECT 1 FROM NodeResourceLinks WHERE section_id=? LIMIT 1", (section_id,)
            ).fetchone():
                raise ValueError("Disable a section with links; only empty custom sections can be removed.")
