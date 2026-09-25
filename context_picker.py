"""Shared context/subcontext picker shells and Dash value bridges.

The visible menus are rendered by ``assets/context_picker.js``.  The existing
Dash controls stay mounted but hidden, preserving every callback's established
``value`` and ``options`` contract while the custom picker supplies the
combined interaction.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from dash import Input, Output, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc

from config import ConfigManager, sort_contexts, sort_subcontexts


_PICKERS = (
    ("node-context-picker", "node-context", "node-subcontext", "single"),
    ("filter-context-picker", "filter-context", "filter-subcontext", "multi"),
    (
        "hub-history-context-picker",
        "hub-history-filter-context",
        "hub-history-filter-subcontext",
        "multi",
    ),
)


def build_context_taxonomy() -> list[dict[str, Any]]:
    """Return the configured hierarchy in the user's dropdown sort order."""
    subcontexts = ConfigManager.get_subcontexts()
    context_sort_mode = ConfigManager.get_context_sort_mode()
    subcontext_sort_mode = ConfigManager.get_subcontext_sort_mode()
    return [
        {
            "context": context,
            "subcontexts": sort_subcontexts(
                subcontexts.get(context, []), subcontext_sort_mode
            ),
        }
        for context in sort_contexts(
            ConfigManager.get_contexts(), context_sort_mode
        )
    ]


def build_context_picker_support() -> list[Any]:
    """Global state and an unclipped portal shared by all visible pickers."""
    return [
        dcc.Store(id="context-taxonomy-store", data=build_context_taxonomy()),
        html.Div(id="context-picker-portal"),
    ]


def _initial_state(mode: str, context_value: Any, subcontext_value: Any) -> str:
    if mode == "multi":
        context_value = list(context_value or [])
        subcontext_value = list(subcontext_value or [])
    else:
        context_value = context_value or ""
        subcontext_value = subcontext_value or ""
    return json.dumps({
        "mode": mode,
        "taxonomy": build_context_taxonomy(),
        "context": context_value,
        "subcontext": subcontext_value,
    })


def _picker_shell(
    picker_id: str,
    mode: str,
    context_bridge: Any,
    subcontext_bridge: Any,
    context_value: Any,
    subcontext_value: Any,
    *,
    empty_label: str,
) -> Any:
    trigger_label = empty_label
    if mode == "single" and context_value:
        trigger_label = (
            f"{context_value} › {subcontext_value}"
            if subcontext_value else str(context_value)
        )
    # Multi-picker summaries need the taxonomy order, so the browser renders
    # them; until then an empty selection is the only state known here.
    is_placeholder = not context_value

    controls: list[Any] = [
        html.Button(
            html.Span(
                trigger_label,
                className="context-picker-value"
                + (" is-placeholder" if is_placeholder else ""),
            ),
            id=f"{picker_id}-trigger",
            type="button",
            className="form-select context-picker-trigger",
            **{
                "aria-expanded": "false",
                "aria-haspopup": "tree" if mode == "multi" else "listbox",
            },
        ),
    ]
    if mode == "multi":
        controls.append(html.Button(
            html.I(className="bi bi-x-lg", **{"aria-hidden": "true"}),
            id=f"{picker_id}-clear",
            type="button",
            className="context-picker-clear",
            hidden=not bool(context_value),
            title="Clear context filters",
            **{"aria-label": "Clear context filters"},
        ))

    return html.Div([
        html.Div(controls, className="context-picker-control"),
        context_bridge,
        subcontext_bridge,
        dcc.Input(
            id=f"{picker_id}-action",
            type="text",
            value="",
            className="context-picker-action",
        ),
        html.Div(
            _initial_state(mode, context_value, subcontext_value),
            id=f"{picker_id}-state",
            className="context-picker-state",
        ),
        html.Div(
            id=f"{picker_id}-announcement",
            className="visually-hidden",
            **{"aria-live": "polite"},
        ),
    ], id=picker_id, className=f"context-picker-root context-picker-{mode}", **{
        "data-context-picker-mode": mode,
        "data-empty-label": empty_label,
    })


def build_single_context_picker(
    picker_id: str,
    context_id: str,
    subcontext_id: str,
    *,
    context_options: Iterable[dict[str, Any]] = (),
    subcontext_options: Iterable[dict[str, Any]] = (),
    context_value: str | None = "",
    subcontext_value: str | None = "",
    empty_label: str = "Select context...",
) -> Any:
    """Build a one-path picker while retaining the two legacy select IDs."""
    context_bridge = dbc.Select(
        id=context_id,
        options=list(context_options),
        value=context_value,
        className="context-picker-bridge",
    )
    subcontext_bridge = dbc.Select(
        id=subcontext_id,
        options=list(subcontext_options),
        value=subcontext_value,
        className="context-picker-bridge",
    )
    return _picker_shell(
        picker_id,
        "single",
        context_bridge,
        subcontext_bridge,
        context_value,
        subcontext_value,
        empty_label=empty_label,
    )


def build_multi_context_picker(
    picker_id: str,
    context_id: str,
    subcontext_id: str,
    *,
    context_value: Iterable[str] | None = None,
    subcontext_value: Iterable[str] | None = None,
    empty_label: str = "All contexts",
) -> Any:
    """Build a hierarchical multi-picker over the legacy list values.

    The bridges are checklists rather than dropdowns: Dash's dropdown prunes
    any value missing from its current options, so a subcontext picked in a
    context that was not selected yet would be dropped before options caught
    up. A checklist only writes ``value`` on its own (hidden) clicks.
    """
    contexts = list(context_value or [])
    subcontexts = list(subcontext_value or [])
    context_bridge = dcc.Checklist(
        id=context_id,
        options=[],
        value=contexts,
        className="context-picker-bridge",
    )
    subcontext_bridge = dcc.Checklist(
        id=subcontext_id,
        options=[],
        value=subcontexts,
        className="context-picker-bridge",
    )
    return _picker_shell(
        picker_id,
        "multi",
        context_bridge,
        subcontext_bridge,
        contexts,
        subcontexts,
        empty_label=empty_label,
    )


def _state_mirror(mode: str) -> str:
    if mode == "multi":
        normalization = (
            "context: Array.isArray(contextValue) ? contextValue : [], "
            "subcontext: Array.isArray(subcontextValue) ? subcontextValue : []"
        )
    else:
        normalization = "context: contextValue || '', subcontext: subcontextValue || ''"
    return f"""
        function(taxonomy, contextValue, subcontextValue) {{
            return JSON.stringify({{
                mode: {json.dumps(mode)},
                taxonomy: taxonomy || [],
                {normalization}
            }});
        }}
    """


def register_context_picker_callbacks(app: Any) -> None:
    """Wire visible picker actions to the established Dash component values."""
    for picker_id, context_id, subcontext_id, mode in _PICKERS:
        app.clientside_callback(
            _state_mirror(mode),
            Output(f"{picker_id}-state", "children"),
            Input("context-taxonomy-store", "data"),
            Input(context_id, "value"),
            Input(subcontext_id, "value"),
        )

        app.clientside_callback(
            """
            function(rawAction) {
                const keep = window.dash_clientside.no_update;
                if (!rawAction) return [keep, keep];
                try {
                    const action = JSON.parse(rawAction);
                    return [action.context, action.subcontext];
                } catch (_error) {
                    return [keep, keep];
                }
            }
            """,
            Output(context_id, "value", allow_duplicate=True),
            Output(subcontext_id, "value", allow_duplicate=True),
            Input(f"{picker_id}-action", "value"),
            prevent_initial_call=True,
        )

    @app.callback(
        Output("context-taxonomy-store", "data"),
        Input("settings-save-status", "children"),
        Input("modal-migration", "is_open"),
        prevent_initial_call=True,
    )
    def refresh_context_taxonomy(settings_status: Any, migration_open: bool) -> Any:
        trigger_id = ctx.triggered_id
        # A context edit appends what it changed ("Settings saved — 1 rename").
        if (trigger_id == "settings-save-status"
                and not str(settings_status or "").startswith("Settings saved")):
            return no_update
        if trigger_id == "modal-migration" and migration_open:
            return no_update
        return build_context_taxonomy()
