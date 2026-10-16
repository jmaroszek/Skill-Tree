"""Canvas view preparation, independent of mutation routing and callback registration."""
import dash
from skilltree.ui import payloads as bridge_payloads
from skilltree.store.settings import ConfigManager, SUPPORTED_NODE_TYPES, sort_contexts
from skilltree.ui.callback_helpers import node_options
from skilltree.engine.response import CoreResponse
from skilltree.ui.canvas.registry import CANVASES

_NODES_TAB = next(canvas.tab for canvas in CANVASES if canvas.key == 'main')

# What goes to elements-pending-store in place of the Nodes canvas's elements
# until that canvas loads. It still marks a render, which is what the graph
# version bridge, the startup cover and the Goals prewarm listen for.
CANVAS_DEFERRED = {'deferred': True}


def _node_count(members):
    return "1 node" if len(members) == 1 else f"{len(members)} nodes"


def canvas_wanted(active_tab, payload_stamp):
    """Whether this render sends the Nodes canvas its elements.

    The canvas loads on its first visit. Its ingest and cold layout cost the
    browser about a second of main-thread work, which used to hold up
    startup. Once loaded it is kept current in the background, so later
    visits find it ready.
    """
    return (active_tab == _NODES_TAB
            or bool((payload_stamp or {}).get('loaded')))


# A Community row's label names its hubs, and the clusters move when the
# graph does: a node marked Done leaves the graph they are drawn from, which
# can regroup a cluster and rename it. A selection whose label is gone used to
# show the whole graph while the Select still held the dead label and the
# "filtered" indicator stayed on. Now the canvas remembers the members of the
# selected row and follows the listed row that shares at least this much of
# them (members in both over members in either). With none, the selection
# goes back to All, so the Select, the indicator and the canvas agree.
FOLLOW_OVERLAP = 0.5


def _overlap(a, b):
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def resolve_community(f_community, rows, memory):
    """The Community row a selection stands for, as ``(value, members)``.

    ``rows`` are list_communities' ``(label, members)`` pairs, and ``memory``
    the ``{"label", "members"}`` the selection had at the last render. The
    value is the label to select, "All" for no selection, and members are
    None for All. A label the user just picked is taken as it is; a label
    kept from earlier must still hold the same cluster.
    """
    if not f_community or f_community == "All":
        return "All", None
    by_label = {label: set(members) for label, members in rows}
    memory = memory if isinstance(memory, dict) else {}
    if memory.get("label") != f_community:
        members = by_label.get(f_community)
        return (f_community, members) if members is not None else ("All", None)
    remembered = set(memory.get("members") or ())
    current = by_label.get(f_community)
    if current is not None and _overlap(remembered, current) >= FOLLOW_OVERLAP:
        return f_community, current
    best = max(by_label, key=lambda label: (_overlap(remembered, by_label[label]), label),
               default=None)
    if best is not None and _overlap(remembered, by_label[best]) >= FOLLOW_OVERLAP:
        return best, by_label[best]
    return "All", None


def build_canvas_view(manager, generate_elements, trigger_id, active_node_id, community_method, filters, f_community, focus_goal, focus_subtree_override, focus_path_info, community_memory=None):
    # --- Visual Generation ---
    ui_only_triggers = ('btn-edit-node', 'btn-add', 'btn-editor-new', 'edit-trigger-input', 'details-edit-trigger-input', 'cytoscape-graph', 'btn-close-editor', 'btn-goals-toggle')
    if trigger_id in ui_only_triggers:
        # We bypass full graph recreation and list evaluation
        elements = dash.no_update
        community_options = dash.no_update
        search_options = dash.no_update
        f_ctx_list = dash.no_update
        ctx_list = dash.no_update
        type_list = dash.no_update
        f_type_list = dash.no_update
        active_stylesheet = dash.no_update
        clear_focus_style = dash.no_update
        community_value = community_memory_out = dash.no_update

    else:
        community_method = community_method or "louvain"
        rows = manager.list_communities(method=community_method, filters=filters)
        # A row's value is its label, not its position: ranks move whenever a
        # score does, and a selection should stay on the same cluster.
        community_options = [{"label": "All", "value": "All"}]
        members_by_value = {}
        for label, members in rows:
            community_options.append({"label": f"{label} ({_node_count(members)})",
                                      "value": label})
            members_by_value[label] = members

        selected, community_names = resolve_community(
            f_community, rows, community_memory)
        if selected == "All" and community_method == "orphans":
            # "All" in orphans mode still means every orphan node, listed or
            # not, and nothing else: none at all once every node has a link.
            community_names = set().union(
                *manager.detect_communities(method="orphans", filters=filters))
        # Written only when they change: the Select's value wakes the
        # filters indicator.
        community_value = (selected if selected != (f_community or "All")
                           else dash.no_update)
        memory = ({"label": selected, "members": sorted(community_names)}
                  if selected != "All" else None)
        community_memory_out = memory if memory != community_memory else dash.no_update

        elements = generate_elements(filters, active_node_id,
                                    community_names=community_names)

        search_options = node_options(manager.get_all_nodes(include_dormant=True))

        # Append alias entries to search options (use alias: prefix for unique values)
        for alias, node_name in manager.get_all_aliases().items():
            search_options.append({'label': f"{alias} \u2192 {node_name}", 'value': f"alias:{alias}"})

        # Populate dynamic contexts datalists from DB + Config, sorted per user setting.
        base_ctx = sort_contexts(ConfigManager.get_contexts())

        ctx_list = [{"label": c, "value": c} for c in base_ctx]
        f_ctx_list = [{"label": c, "value": c} for c in base_ctx]

        base_types = SUPPORTED_NODE_TYPES
        type_list = [{"label": t, "value": t} for t in base_types]

        f_type_list = [{"label": t, "value": t} for t in base_types]

        # Focus mode stylesheet: highlight subtree, dim others
        from skilltree.ui.styles import stylesheet as base_stylesheet
        active_stylesheet = list(base_stylesheet)
        if focus_goal:
            if focus_subtree_override is not None:
                focus_subtree = focus_subtree_override
            else:
                focus_subtree = manager.get_goal_subtree(focus_goal)
                focus_subtree.add(focus_goal)
            active_stylesheet.append({
                'selector': 'node',
                'style': {'opacity': 0.06, 'z-index': 0}
            })
            active_stylesheet.append({
                'selector': 'edge',
                'style': {'opacity': 0.04, 'z-index': 0}
            })
            # Build an attribute-selector with a delimiter that doesn't
            # clash with quote characters in the id. Cytoscape's selector
            # parser does NOT honor CSS backslash-escape inside string
            # values, so a name like Read "Meditations" inside double-quote
            # delimiters silently matches nothing and leaves the node
            # dimmed. Swap to single-quote delimiters when the id has a
            # double-quote (and vice versa). Names containing both kinds
            # are rare; we skip the per-node highlight in that case rather
            # than emit a broken selector.
            def _attr_selector(prop, value):
                has_dq = '"' in value
                has_sq = "'" in value
                if has_dq and has_sq:
                    return None
                quote = "'" if has_dq else '"'
                return f'[{prop} = {quote}{value}{quote}]'

            def _edge_selector(source, target, edge_type):
                parts = [_attr_selector('source', source),
                         _attr_selector('target', target),
                         _attr_selector('type', edge_type)]
                return None if None in parts else ''.join(parts)

            for node_name in focus_subtree:
                sel_tail = _attr_selector('id', node_name)
                if sel_tail is None:
                    continue
                # Pin every opacity sub-channel so nothing downstream
                # (node/border/label/background) inherits the dim; z-index
                # raises focus nodes above the dimmed layer so overlapping
                # neighbors don't peek through concave shapes (stars).
                active_stylesheet.append({
                    'selector': f'node{sel_tail}',
                    'style': {
                        'opacity': 1,
                        'background-opacity': 1,
                        'border-opacity': 1,
                        'text-opacity': 1,
                        'z-index': 10,
                    },
                })
            # Highlight edges between focus subtree nodes
            edges = manager.get_edges()
            for e in edges:
                if e['source'] in focus_subtree and e['target'] in focus_subtree:
                    sel_tail = _edge_selector(e['source'], e['target'], e['type'])
                    if sel_tail is None:
                        continue
                    active_stylesheet.append({
                        'selector': f'edge{sel_tail}',
                        'style': {
                            'opacity': 1,
                            'line-opacity': 1,
                            'text-opacity': 1,
                            'z-index': 5,
                        },
                    })

            # Per-path coloring (new focus-paths feature).
            # Populated only when focus_goal_store carries path_info;
            # the existing mini-graph Focus button leaves it None.
            if focus_path_info:
                # Saturated hues (Material Design A-accent shades) so
                # paths stay punchy against the dimmed background.
                PATH_COLORS = {
                    1: '#ff1744',  # vivid red  # literal: Cytoscape
                    2: '#1de9b6',  # bright teal  # literal: Cytoscape
                    3: '#d500f9',  # electric purple  # literal: Cytoscape
                    4: '#ff6d00',  # deep orange  # literal: Cytoscape
                    5: '#f50057',  # hot pink  # literal: Cytoscape
                }
                for name, rank in (focus_path_info.get('node_rank') or {}).items():
                    color = PATH_COLORS.get(int(rank))
                    if color is None:
                        continue
                    sel_tail = _attr_selector('id', name)
                    if sel_tail is None:
                        continue
                    active_stylesheet.append({
                        'selector': f'node{sel_tail}',
                        'style': {'border-color': color,
                                  'border-width': 4},
                    })
                for edge_key, rank in (focus_path_info.get('edge_rank') or {}).items():
                    parts = bridge_payloads.parse_edge_key(edge_key)
                    if parts is None:
                        continue
                    src, tgt, etype = parts
                    color = PATH_COLORS.get(int(rank))
                    if color is None:
                        continue
                    sel_tail = _edge_selector(src, tgt, etype)
                    if sel_tail is None:
                        continue
                    active_stylesheet.append({
                        'selector': f'edge{sel_tail}',
                        'style': {'line-color': color,
                                  'target-arrow-color': color,
                                  'width': 3},
                    })
                for name, badge in (focus_path_info.get('target_labels') or {}).items():
                    sel_tail = _attr_selector('id', name)
                    if sel_tail is None:
                        continue
                    active_stylesheet.append({
                        'selector': f'node{sel_tail}',
                        'style': {'label': f'{badge} {name}'},
                    })

        clear_focus_style = {"display": "inline-block"} if focus_goal else {"display": "none"}

        # Node-completion events are now fired from GraphManager.update_node
        # whenever a node transitions to Done — no per-callback hook needed.
        # The time-based sweeps (check_pending_activations / check_scheduled_triggers)
        # still run at the top of core_engine because they're polling and
        # don't have a single transition point to hook into.

    return CoreResponse(
        elements=elements,
        community_options=community_options,
        search_options=search_options,
        filter_context_options=f_ctx_list,
        node_context_options=ctx_list,
        node_type_options=type_list,
        filter_type_options=f_type_list,
        stylesheet=active_stylesheet,
        clear_focus_style=clear_focus_style,
        community_value=community_value,
        community_memory=community_memory_out,
    )
