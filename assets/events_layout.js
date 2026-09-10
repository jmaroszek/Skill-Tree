/**
 * Build the Events graph layout request while filtering Dash Cytoscape's
 * positional elements echo.
 *
 * dash-cytoscape writes its live elements (including positions) back to its
 * `elements` prop about 100 ms after add/remove events. The Events layout
 * callback listens to that prop so a new event's graph is laid out once
 * Cytoscape has received it. Without the signature check below, the echo
 * starts a second incremental fCoSE pass from half-animated positions. Both
 * passes then tween the same nodes, and the first finishing before the second
 * reads as a jerk near the end of the animation. details_layout.js filters the
 * same echo for the Details canvas.
 */
(function () {
    window.dash_clientside = window.dash_clientside || {};

    var CY_ID = 'events-detail-graph';

    function triggerId() {
        var context = window.dash_clientside.callback_context || {};
        if (context.triggered_id) return context.triggered_id;
        if (context.triggered && context.triggered.length) {
            return String(context.triggered[0].prop_id || '').split('.')[0];
        }
        return null;
    }

    function topologySignature(elements) {
        if (!Array.isArray(elements)) return '[]';
        var entries = elements.map(function (element) {
            var data = element && element.data ? element.data : {};
            if (data.source !== undefined) {
                return [
                    'edge', String(data.id || ''), String(data.source || ''),
                    String(data.target || ''), String(data.type || '')
                ];
            }
            return ['node', String(data.id || ''), String(data.parent || '')];
        });
        entries.sort(function (left, right) {
            return JSON.stringify(left).localeCompare(JSON.stringify(right));
        });
        return JSON.stringify(entries);
    }

    function currentCyInstance() {
        if (typeof document === 'undefined') return null;
        var wrapper = document.getElementById(CY_ID);
        return wrapper && wrapper._cyreg ? wrapper._cyreg.cy : null;
    }

    // The signature describes one live Cytoscape instance. A replacement
    // instance has no positions even for an identical graph, so its first
    // elements update must not be mistaken for an echo.
    function forgetLayout(state, cy) {
        state._eventsLayoutCy = cy;
        delete state._eventsLayoutRoot;
        delete state._eventsLayoutSignature;
    }

    if (window.SkillTree && window.SkillTree.onCytoReady) {
        window.SkillTree.onCytoReady('#' + CY_ID, function (cy) {
            if (window.SkillTree._eventsLayoutCy === cy) return;
            forgetLayout(window.SkillTree, cy);
        });
    }

    window.dash_clientside.skillTreeEventsLayout = {
        build: function (edgeLength, gravity, repulsion, animate, relayoutClicks,
                         elements, freezeOn, root) {
            var noUpdate = window.dash_clientside.no_update;
            var triggered = triggerId();
            var isElementsUpdate = triggered === CY_ID;
            var isRelayout = triggered === 'events-graph-settings-relayout';

            // While frozen, only the user's explicit Settle action may move
            // the graph. Element deltas are applied in place by
            // freeze_positions.js and intentionally produce no layout.
            if (freezeOn && !isRelayout) return noUpdate;

            var state = window.SkillTree || (window.SkillTree = {});
            var cy = currentCyInstance();
            if (cy && state._eventsLayoutCy !== cy) forgetLayout(state, cy);

            // render_event_graph is driven by selected-event-store, so the
            // State already names the event these elements belong to.
            var rootChanged = state._eventsLayoutRoot !== root;
            if (isElementsUpdate) {
                var signature = topologySignature(elements);
                if (!rootChanged && signature === state._eventsLayoutSignature) {
                    // Same nodes and edges, now carrying positions: this is
                    // dash-cytoscape's feedback echo, not a new graph.
                    return noUpdate;
                }
                state._eventsLayoutRoot = root;
                state._eventsLayoutSignature = signature;
            }

            if (isRelayout && state.allowOneLayout) {
                state.allowOneLayout('events');
            }

            var layout = {
                name: 'fcose',
                quality: 'proof',
                animate: Boolean(animate),
                fit: true,
                // A new event's graph needs a randomized seed. Same-event
                // topology changes remain incremental to preserve its mental
                // map; the positional echo never reaches this point.
                randomize: isRelayout || (isElementsUpdate && rootChanged),
                padding: 20,
                idealEdgeLength: edgeLength || 100,
                nodeRepulsion: repulsion || 4500,
                gravity: gravity !== null && gravity !== undefined ? gravity : 0.25,
                numIter: 2500
            };

            // With autoRefreshLayout disabled, dash-cytoscape only starts a
            // layout when this prop changes. Two events' requests are
            // otherwise byte-for-byte identical, which would leave the second
            // event's nodes at the origin. Cytoscape ignores this namespaced
            // option; React uses it to see a distinct request.
            state._eventsLayoutSequence = (state._eventsLayoutSequence || 0) + 1;
            layout.skillTreeRequestId = state._eventsLayoutSequence;
            return layout;
        }
    };
})();
