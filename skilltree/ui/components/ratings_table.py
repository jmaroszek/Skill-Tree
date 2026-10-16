"""The 1-10 rating definition tables: read-only rows for a popup, and editable rows."""
from dash import html
from skilltree.ui import tokens


# The three ratings-editor textareas hand-painted a DARKLY imitation,
# written out verbatim three times. One definition instead.
_RATING_TEXTAREA_STYLE = {
    "width": "100%", "height": "72px", "resize": "vertical",
    "backgroundColor": tokens.BG_RAISED, "color": tokens.TEXT_PRIMARY,
    "border": f"1px solid {tokens.BORDER_PANEL}",
    "borderRadius": tokens.RADIUS_SM, "padding": "4px",
    "fontSize": tokens.FS_CAP,
}


_cell_style = {
    "padding": "6px 8px",
    "verticalAlign": "top",
    "borderBottom": f"1px solid {tokens.BORDER_SUBTLE}",
    "lineHeight": "1.4",
}


HEADER_CELL_STYLE = {
    **_cell_style,
    "fontWeight": "700",
    "backgroundColor": tokens.BG_RAISED,
    "borderBottom": f"2px solid {tokens.BORDER_PANEL}",
    "position": "sticky",
    "top": "0",
}


def _ratings_cell_children(text):
    """Render a definition string with its leading keyword (up to the first
    colon) bolded for quick scanning."""
    head, sep, tail = text.partition(':')
    if not sep:
        return text
    return [html.Strong(head + sep), tail]


def build_popup_table_rows(defs):
    """Build the ratings popup table rows from a list of definition dicts."""
    return [
        html.Tr([
            html.Td(str(d['rating']), style={
                **_cell_style, "fontWeight": "700", "color": tokens.TEXT_SOFT,
                "backgroundColor": tokens.BG_CANVAS if i % 2 == 0 else "transparent",
            }),
            html.Td(_ratings_cell_children(d['value']), style={
                **_cell_style, "backgroundColor": tokens.BG_CANVAS if i % 2 == 0 else "transparent",
            }),
            html.Td(_ratings_cell_children(d['interest']), style={
                **_cell_style, "backgroundColor": tokens.BG_CANVAS if i % 2 == 0 else "transparent",
            }),
            html.Td(_ratings_cell_children(d['effort']), style={
                **_cell_style, "backgroundColor": tokens.BG_CANVAS if i % 2 == 0 else "transparent",
            }),
        ])
        for i, d in enumerate(defs)
    ]


def build_editor_table(defs, id_prefix="ratings-edit"):
    """Build the full editor table (with header) for a ratings editor modal.

    `id_prefix` namespaces the textarea pattern-matching ids so the estimation
    and reflection editors don't collide (e.g. "ratings-edit" vs
    "reflection-ratings-edit")."""
    return html.Table([
        html.Thead(html.Tr([
            html.Th("#", style={**HEADER_CELL_STYLE, "width": "36px"}),
            html.Th("Value", style=HEADER_CELL_STYLE),
            html.Th("Interest", style=HEADER_CELL_STYLE),
            html.Th("Effort", style=HEADER_CELL_STYLE),
        ])),
        html.Tbody(build_editor_rows(defs, id_prefix)),
    ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": tokens.FS_CAP, "color": tokens.TEXT_PRIMARY})


def build_editor_rows(defs, id_prefix="ratings-edit"):
    """Build the editor modal rows (textareas) from a list of definition dicts."""
    from dash import dcc
    rows = []
    for d in defs:
        i = d['rating'] - 1
        rows.append(html.Tr([
            html.Td(str(d['rating']), style={
                **_cell_style, "fontWeight": "700", "color": tokens.TEXT_SOFT,
                "width": "36px", "textAlign": "center",
            }),
            html.Td(dcc.Textarea(
                id={"type": f"{id_prefix}-value", "index": i},
                value=d['value'],
                style=_RATING_TEXTAREA_STYLE,
            ), style=_cell_style),
            html.Td(dcc.Textarea(
                id={"type": f"{id_prefix}-interest", "index": i},
                value=d['interest'],
                style=_RATING_TEXTAREA_STYLE,
            ), style=_cell_style),
            html.Td(dcc.Textarea(
                id={"type": f"{id_prefix}-effort", "index": i},
                value=d['effort'],
                style=_RATING_TEXTAREA_STYLE,
            ), style=_cell_style),
        ]))
    return rows
