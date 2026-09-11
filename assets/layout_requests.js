/**
 * Layout requests for every canvas in window.SkillTree.canvases.
 *
 * Each canvas's Graph Layout controls feed one clientside callback, registered
 * by _register_layout_callback in callbacks.py, and this module builds the
 * `layout` prop it returns. dash-cytoscape starts a layout whenever that prop
 * changes. The canvases share the rules below and differ only in POLICY.
 *
 * Nodes leaves element updates to dash-cytoscape's autoRefreshLayout, which
 * re-runs the current prop on every add or remove. Details and Events turn it
 * off (`laysOutElements`) and lay out their own element updates here.
 * dash-cytoscape writes its live elements, now carrying positions, back to the
 * `elements` prop about 100 ms after an add or remove. Their callbacks listen
 * to that prop so a real topology update is laid out once Cytoscape has it. A
 * topology signature filters the positional echo. Without it the echo started
 * a second incremental pass from half-animated positions, and the two tweens
 * finishing out of step read as a jerk.
 */
(function () {
    window.dash_clientside = window.dash_clientside || {};
    var SkillTree = window.SkillTree = window.SkillTree || {};

    // Views this small use force-only CoSE. fCoSE's spectral seed tends to
    // make small, sparse dependency views perfectly collinear, while fCoSE
    // stays the faster choice for anything larger.
    var SMALL_VIEW_NODES = 24;

    var DEFAULT_POLICY = {
        smallViewsUseCose: true,
        scaleIterations: true,
        padding: 20,
        physics: { edgeLength: 100, repulsion: 4500, gravity: 0.25 },
        rootFromElements: false
    };

    var POLICY = {
        // The whole graph: fCoSE at every size, its full iteration budget,
        // and its own physics fallbacks.
        main: {
            smallViewsUseCose: false,
            scaleIterations: false,
            padding: 30,
            physics: { edgeLength: 100, repulsion: 50000, gravity: 0 }
        },
        // Dash may deliver a new selection's elements while the selected-node
        // State still names the previous one, so Details marks the view root
        // inside the elements themselves.
        details: { rootFromElements: true }
    };

    function policyFor(key) {
        return Object.assign({}, DEFAULT_POLICY, POLICY[key] || {});
    }

    function canvasFor(key) {
        return SkillTree.canvases.filter(function (canvas) {
            return canvas.key === key;
        })[0];
    }

    function triggerId() {
        var context = window.dash_clientside.callback_context || {};
        if (context.triggered_id) return context.triggered_id;
        if (context.triggered && context.triggered.length) {
            return String(context.triggered[0].prop_id || '').split('.')[0];
        }
        return null;
    }

    function countNodes(elements) {
        if (!Array.isArray(elements)) return 0;
        var count = 0;
        for (var i = 0; i < elements.length; i++) {
            var data = elements[i] && elements[i].data;
            if (data && data.source === undefined) count += 1;
        }
        return count;
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

    function viewRoot(elements, fallback) {
        if (Array.isArray(elements)) {
            for (var i = 0; i < elements.length; i++) {
                var data = elements[i] && elements[i].data;
                if (data && data.source === undefined && data.details_root) {
                    return data.id;
                }
            }
        }
        return fallback;
    }

    function liveCy(canvas) {
        if (typeof document === 'undefined') return null;
        var wrapper = document.getElementById(canvas.cytoscapeId);
        return wrapper && wrapper._cyreg ? wrapper._cyreg.cy : null;
    }

    // The layout on screen, per canvas: the Cytoscape instance it was built
    // on, the view it belongs to, its topology signature, and the id of the
    // newest request.
    var screens = {};

    function screenFor(key) {
        if (!screens[key]) {
            screens[key] = { cy: null, root: undefined, signature: undefined, sequence: 0 };
        }
        return screens[key];
    }

    // The signature describes one live Cytoscape instance, not the wrapper
    // DOM node. Dash can replace the instance during a remount or hot reload.
    // Forget the layout on that boundary, or the replacement's first elements
    // update would look like an echo and leave its nodes stacked at
    // Cytoscape's default origin.
    function adopt(screen, cy) {
        if (!cy || screen.cy === cy) return;
        screen.cy = cy;
        screen.root = undefined;
        screen.signature = undefined;
    }

    // request() lays out an elements update only when its view or its nodes
    // and edges differ from the layout already on screen. settleUnchanged()
    // asks the same question, so the two can never disagree about whether a
    // layout is coming.
    function matchesScreen(screen, root, signature) {
        return screen.root === root && screen.signature === signature;
    }

    // A request carries two things only this app understands. They are
    // resolved here, as dash-cytoscape hands the prop to cy.layout(), which it
    // does for every layout it starts.
    //
    // skillTreeTween asks CoSE for a final-position tween. CoSE's own
    // animate:true repaints the physics as it runs, and holds those repaints
    // back for animationThreshold (250 ms). A small view converged inside that
    // window, so it snapped into place with no visible motion. animate:'end'
    // tweens from the starting positions to the computed ones, the same path
    // fCoSE animates through. The prop can't carry 'end' itself:
    // dash-cytoscape declares layout.animate a boolean, and Dash's prop check
    // in debug mode tears the canvas down over a string.
    //
    // A randomized request is randomized once. autoRefreshLayout re-runs the
    // prop Nodes holds on every add or remove, and those re-runs are
    // transitions. Otherwise every filter change after a Settle would
    // reshuffle the whole graph.
    function resolveRequestOptions(cy) {
        if (!cy || typeof cy.layout !== 'function' || cy._skillTreeRequestOptions) return;
        cy._skillTreeRequestOptions = true;
        var layout = cy.layout;
        var randomizedRequest = null;
        cy.layout = function (options) {
            if (options && options.skillTreeRequestId !== undefined) {
                options = Object.assign({}, options);
                if (options.skillTreeTween && options.animate === true) {
                    options.animate = 'end';
                }
                if (options.randomize === true) {
                    if (randomizedRequest === options.skillTreeRequestId) {
                        options.randomize = false;
                    } else {
                        randomizedRequest = options.skillTreeRequestId;
                    }
                }
            }
            return layout.call(cy, options);
        };
    }

    function layoutOptions(policy, controls, nodeCount, randomize) {
        var name = policy.smallViewsUseCose && nodeCount <= SMALL_VIEW_NODES
            ? 'cose' : 'fcose';
        var animate = Boolean(controls.animate);
        var layout = {
            name: name,
            animate: animate,
            // CoSE leaves this undefined, which Cytoscape reads as 400 ms.
            // State it so every view runs at fCoSE's pace.
            animationDuration: 1000,
            fit: true,
            randomize: randomize,
            padding: policy.padding,
            idealEdgeLength: controls.edgeLength || policy.physics.edgeLength,
            nodeRepulsion: controls.repulsion || policy.physics.repulsion,
            gravity: controls.gravity !== null && controls.gravity !== undefined
                ? controls.gravity : policy.physics.gravity,
            numIter: policy.scaleIterations
                ? Math.max(500, Math.min(2500, nodeCount * 25)) : 2500
        };
        if (name === 'fcose') layout.quality = 'proof';
        // fCoSE's animate:true already tweens to the final positions. CoSE
        // has to be asked; see resolveRequestOptions.
        if (name === 'cose' && animate) layout.skillTreeTween = true;
        return layout;
    }

    function request(canvas, controls) {
        var noUpdate = window.dash_clientside.no_update;
        var policy = policyFor(canvas.key);
        var triggered = triggerId();
        var isSettle = triggered === canvas.settleButtonId;
        var isElementsUpdate = canvas.laysOutElements && triggered === canvas.cytoscapeId;

        // While frozen, only the user's explicit Settle may move the graph.
        // freeze_positions.js applies element deltas in place. Control changes
        // wait for the freeze-off transition, whose request lays the graph out
        // with them.
        if (controls.frozen && !isSettle) return noUpdate;

        var screen = screenFor(canvas.key);
        var cy = liveCy(canvas);
        adopt(screen, cy);
        resolveRequestOptions(cy);

        var newView = false;
        if (isElementsUpdate) {
            var root = policy.rootFromElements
                ? viewRoot(controls.elements, controls.view)
                : controls.view;
            var signature = topologySignature(controls.elements);
            if (matchesScreen(screen, root, signature)) {
                // Same nodes and edges: dash-cytoscape's positional echo, or
                // a server payload the filters left unchanged. Neither is a
                // new graph. settleUnchanged() releases Details' simulation
                // for the second.
                return noUpdate;
            }
            newView = screen.root !== root;
            screen.root = root;
            screen.signature = signature;
        }

        if (isSettle && SkillTree.allowOneLayout) SkillTree.allowOneLayout(canvas.key);

        // An elements update is sized by its payload, which Cytoscape may not
        // have received yet. Every other request lays out what is on screen,
        // which a frozen canvas may have changed without touching the prop.
        var nodeCount = isElementsUpdate || !cy
            ? countNodes(controls.elements)
            : cy.nodes().length;

        // A new view needs a randomized seed. Same-view topology changes,
        // control changes and the freeze-off transition stay incremental, to
        // preserve the mental map.
        var layout = layoutOptions(policy, controls, nodeCount, isSettle || newView);

        // dash-cytoscape starts a layout only when this prop changes, and two
        // requests can produce byte-for-byte identical options, such as two
        // small views that both clamp to 500 iterations. The id keeps every
        // accepted request distinct. Cytoscape ignores the namespaced option.
        screen.sequence += 1;
        layout.skillTreeRequestId = screen.sequence;
        return layout;
    }

    function settleUnchanged(canvas, pending, frozen, view) {
        var noUpdate = window.dash_clientside.no_update;
        // A frozen canvas already bypasses the simulation's layout gate.
        if (frozen || !Array.isArray(pending)) return noUpdate;
        var screen = screenFor(canvas.key);
        var root = policyFor(canvas.key).rootFromElements
            ? viewRoot(pending, view)
            : view;
        if (!root) return noUpdate;
        // A replacement instance has lost its signature; request() will lay
        // this payload out.
        var cy = liveCy(canvas);
        if (cy && screen.cy !== cy) return noUpdate;
        if (!matchesScreen(screen, root, topologySignature(pending))) return noUpdate;
        // An earlier payload's layout is still running. Its own settle
        // releases the simulation; releasing now would start sampling inside
        // the animation.
        if (SkillTree.detailsLayoutSettling && SkillTree.detailsLayoutSettling()) {
            return noUpdate;
        }
        return JSON.stringify({ root: root, settledAt: Date.now() });
    }

    var api = window.dash_clientside.skillTreeLayout = {};

    // Positional arguments follow the Inputs and State that
    // _register_layout_callback gives each canvas.
    SkillTree.canvases.forEach(function (canvas) {
        api[canvas.key] = canvas.laysOutElements
            ? function (edgeLength, gravity, repulsion, animate, settleClicks,
                        elements, frozen, view) {
                return request(canvas, {
                    edgeLength: edgeLength, gravity: gravity, repulsion: repulsion,
                    animate: animate, elements: elements, frozen: frozen, view: view
                });
            }
            : function (edgeLength, gravity, repulsion, animate, settleClicks, frozen) {
                return request(canvas, {
                    edgeLength: edgeLength, gravity: gravity, repulsion: repulsion,
                    animate: animate, frozen: frozen
                });
            };
    });

    /**
     * Release Details' Time Simulation for a payload that will not be laid out.
     *
     * Layout-affecting inputs hold the simulation until the layout they cause
     * settles. An input that changes nothing in this subtree — a context with
     * no nodes here, a depth past its deepest branch — sends back the same
     * nodes and edges, request() starts no layout, and that settle never
     * comes. This runs alongside the elements forward, before request()
     * records the payload, so it still compares against the layout on screen.
     * Returns the settled token, or no_update.
     */
    api.settleUnchanged = function (pending, frozen, root) {
        return settleUnchanged(canvasFor('details'), pending, frozen, root);
    };

    // The view a canvas's layout on screen was built for.
    // details_deferred_subtasks.js scopes its releases to it.
    SkillTree.layoutRoot = function (key) {
        return screens[key] ? screens[key].root : undefined;
    };

    function watchCanvases() {
        if (!SkillTree.onCytoReady) return;
        SkillTree.canvases.forEach(function (canvas) {
            SkillTree.onCytoReady('#' + canvas.cytoscapeId, function (cy) {
                adopt(screenFor(canvas.key), cy);
                resolveRequestOptions(cy);
            });
        });
    }

    // The page's scripts are still loading, and cyto_lifecycle.js among them.
    if (typeof document !== 'undefined' && document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watchCanvases);
    } else {
        watchCanvases();
    }
})();
