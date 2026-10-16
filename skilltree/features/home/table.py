"""The Home tab's Next table and Now section."""
import json

from dash import html

from skilltree.domain.models import EDGE_HELPS, EDGE_NEEDS_HARD, STATUS_DONE
from skilltree.domain.scoring import explain_score
from skilltree.store import database
from skilltree.store.resources import get_sections
from skilltree.store.settings import BADGE_PALETTE, ConfigManager
from skilltree.ui import tokens
from skilltree.ui.components.menus import node_menu_attributes

_MONO_FONT = tokens.FONT_MONO


# The Next priority bar: a tinted fill with a solid edge at its end. The edge
# marks the exact value; the tint keeps the type colours from outweighing the
# length (solid orange read as more urgent than solid blue at the same score).
BAR_FILL_PERCENT = 70


# The name column is as wide as the longest visible name, within these bounds.
# The bar takes whatever the table has left, so a short list of names gives the
# width to the bar and the rest of the row never moves.
NAME_MIN_WIDTH = 200


NAME_MAX_WIDTH = 340


# The rank column is 32px; the rows' 12px side padding is taken from the first
# track when the rows share the list's grid, so the track is wider by that much.
RANK_TRACK_WIDTH = 44


BAR_MIN_WIDTH = 240


# Space between the row's columns, then between the time, the V/I/E chart and the
# link dots inside the last one. The first is looser so the bar's end edge does
# not crowd the time.
BAR_ROW_GAP = 24


META_GAP = 38


def _suggestion_micro_bar(val, label):
    """One bar of the V/I/E micro-chart (6×22 track with bottom-anchored fill, native title tooltip)."""
    try:
        raw = float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        raw = 0.0
    pct = max(0.0, min(100.0, (raw / 10.0) * 100.0))
    display_val = int(raw) if raw == int(raw) else round(raw, 1)
    return html.Span(
        html.Span(style={
            "position": "absolute", "left": 0, "right": 0, "bottom": 0,
            "height": f"{pct}%", "background": tokens.TEXT_SOFT, "borderRadius": "1px",
        }),
        title=f"{label}: {display_val}",
        style={
            "position": "relative", "width": "6px", "height": "22px",
            "background": "rgba(255,255,255,0.06)", "borderRadius": "1px",
            "overflow": "hidden", "display": "inline-block", "cursor": "default",
        },
    )


def _relations_lookup(manager):
    """Return name -> JSON of what a node supports and has synergy with.

    Backs the Home description panel with the node's direct neighbours only; the
    whole downstream reach is Explain Priority's job. Each list holds [name, type
    colour, kind, done] rows, best first, so the panel can show the top few and
    count the rest:

    - `supports`: the nodes, Goals included, that list it as a hard or soft
      prerequisite.
    - `synergy`: its Helps partners, in either direction.

    Prerequisites are left out: a node with an unfinished one is Blocked and never
    reaches the Home lists. Ordering uses each neighbour's contribution to the
    node's score; neighbours that add nothing, such as Done ones, come last.
    Scoring runs once per requested name, over one read of the graph.
    """
    nodes = manager.get_all_nodes()
    by_name = {n.name: n for n in nodes}
    edges = manager.get_edges()
    hypers = ConfigManager.get_hyperparams()
    hypers['context_weights'] = ConfigManager.get_context_weights()
    priority_goals = ConfigManager.get_priority_goals()

    supports, synergy = {}, {}
    for e in edges:
        src, tgt, typ = e['source'], e['target'], e['type']
        if typ == EDGE_HELPS:
            synergy.setdefault(src, set()).add(tgt)
            synergy.setdefault(tgt, set()).add(src)
        else:
            kind = 'hard' if typ == EDGE_NEEDS_HARD else 'soft'
            # A hard edge outranks a soft one on the same pair.
            if supports.setdefault(src, {}).get(tgt) != 'hard':
                supports[src][tgt] = kind

    def row(name, kind=''):
        node = by_name[name]
        return [name, BADGE_PALETTE.get(node.type, ('#6c757d',))[0],  # literal: palette fallback
                kind, node.status == STATUS_DONE]

    def visible(name):
        node = by_name.get(name)
        return node is not None and not getattr(node, 'dormant', False)

    def lookup(name):
        node = by_name.get(name)
        if node is None:
            return json.dumps({})
        weight = {}
        if node.type != 'Goal':
            explained = explain_score(name, nodes, edges, hypers,
                                      priority_goals=priority_goals)
            weight = {c['name']: c['contribution']
                      for c in (explained or {}).get('contributors', [])}

        def ranked(names):
            return sorted(names, key=lambda n: (-weight.get(n, 0.0), n.lower()))

        direct = {n: kind for n, kind in supports.get(name, {}).items()
                  if n != name and visible(n)}
        partners = [n for n in synergy.get(name, ()) if n != name and visible(n)]
        buckets = {
            'supports': [row(n, direct[n]) for n in ranked(direct)],
            'synergy': [row(n) for n in ranked(partners)],
        }
        return json.dumps({k: v for k, v in buckets.items() if v})
    return lookup


def _suggestion_dot(on, label, fill_color):
    """One link-presence indicator dot (filled when a link is set, hollow otherwise)."""
    border_color = fill_color if on else tokens.TEXT_DIM
    return html.Span(
        title=label,
        style={
            "width": "8px", "height": "8px", "borderRadius": "8px",
            "background": fill_color if on else "transparent",
            "border": f"1.2px solid {border_color}",
            "display": "inline-block",
        },
    )


@database.snapshot_read
def format_suggestions_table(suggs, manager, selected_node_id=None, pinned_steps=None):
    """Render the top-scored nodes as bar-chart rows with normalized priority scores (0-100).

    Each row encodes:
      - rank (two-digit monospace label, leftmost)
      - name + context line
      - priority bar (color = type, or the Unblocking accent for a step; length = priority/maxPriority)
      - time + V/I/E micro-chart + Obsidian/Drive/Website link dots

    The number is the node's own normalized priority, against the same base
    the Explain modal and the subtask tables use, so a node reads the same
    everywhere. It descends down the list because suggestion variety is part
    of the score itself rather than a re-ordering applied afterwards. Bar
    *length* stays relative to the longest row on screen, so the column still
    fills its width when a filter leaves the top row below 100.

    `pinned_steps` maps a node name to the Now target it unblocks. Those rows
    are the one exception to the descent: they sit on top whatever they score,
    carry a `↳` in place of a rank so the ranking below still reads 1..N, and
    name their target in the context line, dropping whichever part of their own
    context the target has already implied. They keep their true number rather
    than a flattering one — a step is often worse than what you'd otherwise do,
    and the honest figure is what makes that visible — and the Unblocking accent
    marks them as a group.

    Every row — step or not — stays a `suggestion-row` with the
    `suggestion-bar-row` class. next_selection.js styles them as a positional
    ALL-list through that class, so a step must not be rendered as some other
    kind of element.
    """
    if not suggs:
        nodes = manager.get_all_nodes()
        if not nodes:
            return html.P("Your graph is empty. Add a goal with the node editor, the "
                          "first icon at the top left, and Skill Tree will start "
                          "suggesting what to work on.", className="text-muted")
        # Goals and Milestones are where the work leads, never suggestions.
        if not any(n.type not in ("Goal", "Milestone") and n.status != STATUS_DONE
                   for n in nodes):
            return html.P("Nothing to suggest yet. Add things to learn or do, and "
                          "connect your goals to them with Needs.", className="text-muted")
        return html.P("No suggestions found based on current filters and graph state.", className="text-muted")

    max_score = manager.get_priority_normalizer()

    def normalize(score):
        if max_score <= 0:
            return 0.0
        return round((score / max_score) * 100, 1)

    normalized_scores = [normalize(getattr(s, 'priority_score', 0)) for s in suggs]
    max_priority = max(normalized_scores) if normalized_scores else 0

    # Bar colors come from the static BADGE_PALETTE (in config.py), NOT the
    # user-configurable canvas Type Colors. See the BADGE_PALETTE comment for
    # the rationale — short version: canvas needs vivid hues, bars need a
    # quieter register, and the two are decoupled by design.
    pinned_steps = pinned_steps or {}
    step_color = BADGE_PALETTE['Unblocking'][0]
    # One target per blocked Now node, repeated across its steps — resolve each
    # once so the context trimming below can compare against it.
    step_targets = {name: manager.get_node(name)
                    for name in set(pinned_steps.values())}

    rows = []
    rank = 0
    resource_sections = get_sections()
    relations = _relations_lookup(manager)
    for s in suggs:
        is_selected = (s.name == selected_node_id)
        step_target = pinned_steps.get(s.name)
        if step_target is None:
            rank += 1

        eff_time = manager.get_effective_time(s.name)

        priority_int = round(normalize(getattr(s, 'priority_score', 0)))
        if max_priority > 0:
            bar_width_pct = max(8.0, (priority_int / max_priority) * 100.0)
        else:
            bar_width_pct = 8.0
        bar_color = step_color if step_target else BADGE_PALETTE.get(s.type, ('#6c757d', '#fff'))[0]  # literal: palette fallback

        # Column 1 — rank, or a turnstile for a pinned step so the ranking
        # below still reads 1, 2, 3 rather than starting partway down.
        rank_col = html.Div(
            "↳" if step_target else str(rank),
            style={
                "fontFamily": _MONO_FONT, "fontSize": tokens.FS_XL,
                "color": step_color if step_target else tokens.TEXT_DIM,
                "textAlign": "center",
                "lineHeight": "1",
            },
        )

        # Column 2 — name + context line
        ctx_text = str(s.context) if s.context else ""
        sub_text = str(s.subcontext) if s.subcontext else ""
        if ctx_text and sub_text:
            ctx_children = [html.Span(ctx_text), html.Span("·", style={"opacity": 0.5, "padding": "0 4px"}), html.Span(sub_text)]
        elif ctx_text:
            ctx_children = [html.Span(ctx_text)]
        elif sub_text:
            ctx_children = [html.Span(sub_text)]
        else:
            ctx_children = []

        # A step says what it is for before it says where it lives, because the
        # column ellipsizes and the target is the reason the row is here at all.
        # Naming the target usually says the context too — a hard prerequisite
        # normally sits beside the thing it unblocks — so drop whichever half
        # the target has already given away and let the rest keep its width.
        if step_target:
            target = step_targets.get(step_target)
            if target is not None and target.context == s.context:
                ctx_children = ([html.Span(sub_text)]
                                if sub_text and target.subcontext != s.subcontext
                                else [])
            lead = [html.Span("toward ", style={"opacity": 0.7}),
                    html.Span(step_target, style={"fontWeight": 600})]
            if ctx_children:
                lead.append(html.Span("·", style={"opacity": 0.5, "padding": "0 4px"}))
            ctx_children = [html.Span(lead, style={"color": step_color})] + ctx_children

        name_col = html.Div([
            html.Div(
                html.Span(
                    s.name,
                    style={
                        "fontSize": tokens.FS_MD, "color": tokens.TEXT_PRIMARY,
                        "lineHeight": "1.35",
                    },
                ),
                style={"minWidth": 0, "overflow": "hidden",
                       "whiteSpace": "nowrap", "textOverflow": "ellipsis",
                       "lineHeight": "1.35", "marginBottom": "1px"},
            ),
            html.Div(ctx_children, style={
                "fontSize": tokens.FS_SM, "color": tokens.TEXT_DIM,
                "fontFamily": _MONO_FONT,
                "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis",
                "lineHeight": "1.35",
            }),
        ], style={"minWidth": f"{NAME_MIN_WIDTH}px", "overflow": "hidden"})

        # Column 3 — priority bar
        bar_fill = html.Div(
            html.Span(
                str(priority_int),
                style={
                    "fontFamily": _MONO_FONT, "fontSize": tokens.FS_BASE,
                    "fontWeight": "600", "color": "#fff",  # literal: on a coloured tile
                    "textShadow": "0 1px 1px rgba(0,0,0,0.5)",
                },
            ),
            style={
                "width": f"{bar_width_pct}%", "height": "100%",
                "background": f"color-mix(in srgb, {bar_color} {BAR_FILL_PERCENT}%, transparent)",
                "boxShadow": f"inset -3px 0 0 {bar_color}", "borderRadius": "3px",
                "display": "flex", "alignItems": "center",
                "justifyContent": "flex-end", "paddingRight": "10px",
            },
        )
        bar_col = html.Div(
            bar_fill,
            style={
                "position": "relative", "height": "26px",
                "background": "rgba(255,255,255,0.03)",
                "borderRadius": "3px", "overflow": "hidden",
            },
        )

        # Column 4 — time + V/I/E + R/O/D
        # force_one_decimal keeps the column aligned (1.0w / 1.5w / 11.4h
        # all render with the same decimal width).
        time_label = html.Span(
            ConfigManager.format_time_friendly(eff_time, force_one_decimal=True),
            style={"color": tokens.TEXT_SOFT, "minWidth": "52px", "textAlign": "right",
                   "fontSize": tokens.FS_LG},
        )

        v_val = s.value if s.value is not None else 0
        i_val = getattr(s, 'interest', None) if getattr(s, 'interest', None) is not None else 0
        e_val = s.difficulty if s.difficulty is not None else 0

        micro_chart = html.Span([
            _suggestion_micro_bar(v_val, "Value"),
            _suggestion_micro_bar(i_val, "Interest"),
            _suggestion_micro_bar(e_val, "Effort"),
        ], style={
            "display": "inline-flex", "alignItems": "flex-end",
            "gap": "3px", "height": "22px",
        })

        dots = html.Span([
            _suggestion_dot(bool(s.resource_links.get(section['id'])),
                            section['name'], tokens.TEXT_PRIMARY)
            for section in resource_sections
        ], style={"display": "flex", "gap": "6px", "alignItems": "center"})

        meta_col = html.Div([time_label, micro_chart, dots], style={
            "display": "flex", "alignItems": "center", "gap": f"{META_GAP}px",
            "fontFamily": _MONO_FONT, "fontSize": tokens.FS_XS,
        })

        row_style = {
            "display": "grid",
            "gridTemplateColumns": "subgrid", "gridColumn": "1 / -1",
            "alignItems": "center",
            "gap": f"{BAR_ROW_GAP}px",
            "padding": "9px 12px",
            "borderBottom": f"1px solid {tokens.BORDER_SUBTLE}",
        }
        if is_selected:
            row_style["backgroundColor"] = tokens.BG_RAISED

        rows.append(html.Div(
            [rank_col, name_col, bar_col, meta_col],
            id={"type": "suggestion-row", "index": s.name},
            className="suggestion-bar-row",
            role="button", tabIndex=0,
            style=row_style,
            **{
                "data-description": (s.description or "").strip(),
                "data-relations": relations(s.name),
                **node_menu_attributes(s),
            },  # type: ignore[reportArgumentType]
        ))

    # One grid for the whole list, so every row shares the same columns: the
    # rows are subgrids of it.
    bar_list = html.Div(rows, style={
        "flex": "1", "minWidth": "0", "display": "grid",
        "gridTemplateColumns": (f"{RANK_TRACK_WIDTH}px fit-content({NAME_MAX_WIDTH}px) "
                                f"minmax({BAR_MIN_WIDTH}px, 1fr) auto"),
        "columnGap": f"{BAR_ROW_GAP}px",
    })

    return [bar_list]


@database.snapshot_read
def format_now_nodes_section(now_nodes, cap, manager, selected_node_id=None):
    """Render the 'Now' section for the Home tab as a row of rich cards.

    Each Now node gets a wide horizontal card: a left accent bar in the node's
    type color, then the name, the expected time, and the context/subcontext
    line. Cards sit in a flex row and keep the user's drag order.

    A Now node that can't be started yet contributes its next actionable
    prerequisites to the top of the Next table instead of anything here — see
    GraphManager.get_unblocking_steps.

    When there are no Now nodes the section is suppressed entirely —
    return [] so the Next heading sits at the top of the tab.

    The `cap` argument is accepted for forward-compatibility but no longer
    surfaced — the cap is enforced in the toggle/context-menu callbacks.
    """
    if not now_nodes:
        return []

    heading = html.Div([
        html.H6("Now", className="text-muted mb-0", style=tokens.SECTION_TITLE_STYLE),
    ], className="d-flex align-items-center", style={"gap": tokens.SPACE_BLOCK, "marginBottom": "0.75rem"})

    cards = []
    relations = _relations_lookup(manager)
    for n in now_nodes:
        is_selected = (n.name == selected_node_id)
        eff_time = manager.get_effective_time(n.name)
        accent_color = BADGE_PALETTE.get(n.type, ('#6c757d', '#fff'))[0]  # literal: palette fallback

        # --- Context / subcontext line ---
        ctx_text = str(n.context) if n.context else ""
        sub_text = str(n.subcontext) if n.subcontext else ""
        if ctx_text and sub_text:
            ctx_children = [
                html.Span(ctx_text),
                html.Span("·", style={"opacity": 0.5, "padding": "0 4px"}),
                html.Span(sub_text),
            ]
        elif ctx_text:
            ctx_children = [html.Span(ctx_text)]
        elif sub_text:
            ctx_children = [html.Span(sub_text)]
        else:
            ctx_children = []

        # --- Time estimate ---
        time_label = html.Span(
            ConfigManager.format_time_friendly(eff_time, force_one_decimal=True),
            style={"color": tokens.TEXT_SOFT, "fontSize": tokens.FS_ROW_META,
                   "fontFamily": _MONO_FONT, "fontWeight": "500",
                   "flexShrink": "0"},
        )

        # --- Top row: name + time ---
        top_row = html.Div([
            html.Div(
                html.Span(
                    n.name,
                    style={"fontSize": tokens.FS_ROW_TITLE, "color": tokens.TEXT_PRIMARY,
                           "fontWeight": "700", "lineHeight": "1.3"},
                ),
                style={"minWidth": 0, "overflow": "hidden", "whiteSpace": "nowrap",
                       "textOverflow": "ellipsis", "flex": "1"},
            ),
            time_label,
        ], style={
            "display": "flex", "alignItems": "baseline", "gap": tokens.SPACE_BLOCK,
            "marginBottom": "4px",
        })

        # --- Context subtitle ---
        ctx_line = html.Div(ctx_children, style={
            "fontSize": tokens.FS_BASE, "color": tokens.TEXT_DIM, "fontFamily": _MONO_FONT,
            "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis",
            "lineHeight": "1.35",
            "minHeight": "17px",
        }) if ctx_children else html.Div(style={"minHeight": "17px"})

        # --- Card body (right of the accent bar) ---
        card_body = html.Div(
            [top_row, ctx_line],
            style={"flex": "1", "minWidth": 0, "overflow": "hidden"},
        )

        # --- Accent bar (left edge) ---
        accent_bar = html.Div(style={
            "width": "4px",
            "borderRadius": "2px",
            "backgroundColor": accent_color,
            "alignSelf": "stretch",
            "flexShrink": "0",
        })

        # --- Card container ---
        card_style = {
            "display": "flex",
            "gap": "14px",
            "padding": "16px 20px",
            "borderRadius": "6px",
            "backgroundColor": tokens.BG_RAISED if is_selected else tokens.BG_PANEL,
            "border": f"2px solid {tokens.ACCENT}" if is_selected else f"1px solid {tokens.BORDER_PANEL}",
            "cursor": "pointer",
            "transition": "background-color 0.2s, border-color 0.2s",
            "flex": "0 0 310px",
            "width": "310px",
        }

        cards.append(html.Div(
            [accent_bar, card_body],
            id={"type": "now-row", "index": n.name},
            className="now-card",
            role="button", tabIndex=0,
            style=card_style,
            **{
                **node_menu_attributes(n),
                "data-description": (n.description or "").strip(),
                "data-relations": relations(n.name),
                "data-node-name": n.name,
            },  # type: ignore[reportArgumentType]
        ))

    cards_row = html.Div(cards, id="now-cards-container", style={
        "display": "flex",
        "gap": "1rem",
        "marginBottom": "32px",
    })

    return [heading, cards_row]
