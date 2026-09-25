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
# How a section opens its links: "obsidian" sends Markdown notes to the
# Obsidian app by URI; "mixed" hands URLs to the browser and files to the OS.
KINDS = ("obsidian", "mixed")
_WEB = re.compile(r"^https?://", re.IGNORECASE)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_DOMAIN = re.compile(r"^(?:www\.)?[^/\\\s]+\.[a-z]{2,}(?:[/:?#]|$)", re.IGNORECASE)
_FILE_SUFFIXES = {"txt", "md", "pdf", "png", "jpg", "jpeg", "gif", "webp",
                  "svg", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv",
                  "json", "yaml", "yml", "html", "htm", "py", "js", "zip"}
# What Obsidian itself opens: notes, canvases, bases, PDFs, and the image,
# audio and video formats it embeds. Anything else in an Obsidian section
# goes to the default app instead.
OBSIDIAN_SUFFIXES = {"md", "canvas", "base", "pdf",
                     "png", "jpg", "jpeg", "gif", "bmp", "svg", "webp", "avif",
                     "mp3", "wav", "m4a", "ogg", "flac", "3gp", "webm",
                     "mp4", "ogv", "mov", "mkv"}


def in_obsidian_vault(path):
    """True when a folder above `path` is a vault, which holds `.obsidian`."""
    folder = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isdir(os.path.join(folder, ".obsidian")):
            return True
        parent = os.path.dirname(folder)
        if parent == folder:
            return False
        folder = parent


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
            "SELECT id, name, kind, root_path, position FROM ResourceSections ORDER BY position")]


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


def section_link_counts():
    """How many links each section holds, for the Settings removal warning."""
    with database.get_connection() as conn:
        return dict(conn.execute(
            "SELECT section_id, COUNT(*) FROM NodeResourceLinks GROUP BY section_id"))


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
        if not root and not absolute_path(value):
            raise ValueError("Set this resource's root folder to your Obsidian vault in Settings.")
        path = os.path.normpath(value if absolute_path(value)
                                else os.path.join(root, value.replace("/", os.sep)))
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        # Obsidian can only open its own file types, and only inside a vault
        # it knows. Anything else still opens, in the default app.
        suffix = path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else ""
        if suffix in OBSIDIAN_SUFFIXES and in_obsidian_vault(path):
            return "uri", "obsidian://open?path=" + urllib.parse.quote(path, safe="")
        return "path", path
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
    """Replace the submitted sections' links; other sections keep theirs."""
    sections = {row["id"]: row for row in get_sections()}
    with database.get_connection() as conn:
        for section_id, values in submitted.items():
            section = sections.get(section_id)
            if section is None:
                continue
            cleaned = [normalize_link(value, section) for value in values if value and value.strip()]
            conn.execute("DELETE FROM NodeResourceLinks WHERE node_name=? AND section_id=?",
                         (node_name, section_id))
            conn.executemany(
                "INSERT INTO NodeResourceLinks(node_name, section_id, position, target) VALUES (?, ?, ?, ?)",
                [(node_name, section_id, i, target) for i, target in enumerate(cleaned)])


def live_sections(rows):
    """The draft rows that survive a save: everything not marked for removal."""
    return [row for row in rows if not row.get("deleted")]


@database.atomic
def save_sections(rows):
    """Save the ordered section draft. Removed sections take their links along."""
    validate_sections(rows)
    rows = live_sections(rows)
    ids = [row.get("id") for row in rows]
    with database.get_connection() as conn:
        current = {row[0] for row in conn.execute("SELECT id FROM ResourceSections")}
        for section_id in current - set(ids):
            conn.execute("DELETE FROM NodeResourceLinks WHERE section_id=?", (section_id,))
            conn.execute("DELETE FROM ResourceSections WHERE id=?", (section_id,))
        saved = []
        for i, row in enumerate(rows):
            saved_row = {"id": row.get("id") or uuid.uuid4().hex,
                         "name": (row.get("name") or "").strip(),
                         "kind": row.get("kind") if row.get("kind") in KINDS else "mixed",
                         "root_path": (row.get("root_path") or "").strip(),
                         "position": i}
            conn.execute(
                "INSERT INTO ResourceSections(id, name, kind, root_path, position) "
                "VALUES (:id, :name, :kind, :root_path, :position) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, kind=excluded.kind, root_path=excluded.root_path, "
                "position=excluded.position", saved_row)
            saved.append(saved_row)
    return saved


def validate_sections(rows):
    """Reject invalid edits before an unrelated Settings save writes anything."""
    rows = live_sections(rows)
    if len(rows) > MAX_SECTIONS:
        raise ValueError(f"Keep at most {MAX_SECTIONS} resources.")
    ids = [row.get("id") for row in rows]
    names = [(row.get("name") or "").strip() for row in rows]
    if (len(set(ids)) != len(ids) or any(not name for name in names) or
            len(set(name.casefold() for name in names)) != len(names)):
        raise ValueError("Each resource needs its own name.")
