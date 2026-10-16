"""Named node resources and one platform-neutral opener."""

from __future__ import annotations

import json
import ntpath
import os
import uuid

from skilltree.store import database
from skilltree.runtime.opener import WEB_URL, absolute_path, link_scheme

MAX_SECTIONS = 5


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
            "SELECT id, name, root_path, position FROM ResourceSections ORDER BY position")]


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
    if not value or WEB_URL.match(value) or link_scheme(value):
        return value
    return store_path(value, section.get("root_path", ""))


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
                         "root_path": (row.get("root_path") or "").strip(),
                         "position": i}
            # The kind column is unused since vault files open in Obsidian
            # on their own; it waits for the next schema change to go.
            conn.execute(
                "INSERT INTO ResourceSections(id, name, kind, root_path, position) "
                "VALUES (:id, :name, 'mixed', :root_path, :position) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, root_path=excluded.root_path, "
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
