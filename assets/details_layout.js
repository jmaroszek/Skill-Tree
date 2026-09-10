/**
 * Build the Details graph layout request while filtering Dash Cytoscape's positional
 * elements echo.
 *
 * dash-cytoscape writes its live elements (including positions) back to its
 * `elements` prop about 100 ms after add/remove events. The Details layout
 * callback listens to that prop so a genuine topology update is laid out only
 * after Cytoscape has received it. Without the signature check below, the
 * positional echo starts a second incremental layout pass over the same graph.
 */
(function () {
    window.dash_clientside = window.dash_clientside || {};

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

    function topologyRoot(elements, fallbackRoot) {
        if (Array.isArray(elements)) {
            for (var i = 0; i < elements.length; i++) {
                var data = elements[i] && elements[i].data;
                if (data && data.source === undefined && data.details_root) {
                    return data.id;
                }
            }
        }
        return fallbackRoot;
    }

    function currentCyInstance() {
        if (typeof document === 'undefined') return null;
        var wrapper = document.getElementById('details-mini-graph');
        return wrapper && wrapper._cyreg ? wrapper._cyreg.cy : null;
    }

    // The signature describes one live Cytoscape instance, not the wrapper
    // DOM node. Dash can replace the instance during a remount/hot reload
    // while leaving window.SkillTree intact. Reset on that boundary or the
    // first real elements update for the replacement could look like an echo,
    // leaving all of its nodes at Cytoscape's default origin.
    if (window.SkillTree && window.SkillTree.onCytoReady) {
        window.SkillTree.onCytoReady('#details-mini-graph', function (cy) {
            if (window.SkillTree._detailsLayoutCy === cy) return;
            window.SkillTree._detailsLayoutCy = cy;
            delete window.SkillTree._detailsLayoutRoot;
            delete window.SkillTree._detailsLayoutSignature;
        });
    }

    window.dash_clientside.skillTreeDetailsLayout = {
        build: function (edgeLength, gravity, repulsion, animate, relayoutClicks,
                         elements, freezeOn, root) {
            var noUpdate = window.dash_clientside.no_update;
            var triggered = triggerId();
            var isElementsUpdate = triggered === 'details-mini-graph';
            var isRelayout = triggered === 'details-graph-settings-relayout';

            // While frozen, only the user's explicit Settle action may move
            // the graph. Element deltas are applied in place by
            // freeze_positions.js and intentionally produce no layout.
            if (freezeOn && !isRelayout) return noUpdate;

            var state = window.SkillTree || (window.SkillTree = {});
            var cy = currentCyInstance();
            if (cy && state._detailsLayoutCy !== cy) {
                state._detailsLayoutCy = cy;
                delete state._detailsLayoutRoot;
                delete state._detailsLayoutSignature;
            }
            // Use the root carried by the elements instead of relying only on
            // the selected-node State. Dash may deliver both callback outputs
            // in separate renderer turns; the graph can otherwise arrive
            // while State still names the previous selection.
            var layoutRoot = isElementsUpdate
                ? topologyRoot(elements, root)
                : root;
            var rootChanged = state._detailsLayoutRoot !== layoutRoot;
            if (isElementsUpdate) {
                var signature = topologySignature(elements);
                if (!rootChanged && signature === state._detailsLayoutSignature) {
                    // Same nodes and edges, now carrying positions: this is
                    // dash-cytoscape's feedback echo, not a new graph.
                    return noUpdate;
                }
                state._detailsLayoutRoot = layoutRoot;
                state._detailsLayoutSignature = signature;
            }

            if (isRelayout && state.allowOneLayout) {
                state.allowOneLayout('details');
            }

            var nodeCount = 0;
            if (Array.isArray(elements)) {
                for (var i = 0; i < elements.length; i++) {
                    var data = elements[i] && elements[i].data;
                    if (data && data.source === undefined) nodeCount += 1;
                }
            }

            // fCoSE's spectral seed tends to make small, sparse dependency
            // views perfectly collinear. Cytoscape's force-only CoSE keeps
            // those local views spatial, while fCoSE remains the faster
            // choice once a Details subtree is large.
            var name = nodeCount <= 24 ? 'cose' : 'fcose';

            // The two layouts read `animate` differently, and taking CoSE's
            // `true` at face value is what made small subtrees snap into place
            // with no motion at all.
            //
            // CoSE's `true` means "repaint the physics as it runs", and it
            // suppresses those repaints for the first animationThreshold
            // (250 ms) so a fast run doesn't flash. A subtree this small
            // converges well inside that window, so every intermediate frame
            // was skipped and only the final jump ever reached the screen.
            // `'end'` instead tweens from the starting positions to the
            // computed ones — the same layoutPositions() path fCoSE animates
            // through, so both sizes now expand out of the centre alike.
            // fCoSE has no 'end' mode; `true` already means exactly that.
            var layout = {
                name: name,
                animate: animate ? (name === 'cose' ? 'end' : true) : false,
                // CoSE leaves this undefined, which Cytoscape reads as 400 ms.
                // State it so the short views run at fCoSE's pace instead of
                // rushing past at less than half of it.
                animationDuration: 1000,
                fit: true,
                // A new subtree needs a randomized seed. Same-root
                // topology changes remain incremental to preserve its mental
                // map; the positional echo never reaches this point.
                randomize: isRelayout || (isElementsUpdate && rootChanged),
                padding: 20,
                idealEdgeLength: edgeLength || 100,
                nodeRepulsion: repulsion || 4500,
                gravity: gravity !== null && gravity !== undefined ? gravity : 0.25,
                numIter: Math.max(500, Math.min(2500, nodeCount * 25))
            };
            if (layout.name === 'fcose') layout.quality = 'proof';

            // With autoRefreshLayout disabled, dash-cytoscape only starts a
            // layout when this prop changes. Two different small graphs can
            // otherwise produce byte-for-byte identical options (both clamp
            // to 500 iterations), leaving the replacement nodes at origin.
            // Cytoscape ignores this namespaced option; React uses it to see a
            // distinct, accepted request.
            state._detailsLayoutSequence =
                (state._detailsLayoutSequence || 0) + 1;
            layout.skillTreeRequestId = state._detailsLayoutSequence;
            return layout;
        }
    };
})();
