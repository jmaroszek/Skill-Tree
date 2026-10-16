"""The Contexts editor in Settings: its rows, and the chips that say what
changed."""
import hashlib

import dash_bootstrap_components as dbc
from dash import html

# A chip input sized to its text; below this it reads as an empty box.
_MIN_CHIP_CHARS = 5


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _is_fresh(item):
    """A blank row or chip the user just added — it takes the focus."""
    return not item.get("orig") and not (item.get("name") or "").strip()


def _chip(sub, count=0, error=None):
    """One subcontext chip: grip, an input sized to its own text, and remove.

    The input is what makes a chip editable in place, and a drag cannot start
    from inside a text field, so the grip is the chip's drag handle.
    """
    name = sub.get("name") or ""
    width = f"{max(_MIN_CHIP_CHARS, len(name) + 1)}ch"
    return html.Div([
        html.Span(html.I(className="bi bi-list"),
                  className="ctx-chip-grip"),
        dbc.Input(
            id={"type": "ctx-sub-name", "index": sub["sid"]},
            type="text", value=name, placeholder="name",
            className="ctx-chip-input", style={"width": width},
            invalid=bool(error), autoFocus=_is_fresh(sub),
        ),
        dbc.Button(html.I(className="bi bi-x"),
                   id={"type": "ctx-sub-remove", "index": sub["sid"]},
                   title="Remove subcontext",
                   className="ctx-chip-remove"),
    ], className="ctx-chip",
        title=error or (_plural(count, "node") if count else None),
        key=sub["sid"], **{"data-ctx-sub": sub["sid"]})


def _deleted_row(row, count):
    """A removed context, held struck-through until Save so it can be undone."""
    stranded = (f"{_plural(count, 'node')} need a new home" if count
                else "no nodes affected")
    return html.Div([
        html.Span(html.I(className="bi bi-list"),
                  className="ctx-drag-handle ctx-drag-disabled"),
        html.Span(row.get("orig") or row.get("name") or "",
                  className="ctx-row-name-static ctx-row-removed"),
        html.Span(f"removed — {stranded}", className="ctx-row-note"),
        dbc.Button(html.I(className="bi bi-arrow-counterclockwise"),
                   id={"type": "ctx-row-undelete", "index": row["rid"]},
                   title="Keep this context",
                   className="ctx-row-btn"),
    ], className="ctx-row ctx-row-deleted", key=row["rid"],
        **{"data-ctx-row": row["rid"]})


def _structure_key(rows):
    """A React key that changes whenever rows or chips are added, removed or
    reordered.

    SortableJS moves DOM nodes itself, behind React's back. If React then
    reconciled the next render against those moved nodes it would patch the
    wrong ones. Changing the key on
    every structural change remounts the editor instead, so React never
    reconciles against a DOM that SortableJS rearranged. Typing does not
    re-render, so this never costs the caret.
    """
    shape = "|".join(
        f"{r['rid']}{'-' if r.get('deleted') else ''}:"
        + ",".join(s["sid"] for s in r.get("subs", []))
        for r in rows or [])
    return hashlib.md5(shape.encode("utf-8")).hexdigest()[:12]


def build_context_editor_rows(rows, ctx_counts=None, pair_counts=None, errors=None):
    """Build the Contexts tab's row editor.

    One row per context: drag handle, name, subcontext chips, its priority,
    and remove. How many nodes sit in a context or subcontext today is its
    hover title (on the name or chip) rather than a column. Counts are looked up by the names the
    nodes currently carry (each row's and chip's origin), so a pending rename
    does not zero them out.

    Rows keep their identity in the store rather than in these components —
    the ids here are only how a click finds its row again.
    """
    ctx_counts = ctx_counts or {}
    pair_counts = pair_counts or {}
    errors = errors or {}

    out = []
    for row in rows or []:
        rid = row["rid"]
        count = ctx_counts.get(row.get("orig") or row.get("name"), 0)
        if row.get("deleted"):
            out.append(_deleted_row(row, count))
            continue

        chips = [
            _chip(sub,
                  pair_counts.get((sub.get("orig_ctx"), sub.get("orig")), 0),
                  errors.get(f"sub:{sub['sid']}"))
            for sub in row.get("subs", [])
        ]
        chips.append(dbc.Button(
            [html.I(className="bi bi-plus"), " add"],
            id={"type": "ctx-sub-add", "index": rid},
            title="Add a subcontext", className="ctx-chip-add"))

        out.append(html.Div([
            html.Span(html.I(className="bi bi-list"),
                      className="ctx-drag-handle"),
            # dbc.Input takes no title, so a wrapper carries the node count.
            html.Div(dbc.Input(
                id={"type": "ctx-row-name", "index": rid},
                type="text", value=row.get("name", ""), placeholder="Context",
                className="ctx-row-name", invalid=bool(errors.get(f"row:{rid}")),
                autoFocus=_is_fresh(row),
            ), className="ctx-row-name-wrap",
                title=_plural(count, "node") if count else None),
            html.Div(chips, className="ctx-chips", **{"data-ctx-subs": rid}),
            dbc.Input(
                id={"type": "ctx-row-weight", "index": rid},
                type="number", min=0, max=10, step="any",
                value=float(row.get("weight", 1.0)),
                className="ctx-row-weight",
            ),
            dbc.Button(html.I(className="bi bi-x-lg"),
                       id={"type": "ctx-row-delete", "index": rid},
                       title="Remove context",
                       className="ctx-row-btn ctx-row-btn-danger"),
        ], className="ctx-row", key=rid, **{"data-ctx-row": rid}))

    # The "Add context" button is not here: a callback Input needs its
    # component in the initial layout, so it sits in settings_layout just
    # below this container.
    return html.Div(html.Div(out, className="ctx-row-list"),
                    id="ctx-editor-rows", key=_structure_key(rows))
