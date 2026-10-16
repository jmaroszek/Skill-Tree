"""Behavior every canvas shares: the hover tooltip, Locate, freezing positions
and layout requests. Each loops over CANVASES rather than naming a canvas."""
import dash
from dash import ClientsideFunction, Input, Output, State, ctx, html

from skilltree.store.graph.manager import GraphManager
from skilltree.ui import tokens
from skilltree.ui.canvas.registry import CANVASES
from skilltree.ui.components.duration import format_time_friendly
from skilltree.ui.dash_tools import get_trigger_id
from skilltree.ui.kit import progress_bar_color
from skilltree.ui.prerender import prerendered

manager = GraphManager()


def register_canvas_callbacks(app, services=None):
    manager = services.graph if services is not None else globals()['manager']

    # --- Tooltip Formatting ---
    @app.callback(
        Output('hover-tooltip', 'children'),
        *(Input(canvas.cytoscape_id, 'mouseoverNodeData') for canvas in CANVASES),
        prevent_initial_call=True,
    )
    @prerendered
    def display_hover_data(*hover_data):
        # Only the canvas that fired holds the node under the cursor. Before
        # any hover nothing has fired, and the first canvas's value is empty.
        trigger = get_trigger_id()
        data = next((value for canvas, value in zip(CANVASES, hover_data)
                     if canvas.cytoscape_id == trigger), hover_data[0])
        if not data: return ""

        node_type = data.get('type', '')
        node_id = data.get('id', data.get('label', ''))

        # Identity marker — tooltip.js reads this to verify the rendered
        # content matches the currently hovered node before showing. Necessary
        # because Dash callback responses can lag cursor movement, so the
        # tooltip's children may briefly hold a previous node's data.
        marker = html.Span(
            node_id,
            className='_tt-marker',
            style={"display": "none"}
        )

        header = html.Div(
            html.Strong(data.get('label', node_id)),
            style={"fontSize": tokens.FS_LG, "marginBottom": "4px",
                   "borderBottom": f"1px solid {tokens.BORDER_PANEL}", "paddingBottom": "4px"}
        )

        if node_type in ('Goal', 'Milestone'):
            completion = manager.get_goal_completion(node_id, include_soft=False)
            total = completion.get('total', 0)
            pct = completion.get('pct', 0)
            remaining = completion.get('remaining_time', 0)

            lines = [marker, header]

            # A Milestone over nothing but other Milestones has no hours to
            # show progress on; a Goal still counts its nodes.
            if total > 0 and (node_type == 'Goal' or completion.get('has_work')):
                bar_color = progress_bar_color(pct)
                lines += [
                    html.Hr(style={"margin": "6px 0", "borderColor": tokens.BORDER_PANEL}),
                    html.Div([html.Strong("Progress: "), f"{pct}% of the estimated work"]),
                    html.Div(
                        html.Div(style={
                            "width": f"{pct}%", "height": "6px",
                            "backgroundColor": bar_color, "borderRadius": "3px",
                            "transition": "width 0.3s ease"
                        }),
                        style={"backgroundColor": tokens.BORDER_PANEL, "borderRadius": "3px",
                               "margin": "4px 0", "overflow": "hidden"}
                    ),
                    html.Div([html.Strong("Remaining: "),
                              format_time_friendly(remaining)]),
                ]
            else:
                empty_text = "No subtasks yet" if total == 0 else "No work beneath it yet"
                lines.append(html.Div(empty_text, style={"color": tokens.TEXT_DIM, "fontStyle": "italic"}))

            ctx_val = data.get('context', '')
            sub_val = data.get('subcontext', '')
            if ctx_val or sub_val:
                subctx_str = f"{ctx_val} > {sub_val}" if ctx_val and sub_val else ctx_val or sub_val
                lines.append(html.Div(subctx_str, style={"color": tokens.TEXT_SOFT}))

        else:
            ratings_inherited = data.get('value_mode') == 'inherited'
            time_inherited = data.get('time_mode') == 'inherited'

            lines = [marker, header]

            if ratings_inherited and time_inherited:
                lines.append(html.Div("Container", style={"color": tokens.TEXT_SOFT}))
            else:
                if ratings_inherited:
                    # Effort stays the node's own while it has its own hours.
                    lines.append(html.Div([html.Strong("Ratings: "), "inherited"]))
                    if not time_inherited:
                        lines.append(html.Div([html.Strong("Effort: "), str(data.get('difficulty', ''))]))
                else:
                    lines += [
                        html.Div([html.Strong("Value: "), str(data.get('value', ''))]),
                        html.Div([html.Strong("Interest: "), str(data.get('interest', ''))]),
                        html.Div([html.Strong("Effort: "), str(data.get('difficulty', ''))]),
                    ]

                if time_inherited:
                    lines.append(html.Div([html.Strong("Time: "), "inherited"]))
                else:
                    time_str = format_time_friendly(data.get('time', 0))
                    lines.append(html.Div([html.Strong("Time: "), time_str]))

            ctx_val = data.get('context', '')
            sub_val = data.get('subcontext', '')
            if ctx_val or sub_val:
                subctx_str = f"{ctx_val} > {sub_val}" if ctx_val and sub_val else ctx_val or sub_val
                lines.append(html.Div(subctx_str, style={"color": tokens.TEXT_SOFT}))

        return lines

    # --- "Locate on graph": enable/disable based on currently-loaded node ---
    # `node-original-name` is populated by the editor whenever ANY node is
    # loaded (via tap, search, details, edit-trigger). `search-node.value` is
    # only set when the user picks from the dropdown, so it's unreliable here.
    app.clientside_callback(
        "function(name) { return !name; }",
        Output('btn-locate-node', 'disabled'),
        Input('node-original-name', 'data'),
    )

    # --- "Locate on graph": validate the editor target, then let the browser
    # inspect the live canvas. Freeze mode mutates Cytoscape directly, so Dash's
    # cached `elements` prop is not authoritative for membership.
    @app.callback(
        Output('locate-message', 'children'),
        Output('locate-clear-interval', 'disabled'),
        Output('locate-clear-interval', 'n_intervals'),
        Output('locate-request-store', 'data'),
        Input('btn-locate-node', 'n_clicks'),
        State('node-original-name', 'data'),
        State('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def handle_locate_click(n_clicks, name, current_tab):
        if not n_clicks or not name:
            return (dash.no_update,) * 4
        node = manager.get_node(name)
        if not node:
            return "This node no longer exists.", False, 0, dash.no_update
        return "", True, 0, {
            'name': name,
            'activeTab': current_tab,
            'request': n_clicks,
        }

    # Resolve the active canvas against the live Cytoscape instance. Details
    # and Events remain in place; tabs without a canvas retain the historical
    # Nodes fallback. The result callback below owns navigation and dialogs.
    app.clientside_callback(
        """function(request) {
            if (!request || !request.name || !window.SkillTree ||
                    typeof window.SkillTree.resolveLocateRequest !== 'function') {
                return window.dash_clientside.no_update;
            }
            return window.SkillTree.resolveLocateRequest(request);
        }""",
        Output('locate-result-store', 'data'),
        Input('locate-request-store', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Output('locate-animate-trigger', 'data'),
        Output('modal-locate-missing', 'is_open'),
        Output('locate-missing-title', 'children'),
        Output('locate-missing-node-store', 'data'),
        Output('details-node-select', 'value', allow_duplicate=True),
        Input('locate-result-store', 'data'),
        Input('btn-locate-dismiss', 'n_clicks'),
        Input('btn-locate-view-details', 'n_clicks'),
        State('locate-missing-node-store', 'data'),
        State('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def handle_locate_result(result, _dismiss_clicks, view_details_clicks,
                             missing_node, current_tab):
        triggered = ctx.triggered_id
        unchanged = (dash.no_update,) * 6

        if triggered == 'btn-locate-dismiss':
            return dash.no_update, dash.no_update, False, dash.no_update, None, dash.no_update

        if triggered == 'btn-locate-view-details':
            name = (missing_node or {}).get('name')
            if not name or not manager.get_node(name):
                return dash.no_update, dash.no_update, False, dash.no_update, None, dash.no_update
            next_tab = dash.no_update if current_tab == 'tab-details' else 'tab-details'
            animate = {
                'name': name,
                'canvasId': 'details-mini-graph',
                'request': view_details_clicks,
            }
            return next_tab, animate, False, dash.no_update, None, name

        if triggered != 'locate-result-store' or not result:
            return unchanged

        status = result.get('status')
        if status == 'located':
            return dash.no_update, dash.no_update, False, dash.no_update, None, dash.no_update
        if status == 'navigate':
            animate = {
                'name': result.get('name'),
                'canvasId': result.get('canvasId'),
                'request': result.get('request'),
            }
            return result.get('targetTab'), animate, False, dash.no_update, None, dash.no_update
        if status == 'missing':
            view_labels = {
                'main': 'Nodes',
                'details': 'Details',
                'events': 'Events',
                'canvas': 'current',
            }
            name = result.get('name')
            label = view_labels.get(result.get('view'), 'current')
            title = f'“{name}” is not in the {label} view'
            return (dash.no_update, dash.no_update, True, title,
                    {'name': name}, dash.no_update)
        return unchanged

    # Run the pulse after a tab switch or Details re-root. The fcose layout may
    # still be running, so locateNodeOnGraph retries until the node is present.
    app.clientside_callback(
        """function(trigger) {
            if (!trigger || !trigger.name || !trigger.canvasId) {
                return window.dash_clientside.no_update;
            }
            if (typeof window.locateNodeOnGraph === 'function') {
                window.locateNodeOnGraph(trigger.name, trigger.canvasId);
            }
            return window.dash_clientside.no_update;
        }""",
        Output('locate-message', 'title'),  # dummy/no-op output
        Input('locate-animate-trigger', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('locate-message', 'children', allow_duplicate=True),
        Output('locate-clear-interval', 'disabled', allow_duplicate=True),
        Input('locate-clear-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def clear_locate_message(n):
        if n > 0:
            return "", True
        return dash.no_update, dash.no_update

    # --- Freeze feature: per-canvas clientside wiring ---
    # Each canvas in canvases.CANVASES gets three parameterized
    # clientside callbacks: pending-store → elements bypass, switch → store
    # sync (also flips the JS frozen flag so the freeze-off refresh doesn't
    # race it), and snowflake/class-name indicator. The Settle (re-layout)
    # button's allowOneLayout call lives inside the layout callback itself
    # so it's sequenced synchronously with the layout-prop write.
    def _register_freeze_callbacks(canvas_id, switch_id, store_id, pending_id,
                                   cytoscape_id, indicator_id, container_id):
        """Wire the three freeze clientside callbacks for one canvas."""
        js_canvas = repr(canvas_id)  # JS-safe quoted string literal

        # Bypass: pending-store -> cytoscape.elements. A hidden canvas's
        # payload waits for its tab (assets/hidden_canvas_payloads.js).
        app.clientside_callback(
            """
            function(pending, activeTab) {
                var st = window.SkillTree || {};
                var noUpdate = window.dash_clientside.no_update;
                function frozen(elements) {
                    if (st.isFrozen && st.isFrozen(__CANVAS__) && st.applyDelta) {
                        st.applyDelta(__CANVAS__, elements);
                        return true;
                    }
                    return false;
                }
                var fired = (window.dash_clientside.callback_context.triggered || [])
                    .map(function (t) { return t.prop_id; });
                if (fired.indexOf(__PENDING__ + '.data') === -1) {
                    // The tab changed. What this canvas was holding lands
                    // once the tab has painted.
                    if (st.showHeldPayload) {
                        st.showHeldPayload(__CANVAS__, activeTab, function (elements) {
                            if (!frozen(elements)) {
                                window.dash_clientside.set_props(__CYTOSCAPE__, {elements: elements});
                            }
                        });
                    }
                    return noUpdate;
                }
                // Anything but a list is a render with no elements to apply,
                // such as the Nodes canvas's deferred marker.
                if (!Array.isArray(pending)) return noUpdate;
                if (st.holdHiddenPayload && st.holdHiddenPayload(__CANVAS__, pending, activeTab)) {
                    return noUpdate;
                }
                return frozen(pending) ? noUpdate : pending;
            }
            """.replace('__CANVAS__', js_canvas).replace('__PENDING__', repr(pending_id))
               .replace('__CYTOSCAPE__', repr(cytoscape_id)),
            Output(cytoscape_id, 'elements'),
            Input(pending_id, 'data'),
            Input('main-tabs', 'active_tab'),
            prevent_initial_call=True,
        )

        # Switch -> store sync (also flips JS frozen flag synchronously).
        app.clientside_callback(
            """
            function(value) {
                var v = Boolean(value);
                if (window.SkillTree && window.SkillTree.setFreezeActive) {
                    window.SkillTree.setFreezeActive(__CANVAS__, v);
                }
                return v;
            }
            """.replace('__CANVAS__', js_canvas),
            Output(store_id, 'data'),
            Input(switch_id, 'value'),
            prevent_initial_call=True,
        )

        # Indicator: snowflake style + container class.
        app.clientside_callback(
            """
            function(frozen, currentClass) {
                var baseStyle = {
                    position: "absolute", top: "12px", right: "19px",
                    fontSize: "1.6rem", color: "var(--st-accent-soft)",
                    textShadow: "0 0 6px rgba(126, 200, 227, 0.5)",
                    pointerEvents: "none", zIndex: 10,
                };
                var classes = (currentClass || "").split(/\\s+/).filter(function(c) {
                    return c && c !== "cyto-frozen";
                });
                if (frozen) classes.push("cyto-frozen");
                baseStyle.display = frozen ? "block" : "none";
                return [baseStyle, classes.join(" ")];
            }
            """,
            Output(indicator_id, 'style'),
            Output(container_id, 'className'),
            Input(store_id, 'data'),
            State(container_id, 'className'),
        )

    for canvas in CANVASES:
        _register_freeze_callbacks(
            canvas_id=canvas.key,
            switch_id=canvas.control_id('freeze-rerender'),
            store_id=canvas.freeze_store_id,
            pending_id=canvas.pending_store_id,
            cytoscape_id=canvas.cytoscape_id,
            indicator_id=canvas.freeze_indicator_id,
            container_id=canvas.container_id,
        )

    # --- Graph Layout: one layout request per canvas ---
    # assets/layout_requests.js builds each canvas's layout prop. It stays
    # clientside so allowOneLayout() is set in the same synchronous function
    # that returns the new layout dict. A previous server-side implementation
    # paired with a separate clientside allowOneLayout callback was racy: Dash
    # doesn't order parallel callbacks bound to the same input, so the layout
    # prop sometimes reached Cytoscape before the JS guard's allowNextLayout
    # flag was set, causing the freeze guard at layoutstart to stop the layout
    # (Settle button silently no-op).
    def _register_layout_callback(canvas):
        inputs = [
            Input(canvas.control_id('edge-length'), 'value'),
            Input(canvas.control_id('gravity'), 'value'),
            Input(canvas.control_id('repulsion'), 'value'),
            Input(canvas.control_id('animate'), 'value'),
            Input(canvas.control_id('relayout'), 'n_clicks'),
        ]
        if canvas.lays_out_elements:
            inputs.append(Input(canvas.cytoscape_id, 'elements'))
        # Control changes wait while the canvas is frozen. The freeze-off
        # transition lays the graph out with them.
        inputs.append(Input(canvas.freeze_store_id, 'data'))
        states = [State(canvas.view_store_id, 'data')] if canvas.view_store_id else []
        app.clientside_callback(
            ClientsideFunction(namespace='skillTreeLayout', function_name=canvas.key),
            Output(canvas.cytoscape_id, 'layout'),
            *inputs,
            *states,
            # Nodes keeps the transition prop layout.py gives it until a
            # control is touched.
            prevent_initial_call=not canvas.lays_out_elements,
        )

    for canvas in CANVASES:
        _register_layout_callback(canvas)
