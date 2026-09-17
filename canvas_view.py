"""Canvas view preparation, independent of mutation routing and callback registration."""
import dash
from config import ConfigManager, SUPPORTED_NODE_TYPES, sort_contexts
from callback_helpers import format_traversal_ui, node_options
from core_response import CoreResponse


def build_canvas_view(manager, generate_elements, trigger_id, tapped_node, active_node_id, community_method, filters, f_community, focus_goal, focus_subtree_override, focus_path_info):
    # --- Visual Generation ---
    ui_only_triggers = ('btn-edit-node', 'btn-add', 'btn-new-node', 'btn-editor-new', 'edit-trigger-input', 'details-edit-trigger-input', 'cytoscape-graph', 'btn-close-editor', 'btn-goals-toggle')
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

        # Still format sidebar traversal UI
        sugg_ui = dash.no_update  # Next owns recommendation rendering independently.
        effective_tapped_node = None if trigger_id in ('background-click-input', 'btn-editor-new') else tapped_node
        hard_chains_ui, soft_chains_ui, synergies_ui, description_ui = format_traversal_ui(effective_tapped_node, active_node_id, manager)

    else:
        community_method = community_method or "louvain"
        communities = manager.detect_communities(method=community_method, filters=filters)
        community_options = [{"label": "All", "value": "All"}]
        name_counts: dict[str, int] = {}
        for i, comm in enumerate(communities):
            base_name = manager.name_community(comm)
            name_counts[base_name] = name_counts.get(base_name, 0) + 1
            if name_counts[base_name] > 1:
                label = f"{base_name} #{name_counts[base_name]} ({len(comm)} nodes)"
            else:
                label = f"{base_name} ({len(comm)} nodes)"
            community_options.append({"label": label, "value": str(i)})
        # Fix labels retroactively when the first occurrence also needs a number
        for key, count in name_counts.items():
            if count > 1:
                for opt in community_options:
                    if opt["label"].startswith(f"{key} (") and opt["value"] != "All":
                        opt["label"] = opt["label"].replace(f"{key} (", f"{key} #1 (", 1)
                        break

        community_names = None
        if f_community and f_community != "All":
            try:
                idx = int(f_community)
                if 0 <= idx < len(communities):
                    community_names = communities[idx]
            except (ValueError, IndexError): pass
        elif community_method == "orphans" and communities:
            # "All" in orphans mode still means "only orphan nodes", not every node
            community_names = set().union(*communities)

        elements = generate_elements(filters, active_node_id,
                                    community_names=community_names)

        sugg_ui = dash.no_update  # Next owns recommendation rendering independently.
        effective_tapped_node = None if trigger_id in ('background-click-input', 'btn-editor-new') else tapped_node
        hard_chains_ui, soft_chains_ui, synergies_ui, description_ui = format_traversal_ui(effective_tapped_node, active_node_id, manager)

        all_nodes = manager.get_all_nodes()
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
        from styles import stylesheet as base_stylesheet
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
                    eid = f"{e['source']}_{e['target']}_{e['type']}"
                    sel_tail = _attr_selector('id', eid)
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
                    1: '#ff1744',  # vivid red
                    2: '#1de9b6',  # bright teal
                    3: '#d500f9',  # electric purple
                    4: '#ff6d00',  # deep orange
                    5: '#f50057',  # hot pink
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
                    parts = edge_key.split('|')
                    if len(parts) != 3:
                        continue
                    src, tgt, etype = parts
                    color = PATH_COLORS.get(int(rank))
                    if color is None:
                        continue
                    eid = f"{src}_{tgt}_{etype}"
                    sel_tail = _attr_selector('id', eid)
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
        suggestions=sugg_ui,
        hard_chains=hard_chains_ui,
        soft_chains=soft_chains_ui,
        synergies=synergies_ui,
        description=description_ui,
        community_options=community_options,
        search_options=search_options,
        filter_context_options=f_ctx_list,
        node_context_options=ctx_list,
        node_type_options=type_list,
        filter_type_options=f_type_list,
        stylesheet=active_stylesheet,
        clear_focus_style=clear_focus_style,
    )
