"""The Contexts editor in Settings: its rows and the chips that say what
changed, the editor's state as the user types, and its callbacks."""
import hashlib
import json

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, html

from skilltree.ui.kit import hint
from skilltree.domain import contexts as context_rules
from skilltree.store import settings

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
        html.Button(html.I(className="bi bi-x"),
                   id={"type": "ctx-sub-remove", "index": sub["sid"]},
                   **hint("Remove subcontext", label=True),
                   type="button", className="btn btn-primary ctx-chip-remove"),
    ], className="ctx-chip",
        key=sub["sid"], **{"data-ctx-sub": sub["sid"]},
        **({"data-hint": error or _plural(count, "node")} if error or count else {}))


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
        html.Button(html.I(className="bi bi-arrow-counterclockwise"),
                   id={"type": "ctx-row-undelete", "index": row["rid"]},
                   **hint("Keep this context", label=True),
                   type="button", className="btn btn-primary ctx-row-btn"),
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
        chips.append(html.Button(
            [html.I(className="bi bi-plus"), " add"],
            id={"type": "ctx-sub-add", "index": rid},
            type="button", className="btn btn-primary ctx-chip-add", **hint("Add a subcontext")))

        out.append(html.Div([
            html.Span(html.I(className="bi bi-list"),
                      className="ctx-drag-handle"),
            # The wrapper carries the node count: hover tips go on plain elements.
            html.Div(dbc.Input(
                id={"type": "ctx-row-name", "index": rid},
                type="text", value=row.get("name", ""), placeholder="Context",
                className="ctx-row-name", invalid=bool(errors.get(f"row:{rid}")),
                autoFocus=_is_fresh(row),
            ), className="ctx-row-name-wrap",
                **({"data-hint": _plural(count, "node")} if count else {})),
            html.Div(chips, className="ctx-chips", **{"data-ctx-subs": rid}),
            dbc.Input(
                id={"type": "ctx-row-weight", "index": rid},
                type="number", min=0, max=10, step="any",
                value=float(row.get("weight", 1.0)),
                className="ctx-row-weight",
            ),
            html.Button(html.I(className="bi bi-x-lg"),
                       id={"type": "ctx-row-delete", "index": rid},
                       **hint("Remove context", label=True),
                       type="button", className="btn btn-primary ctx-row-btn ctx-row-btn-danger"),
        ], className="ctx-row", key=rid, **{"data-ctx-row": rid}))

    # The "Add context" button is not here: a callback Input needs its
    # component in the initial layout, so it sits in settings_layout just
    # below this container.
    return html.Div(html.Div(out, className="ctx-row-list"),
                    id="ctx-editor-rows", key=_structure_key(rows))


def fold_live_values(rows, name_vals, name_ids, weight_vals, weight_ids,
                      sub_vals, sub_ids):
    """Copy what is currently typed in the editor back into the stored rows.

    The name, priority and chip inputs are deliberately not callback Inputs —
    re-rendering the container on every keystroke would take the caret with
    it. They are read here instead, just before a structural edit (add,
    remove, drag) rebuilds the rows, and again on save.
    """
    by_rid_name = {i["index"]: v for i, v in zip(name_ids or [], name_vals or [])}
    by_rid_weight = {i["index"]: v for i, v in zip(weight_ids or [], weight_vals or [])}
    by_sid = {i["index"]: v for i, v in zip(sub_ids or [], sub_vals or [])}

    folded = []
    for row in rows or []:
        rid = row["rid"]
        name = by_rid_name.get(rid, row.get("name"))
        weight = by_rid_weight.get(rid, row.get("weight"))
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = context_rules.DEFAULT_CONTEXT_WEIGHT
        subs = [{**s, "name": by_sid.get(s["sid"], s.get("name"))}
                for s in row.get("subs", [])]
        folded.append({**row, "name": name if name is not None else "",
                       "weight": weight, "subs": subs})
    return folded


def editor_state(manager, rows=None):
    """Build the Contexts editor's store payload.

    Alongside the rows it carries the taxonomy they are diffed against and the
    node counts per context and per (context, subcontext) pair. Capturing
    those once, when the modal opens, is what lets the live summary and the
    validation run on every keystroke without touching the database. Saving
    re-reads the config rather than trusting this snapshot.
    """
    contexts = settings.CONTEXTS.get()
    subcontexts = settings.SUBCONTEXTS.get()
    ctx_counts, pair_counts = manager.count_nodes_by_context()
    if rows is None:
        rows = context_rules.taxonomy_to_rows(
            contexts, subcontexts, settings.CONTEXT_WEIGHTS.get())
    return {
        'rows': rows,
        'old': {'contexts': contexts, 'subcontexts': subcontexts},
        'counts': {
            'ctx': ctx_counts,
            # JSON has no tuple keys, so pairs travel as [ctx, sub, n] triples.
            'pair': [[c, s, n] for (c, s), n in pair_counts.items()],
        },
    }


def counts_from_state(state):
    """Unpack the store's node counts back into ({ctx: n}, {(ctx, sub): n})."""
    counts = (state or {}).get('counts') or {}
    pairs = {(row[0], row[1]): row[2] for row in counts.get('pair', [])
             if len(row) == 3}
    return counts.get('ctx', {}), pairs


def _remove_row(rows, rid):
    """Drop a row, or mark it removed when it has something to lose.

    A row that was never saved just disappears — there is nothing to undo. One
    that came from the config is kept, struck through, so the node count stays
    visible and the removal can be taken back before Save.
    """
    out = []
    for row in rows:
        if row["rid"] != rid:
            out.append(row)
        elif row.get("orig"):
            out.append({**row, "deleted": True})
    return out


def _clicked(triggered_value) -> bool:
    """True when a pattern-matched button was actually clicked.

    Re-rendering the row container mounts fresh buttons whose n_clicks is
    None, which fires the callback again; without this guard the first render
    after any edit would replay that edit.
    """
    return bool(triggered_value)


CTX_EDIT_STATES = (
    State('context-editor-store', 'data'),
    State({"type": "ctx-row-name", "index": ALL}, "value"),
    State({"type": "ctx-row-name", "index": ALL}, "id"),
    State({"type": "ctx-row-weight", "index": ALL}, "value"),
    State({"type": "ctx-row-weight", "index": ALL}, "id"),
    State({"type": "ctx-sub-name", "index": ALL}, "value"),
    State({"type": "ctx-sub-name", "index": ALL}, "id"),
)


def live_rows(state, name_vals, name_ids, weight_vals, weight_ids,
               sub_vals, sub_ids):
    """Rows from the store with whatever is currently typed folded in."""
    return fold_live_values((state or {}).get('rows', []),
                             name_vals, name_ids, weight_vals, weight_ids,
                             sub_vals, sub_ids)


def register_context_editor_callbacks(app, services):
    # --- Contexts editor -----------------------------------------------
    # The rows live in `context-editor-store`; the components below are only
    # how a click finds its row again. Text inputs are read as State rather
    # than driving Inputs, so typing never re-renders the container out from
    # under the caret. See context_rules.py for the row model.

    @app.callback(
        Output('setting-context-editor', 'children'),
        Input('context-editor-store', 'data'),
    )
    def render_context_editor(state):
        state = state or {}
        ctx_counts, pair_counts = counts_from_state(state)
        rows = state.get('rows', [])
        return build_context_editor_rows(
            rows, ctx_counts, pair_counts,
            context_rules.validate_rows(context_rules.normalize_rows(rows)))

    @app.callback(
        Output({"type": "ctx-row-name", "index": ALL}, "invalid"),
        Output({"type": "ctx-sub-name", "index": ALL}, "invalid"),
        Output('ctx-editor-summary', 'children'),
        Output('ctx-editor-summary', 'className'),
        Input({"type": "ctx-row-name", "index": ALL}, "value"),
        Input({"type": "ctx-sub-name", "index": ALL}, "value"),
        State('context-editor-store', 'data'),
        State({"type": "ctx-row-name", "index": ALL}, "id"),
        State({"type": "ctx-sub-name", "index": ALL}, "id"),
    )
    def validate_context_editor(name_vals, sub_vals, state, name_ids, sub_ids):
        """Flag problems and say what a save would do, without a re-render.

        Writing only `invalid` flags and one line of text leaves the inputs
        themselves in place, which is what lets this run on every keystroke.
        Everything it needs was captured in the store when the modal opened,
        so it costs no database read.
        """
        state = state or {}
        rows = fold_live_values(state.get('rows', []),
                                 name_vals, name_ids, [], [], sub_vals, sub_ids)
        rows = context_rules.normalize_rows(rows)
        errors = context_rules.validate_rows(rows)

        name_flags = [f"row:{i['index']}" in errors for i in name_ids or []]
        sub_flags = [f"sub:{i['index']}" in errors for i in sub_ids or []]

        if errors:
            first = next(iter(errors.values()))
            extra = len(errors) - 1
            text = first + (f" (+{extra} more)" if extra else "")
            return name_flags, sub_flags, text, "mt-1 ctx-summary-error"

        old = state.get('old') or {}
        ctx_counts, pair_counts = counts_from_state(state)
        plan = context_rules.plan_taxonomy_change(
            rows, old.get('contexts', []), old.get('subcontexts', {}))
        return (name_flags, sub_flags,
                context_rules.describe_plan(plan, ctx_counts, pair_counts),
                "mt-1")

    @app.callback(
        Output('context-editor-store', 'data', allow_duplicate=True),
        Input('btn-ctx-row-add', 'n_clicks'),
        Input({"type": "ctx-row-delete", "index": ALL}, "n_clicks"),
        Input({"type": "ctx-row-undelete", "index": ALL}, "n_clicks"),
        Input({"type": "ctx-sub-add", "index": ALL}, "n_clicks"),
        Input({"type": "ctx-sub-remove", "index": ALL}, "n_clicks"),
        Input('ctx-editor-drag-input', 'value'),
        *CTX_EDIT_STATES,
        prevent_initial_call=True,
    )
    def edit_context_rows(_add, _del, _undel, _sub_add, _sub_del, drag_value,
                          state,
                          name_vals, name_ids, weight_vals, weight_ids,
                          sub_vals, sub_ids):
        """Apply one structural edit to the rows and hand back a fresh store.

        Every branch folds the live text values in first, so an edit never
        discards a name the user typed but has not blurred.
        """
        trigger = ctx.triggered_id
        if trigger is None:
            return dash.no_update
        fired = ctx.triggered[0].get('value') if ctx.triggered else None
        rows = live_rows(state, name_vals, name_ids, weight_vals, weight_ids,
                          sub_vals, sub_ids)

        if trigger == 'btn-ctx-row-add':
            if not _clicked(fired):
                return dash.no_update
            rows.append({"rid": context_rules.next_row_id(rows), "orig": None,
                         "name": "", "subs": [],
                         "weight": context_rules.DEFAULT_CONTEXT_WEIGHT})

        elif trigger == 'ctx-editor-drag-input':
            if not drag_value:
                return dash.no_update
            try:
                rows = context_rules.apply_drag_order(rows, json.loads(drag_value))
            except (ValueError, TypeError):
                return dash.no_update

        elif isinstance(trigger, dict):
            if not _clicked(fired):
                return dash.no_update
            kind, index = trigger.get('type'), trigger.get('index')
            if kind == 'ctx-row-delete':
                rows = _remove_row(rows, index)
            elif kind == 'ctx-row-undelete':
                rows = [{**r, "deleted": False} if r["rid"] == index else r
                        for r in rows]
            elif kind == 'ctx-sub-add':
                sid = context_rules.next_sub_id(rows)
                blank = {"sid": sid, "orig": None, "orig_ctx": None, "name": ""}
                rows = [{**r, "subs": list(r["subs"]) + [blank]}
                        if r["rid"] == index else r for r in rows]
            elif kind == 'ctx-sub-remove':
                rows = [{**r, "subs": [s for s in r["subs"] if s["sid"] != index]}
                        for r in rows]
            else:
                return dash.no_update
        else:
            return dash.no_update

        return {**(state or {}), 'rows': rows}
