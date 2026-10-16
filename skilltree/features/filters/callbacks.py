"""The Filters sidebar's callbacks: Clear filters, the search field, and the
chips and funnel that say a view is filtered."""
from dash import Input, Output, State, no_update

from skilltree.ui.filters import (
    filter_chip_state,
    filter_chip_updates,
    filter_summary,
    is_filters_active,
)
from skilltree.ui.prerender import prerendered


def register_filter_callbacks(app, services=None):
    # --- Clear Filters ---
    # Note: filter-subcontext.value is reset clientside (see below). The prop is
    # written by the context picker's own JS, and a server-side Output here
    # would let Dash clobber those picks on unrelated callback runs.
    @app.callback(
        Output('filter-node-type', 'value'),
        Output('filter-context', 'value'),
        Output('community-method', 'value'),
        Output('filter-community', 'value'),
        Output('filter-value', 'value'),
        Output('filter-interest', 'value'),
        Output('filter-difficulty', 'value'),
        Output('filter-time-min', 'value'),
        Output('filter-time', 'value'),
        Output('filter-time-unit', 'value'),
        Output('filter-done', 'value', allow_duplicate=True),
        Output('filter-dormant', 'value', allow_duplicate=True),
        Output('filter-text', 'value', allow_duplicate=True),
        Output('filter-text-scope', 'value'),
        Input('btn-clear-filters', 'n_clicks'),
        Input('btn-details-focus', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_filters(_clear_clicks, _focus_clicks):
        return ([], [], 'louvain', 'All', [1, 10], [1, 10], [1, 10], None, None,
                'hours', [], [], '', [])

    # The Search query every canvas filters by: the field's text and the
    # descriptions switch, as one value. None without text, so a switch change
    # with nothing to search is not a filter change, and an unchanged query is
    # not rewritten. A rewrite would start a layout for the same nodes.
    app.clientside_callback(
        """
        function(text, scope, current) {
            var q = (text || '').trim();
            var next = q ? {text: q, descriptions: (scope || []).indexOf('descriptions') !== -1} : null;
            return JSON.stringify(next) === JSON.stringify(current || null)
                ? window.dash_clientside.no_update : next;
        }
        """,
        Output('filter-search-query', 'data'),
        Input('filter-text', 'value'),
        Input('filter-text-scope', 'value'),
        State('filter-search-query', 'data'),
        prevent_initial_call=True,
    )

    # The Search field's own clear button. It empties the field, which the
    # canvas then answers like any other change to it.
    app.clientside_callback(
        """
        function(clicks) {
            return clicks ? '' : window.dash_clientside.no_update;
        }
        """,
        Output('filter-text', 'value', allow_duplicate=True),
        Input('btn-clear-filter-text', 'n_clicks'),
        prevent_initial_call=True,
    )

    # The suggestions under the Search field come from the node editor's own
    # Search list, which holds every node's name and alias. The script keeps
    # the names and draws the panel (assets/filter_suggest.js).
    app.clientside_callback(
        """
        function(options) {
            var suggest = window.SkillTree && window.SkillTree.filterSuggest;
            if (suggest) suggest.setOptions(options);
        }
        """,
        Input('search-node', 'options'),
    )

    # An applied query outlines the field, so a narrowing is never invisible.
    app.clientside_callback(
        """
        function(text) {
            return 'editor-field-group filter-search'
                + (text && text.trim() ? ' filter-search-active' : '');
        }
        """,
        Output('filter-search', 'className'),
        Input('filter-text', 'value'),
        prevent_initial_call=True,
    )

    # The placeholder says what the field searches, and follows the switch.
    # The opening text is in build_filters_content.
    app.clientside_callback(
        """
        function(scope) {
            return (scope || []).indexOf('descriptions') !== -1
                ? 'Filter by names, aliases and descriptions...'
                : 'Filter by names and aliases...';
        }
        """,
        Output('filter-text', 'placeholder'),
        Input('filter-text-scope', 'value'),
        prevent_initial_call=True,
    )

    # A minimum above the maximum matches nothing, so build_filters ignores
    # the time range then; outline both fields so that is not silent.
    app.clientside_callback(
        """
        function(low, high) {
            var crossed = low !== null && low !== undefined && low !== ''
                && high !== null && high !== undefined && high !== ''
                && Number(low) > Number(high);
            return [crossed, crossed];
        }
        """,
        Output('filter-time-min', 'invalid'),
        Output('filter-time', 'invalid'),
        Input('filter-time-min', 'value'),
        Input('filter-time', 'value'),
    )

    # Clientside reset of filter-subcontext.value on Clear Filters / Focus.
    # Server-side reset would put a callback Output on this prop, which Dash
    # uses as license to discard the layout-set value on initial render.
    app.clientside_callback(
        """
        function(clear_clicks, focus_clicks) {
            if (!clear_clicks && !focus_clicks) {
                return window.dash_clientside.no_update;
            }
            return [];
        }
        """,
        Output('filter-subcontext', 'value', allow_duplicate=True),
        Input('btn-clear-filters', 'n_clicks'),
        Input('btn-details-focus', 'n_clicks'),
        prevent_initial_call=True,
    )

    # Whether any filter narrows the Nodes canvas, for the top bar's funnel,
    # and each chip's summary. Next ignores Community and Orphans, so they don't
    # mark it filtered. Each writes only when its answer changes: a filter
    # change starts the Nodes layout, and each write would land inside it.
    @app.callback(
        Output('canvas-filters-active-store', 'data'),
        Output('next-filter-chip-text', 'children'),
        Output('next-filter-chip', 'title'),
        Output('next-filter-chip', 'hidden'),
        Output('nodes-filter-chip-text', 'children'),
        Output('nodes-filter-chip', 'title'),
        Output('nodes-filter-chip', 'hidden'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('filter-community', 'value'),
        Input('community-method', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-time-unit', 'value'),
        Input('filter-time-min', 'value'),
        Input('filter-search-query', 'data'),
        State('canvas-filters-active-store', 'data'),
        State('next-filter-chip-text', 'children'),
        State('next-filter-chip', 'title'),
        State('next-filter-chip', 'hidden'),
        State('nodes-filter-chip-text', 'children'),
        State('nodes-filter-chip', 'title'),
        State('nodes-filter-chip', 'hidden'),
        prevent_initial_call=True,
    )
    @prerendered
    def update_canvas_filters_active(f_type, f_ctx, f_sub, f_comm,
                                     f_comm_method, f_val, f_int, f_diff,
                                     f_time, f_time_unit, f_time_min, f_search,
                                     current, chip_text, chip_title, chip_class,
                                     nodes_text, nodes_title, nodes_hidden):
        shared = dict(node_type=f_type, context=f_ctx, subcontext=f_sub,
                      value=f_val, interest=f_int, difficulty=f_diff,
                      time=f_time, time_min=f_time_min, search=f_search)
        active = is_filters_active(community=f_comm,
                                   community_method=f_comm_method, **shared)
        chip = filter_chip_state(filter_summary(time_unit=f_time_unit, **shared))
        nodes_chip = filter_chip_state(filter_summary(
            time_unit=f_time_unit, community=f_comm,
            community_method=f_comm_method, **shared))
        return (no_update if active == bool(current) else active,
                *filter_chip_updates(chip, (chip_text, chip_title, chip_class)),
                *filter_chip_updates(nodes_chip, (nodes_text, nodes_title, nodes_hidden)))

    # The top bar's funnel fills in while any filter is narrowing the app.
    app.clientside_callback(
        """
        function(active) {
            return active ? 'bi bi-funnel-fill filters-icon-active' : 'bi bi-funnel';
        }
        """,
        Output('btn-filters-icon', 'className'),
        Input('canvas-filters-active-store', 'data'),
    )

    # The chips' clear buttons press Clear Filters, as the empty canvas's does.
    app.clientside_callback(
        """
        function(next_clicks, details_clicks, nodes_clicks, events_clicks, current) {
            return (next_clicks || details_clicks || nodes_clicks || events_clicks)
                ? (current || 0) + 1 : window.dash_clientside.no_update;
        }
        """,
        Output('btn-clear-filters', 'n_clicks', allow_duplicate=True),
        Input('next-filter-chip-clear', 'n_clicks'),
        Input('details-filter-chip-clear', 'n_clicks'),
        Input('nodes-filter-chip-clear', 'n_clicks'),
        Input('events-filter-chip-clear', 'n_clicks'),
        State('btn-clear-filters', 'n_clicks'),
        prevent_initial_call=True,
    )

    # The message's buttons flip the switches it names, or press Clear Filters.
    app.clientside_callback(
        "function(clicks) { return clicks ? ['show_done'] : window.dash_clientside.no_update; }",
        Output('filter-done', 'value', allow_duplicate=True),
        Input('btn-empty-show-done', 'n_clicks'),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        "function(clicks) { return clicks ? ['show_dormant'] : window.dash_clientside.no_update; }",
        Output('filter-dormant', 'value', allow_duplicate=True),
        Input('btn-empty-show-dormant', 'n_clicks'),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(clicks, current) {
            return clicks ? (current || 0) + 1 : window.dash_clientside.no_update;
        }
        """,
        Output('btn-clear-filters', 'n_clicks', allow_duplicate=True),
        Input('btn-empty-clear', 'n_clicks'),
        State('btn-clear-filters', 'n_clicks'),
        prevent_initial_call=True,
    )

    # When the user changes context, prune any subcontext picks whose context
    # is no longer in the selection. Clientside only: Dash strips the layout's
    # `value=` for any prop that has a server-side callback Output, which
    # would nuke the memory-restored picks.
    app.clientside_callback(
        """
        function(ctx, current_subs) {
            if (!current_subs || current_subs.length === 0) {
                return window.dash_clientside.no_update;
            }
            const contexts = Array.isArray(ctx) ? ctx : (ctx ? [ctx] : []);
            const ctxSet = new Set(contexts);
            const SEP = '\\u001f';
            const kept = current_subs.filter(v => {
                const sep = v.indexOf(SEP);
                if (sep < 0) return false;
                return ctxSet.has(v.slice(0, sep));
            });
            if (kept.length === current_subs.length) {
                return window.dash_clientside.no_update;
            }
            return kept;
        }
        """,
        Output('filter-subcontext', 'value'),
        Input('filter-context', 'value'),
        State('filter-subcontext', 'value'),
        prevent_initial_call=True,
    )
