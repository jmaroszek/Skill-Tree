/**
 * Freeze-rerender: preserve node positions and viewport during freeze,
 * across multiple independent Cytoscape canvases (main / details / events).
 *
 * Each canvas gets its own state bundle (frozen flag, position lock, viewport
 * lock, interaction flags) keyed by a short canvas id. Dash wires up per-canvas
 * clientside callbacks that dispatch to this module by id.
 *
 * The guard mechanics (layoutstart interception, pan/zoom revert, monkey-
 * patched cy.fit/center/reset, applyDelta for direct cy mutation, DOM
 * listeners on cy.container() in capture phase) are identical to the
 * single-canvas version — just multiplied.
 */
(function () {
    if (!window.SkillTree) window.SkillTree = {};
    if (window.SkillTree.registerCanvas) return;

    // registry: { [canvasId]: CanvasState }
    var registry = Object.create(null);

    function makeState(canvasId, cytoscapeElementId) {
        return {
            canvasId: canvasId,
            cytoscapeElementId: cytoscapeElementId,
            frozen: false,
            lockedPositions: {},
            lockedZoom: 1,
            lockedPan: { x: 0, y: 0 },
            inProgrammatic: false,
            userInteracting: false,
            wheelDebounceTimer: null,
            allowNextLayout: false,
            bypassFreeze: false,
            boundCy: null,
            originals: { fit: null, center: null, reset: null },
            domBound: false,
        };
    }

    function getCy(state) {
        var el = document.querySelector('#' + state.cytoscapeElementId);
        return (el && el._cyreg && el._cyreg.cy) ? el._cyreg.cy : null;
    }

    function captureAll(state, cy) {
        state.lockedPositions = {};
        cy.nodes().forEach(function (n) {
            var p = n.position();
            state.lockedPositions[n.id()] = { x: p.x, y: p.y };
        });
        state.lockedZoom = cy.zoom();
        var pan = cy.pan();
        state.lockedPan = { x: pan.x, y: pan.y };
    }

    function captureViewport(state, cy) {
        state.lockedZoom = cy.zoom();
        var pan = cy.pan();
        state.lockedPan = { x: pan.x, y: pan.y };
    }

    function withProgrammatic(state, fn) {
        var prev = state.inProgrammatic;
        state.inProgrammatic = true;
        try { fn(); }
        finally {
            state.inProgrammatic = prev;
            if (!prev) {
                setTimeout(function () { state.inProgrammatic = false; }, 0);
            }
        }
    }

    function restoreAll(state, cy) {
        if (!cy || !state.frozen) return;
        withProgrammatic(state, function () {
            cy.batch(function () {
                cy.nodes().forEach(function (n) {
                    var locked = state.lockedPositions[n.id()];
                    if (!locked) return;
                    var p = n.position();
                    if (Math.abs(p.x - locked.x) > 0.01 || Math.abs(p.y - locked.y) > 0.01) {
                        n.position(locked);
                    }
                });
                cy.viewport({ zoom: state.lockedZoom, pan: { x: state.lockedPan.x, y: state.lockedPan.y } });
            });
        });
    }

    function restoreViewport(state, cy) {
        if (!cy || !state.frozen) return;
        withProgrammatic(state, function () {
            cy.viewport({ zoom: state.lockedZoom, pan: { x: state.lockedPan.x, y: state.lockedPan.y } });
        });
    }

    function bindDOMListeners(state, cy) {
        if (state.domBound) return;
        var c = cy.container && cy.container();
        if (!c) return;
        state.domBound = true;

        c.addEventListener('mousedown', function () {
            if (state.frozen) state.userInteracting = true;
        }, true);
        c.addEventListener('mouseup', function () {
            if (!state.frozen) return;
            state.userInteracting = false;
            captureViewport(state, cy);
        }, true);
        c.addEventListener('mouseleave', function () {
            if (!state.frozen) return;
            if (state.userInteracting) captureViewport(state, cy);
            state.userInteracting = false;
        }, true);
        c.addEventListener('wheel', function () {
            if (!state.frozen) return;
            state.userInteracting = true;
            if (state.wheelDebounceTimer) clearTimeout(state.wheelDebounceTimer);
            state.wheelDebounceTimer = setTimeout(function () {
                state.userInteracting = false;
                captureViewport(state, cy);
            }, 300);
        }, true);
    }

    function bindGuards(state, cy) {
        if (state.boundCy === cy) return;
        state.boundCy = cy;

        if (state.originals.fit === null) {
            state.originals.fit = cy.fit.bind(cy);
            cy.fit = function () {
                if (state.frozen && !state.bypassFreeze) return cy;
                return state.originals.fit.apply(null, arguments);
            };
        }
        if (state.originals.center === null) {
            state.originals.center = cy.center.bind(cy);
            cy.center = function () {
                if (state.frozen && !state.bypassFreeze) return cy;
                return state.originals.center.apply(null, arguments);
            };
        }
        if (state.originals.reset === null) {
            state.originals.reset = cy.reset.bind(cy);
            cy.reset = function () {
                if (state.frozen && !state.bypassFreeze) return cy;
                return state.originals.reset.apply(null, arguments);
            };
        }

        cy.on('layoutstart', function (evt) {
            if (!state.frozen) return;
            if (state.allowNextLayout) {
                state.allowNextLayout = false;
                state.bypassFreeze = true;
                return;
            }
            try { if (evt.layout && evt.layout.stop) evt.layout.stop(); } catch (e) { /* best effort */ }
        });

        cy.on('layoutstop', function () {
            if (!state.frozen) return;
            if (state.bypassFreeze) {
                state.bypassFreeze = false;
                captureAll(state, cy);
                return;
            }
            restoreAll(state, cy);
        });

        cy.on('position', 'node', function (evt) {
            if (!state.frozen || state.inProgrammatic || state.bypassFreeze) return;
            // Active user drag — let position events through so the node tracks
            // the cursor. dragfree captures the final position into
            // lockedPositions on release. `:grabbed` (not just evt.target.grabbed())
            // catches grouped drag, where siblings move alongside the grabbed node.
            if (cy.$(':grabbed').length > 0) return;
            var n = evt.target;
            var locked = state.lockedPositions[n.id()];
            if (!locked) return;
            var p = n.position();
            if (Math.abs(p.x - locked.x) > 0.01 || Math.abs(p.y - locked.y) > 0.01) {
                withProgrammatic(state, function () { n.position(locked); });
            }
        });

        cy.on('pan zoom', function () {
            if (!state.frozen || state.inProgrammatic || state.userInteracting || state.bypassFreeze) return;
            restoreViewport(state, cy);
        });

        cy.on('dragfree', 'node', function (evt) {
            if (!state.frozen) return;
            var n = evt.target;
            var p = n.position();
            state.lockedPositions[n.id()] = { x: p.x, y: p.y };
        });

        bindDOMListeners(state, cy);
    }

    // --- Public API ---------------------------------------------------
    window.SkillTree.registerCanvas = function (canvasId, cytoscapeElementId) {
        if (registry[canvasId]) return;
        registry[canvasId] = makeState(canvasId, cytoscapeElementId);
    };

    window.SkillTree.setFreezeActive = function (canvasId, active) {
        var state = registry[canvasId];
        if (!state) return;
        var prev = state.frozen;
        state.frozen = Boolean(active);
        var cy = getCy(state);
        if (!cy) return;
        bindGuards(state, cy);
        if (state.frozen && !prev) {
            captureAll(state, cy);
        } else if (!state.frozen && prev) {
            // Freeze just turned off — deterministic fcose refresh.
            requestAnimationFrame(function () {
                try {
                    cy.layout({
                        name: 'fcose',
                        quality: 'proof',
                        fit: true,
                        animate: true,
                        randomize: false,
                        idealEdgeLength: 100,
                        nodeRepulsion: 4500,
                        gravity: 0.25,
                        numIter: 2500,
                    }).run();
                } catch (e) { /* best effort */ }
            });
        }
    };

    window.SkillTree.isFrozen = function (canvasId) {
        var state = registry[canvasId];
        return state ? state.frozen : false;
    };

    window.SkillTree.allowOneLayout = function (canvasId) {
        var state = registry[canvasId];
        if (state) state.allowNextLayout = true;
    };

    function pickInitialPosition(state, nodeId, neighborIdsById) {
        // Place a new node at the centroid of its already-locked neighbors so
        // it appears near its connections instead of at Cytoscape's default
        // (which lands new nodes near 0,0 and visually "swirls" the layout).
        var neighborIds = neighborIdsById[nodeId] || [];
        var sumX = 0, sumY = 0, count = 0;
        for (var i = 0; i < neighborIds.length; i++) {
            var p = state.lockedPositions[neighborIds[i]];
            if (p) { sumX += p.x; sumY += p.y; count++; }
        }
        if (count > 0) return { x: sumX / count, y: sumY / count };
        // No locked neighbors — fall back to centroid of all locked nodes.
        var ids = Object.keys(state.lockedPositions);
        if (ids.length > 0) {
            sumX = 0; sumY = 0;
            for (var j = 0; j < ids.length; j++) {
                sumX += state.lockedPositions[ids[j]].x;
                sumY += state.lockedPositions[ids[j]].y;
            }
            return { x: sumX / ids.length, y: sumY / ids.length };
        }
        return { x: 0, y: 0 };
    }

    window.SkillTree.applyDelta = function (canvasId, newElements) {
        var state = registry[canvasId];
        if (!state) return;
        var cy = getCy(state);
        if (!cy || !Array.isArray(newElements)) return;

        var nextById = Object.create(null);
        var neighborIdsById = Object.create(null);
        newElements.forEach(function (el) {
            if (!el || !el.data || el.data.id == null) return;
            nextById[el.data.id] = el;
            // Edges carry source+target; record both directions so a new node
            // can find its already-positioned neighbors regardless of direction.
            if (el.data.source != null && el.data.target != null) {
                var s = el.data.source, t = el.data.target;
                (neighborIdsById[s] = neighborIdsById[s] || []).push(t);
                (neighborIdsById[t] = neighborIdsById[t] || []).push(s);
            }
        });

        withProgrammatic(state, function () {
            cy.batch(function () {
                // Phase 1: collect ids to remove. Don't mutate cy.elements()
                // during iteration — the live collection silently skips
                // entries otherwise.
                var idsToRemove = [];
                cy.elements().forEach(function (el) {
                    if (!(el.id() in nextById)) idsToRemove.push(el.id());
                });
                // Phase 2: remove.
                idsToRemove.forEach(function (id) {
                    var el = cy.getElementById(id);
                    if (el && el.length) el.remove();
                });
                // Phase 3: add or update.
                Object.keys(nextById).forEach(function (id) {
                    var newEl = nextById[id];
                    var existing = cy.getElementById(id);
                    if (existing.length === 0) {
                        var cloned = JSON.parse(JSON.stringify(newEl));
                        var isNode = !(cloned.data && cloned.data.source);
                        if (isNode && !cloned.position) {
                            var pos = state.lockedPositions[id]
                                || pickInitialPosition(state, id, neighborIdsById);
                            // Write back so subsequent applyDelta calls see this
                            // node as locked — otherwise we'd re-pick a new
                            // position every edit and the node would drift.
                            state.lockedPositions[id] = { x: pos.x, y: pos.y };
                            cloned.position = { x: pos.x, y: pos.y };
                        }
                        try { cy.add(cloned); } catch (e) { /* best effort */ }
                    } else {
                        existing.data(newEl.data || {});
                        var raw = newEl.classes;
                        var str = Array.isArray(raw) ? raw.join(' ') : (raw || '');
                        var target = str.toString().split(/\s+/).filter(Boolean);
                        existing.classes(target);
                    }
                });
            });
        });
    };

    // Handle cy lifecycle (initial mount + any instance swap by dash-cytoscape)
    // via the shared onCytoReady hook — event-driven, no polling.
    function onCySwap(canvasId, cy) {
        var state = registry[canvasId];
        if (!state || state.boundCy === cy) return;
        state.boundCy = null;
        state.domBound = false;
        bindGuards(state, cy);
        if (state.frozen) captureAll(state, cy);
    }

    function registerAll() {
        window.SkillTree.registerCanvas('main', 'cytoscape-graph');
        window.SkillTree.registerCanvas('details', 'details-mini-graph');
        window.SkillTree.registerCanvas('events', 'events-detail-graph');
        if (window.SkillTree.onCytoReady) {
            window.SkillTree.onCytoReady('#cytoscape-graph',     function (cy) { onCySwap('main', cy); });
            window.SkillTree.onCytoReady('#details-mini-graph',  function (cy) { onCySwap('details', cy); });
            window.SkillTree.onCytoReady('#events-detail-graph', function (cy) { onCySwap('events', cy); });
        }
    }
    registerAll();
})();
