/**
 * "Locate on graph" animation helper.
 *
 * Exposes `window.locateNodeOnGraph(nodeName, canvasId)` which finds the
 * given node on a Cytoscape canvas and runs a size+border pulse for
 * ~1.5 seconds. `canvasId` defaults to the main canvas ('cytoscape-graph');
 * pass 'details-mini-graph' (or any other Cytoscape wrapper DOM id) to
 * target an embedded mini-graph instead.
 *
 * Two Cytoscape details make this more than a pair of animate() calls, and
 * both bite hardest on a Now node, where now_pulse.js keeps an endless
 * border animation running:
 *
 *   - animate() queues behind whatever is already animating on the element
 *     unless `queue: false` is passed. Without it the pulse takes turns with
 *     the Now border loop, waiting out a half-cycle before each half of its
 *     own — which is what made the animation look choppy.
 *   - a *queued* animation is discarded outright by stop(clearQueue), and a
 *     discarded animation never runs its `complete` callback. That callback
 *     was the only thing clearing the inline width/height, so an interrupted
 *     pulse left the node stranded at three times its size. The size is now
 *     cleared by a timer that fires regardless of what becomes of the
 *     animations.
 */
(function () {
    if (!window.SkillTree) window.SkillTree = {};

    var PULSE_SCALE = 3;
    var PULSE_EXPAND_MS = 350;
    var PULSE_HOLD_MS = 700;
    var PULSE_CONTRACT_MS = 400;
    var PAN_DURATION_MS = 400;
    var VIEWPORT_MARGIN = 24;
    // Comfortably past expand + hold + contract, so the safety net only ever
    // fires for a pulse that was interrupted and never races a healthy one.
    var PULSE_CLEANUP_MS =
        PULSE_EXPAND_MS + PULSE_HOLD_MS + PULSE_CONTRACT_MS + 600;

    // "canvasId|nodeId" -> the run currently pulsing that node. Doubles as the
    // flag now_pulse.js checks before force-stopping a node's animations.
    var active = Object.create(null);

    function key(canvasId, nodeId) {
        return canvasId + '|' + nodeId;
    }

    window.SkillTree.isLocating = function (canvasId, nodeId) {
        return Object.prototype.hasOwnProperty.call(
            active, key(canvasId, nodeId));
    };

    function getCyInstance(canvasId) {
        var wrapper = document.getElementById(canvasId);
        return window.SkillTree.getCy(wrapper);
    }

    function canvasIsEmpty(canvasId) {
        var cy = getCyInstance(canvasId);
        if (!cy) return true;
        return typeof cy.nodes === 'function' && cy.nodes().length === 0;
    }

    window.SkillTree.canvasHasNode = function (canvasId, nodeName) {
        var cy = getCyInstance(canvasId);
        if (!cy || !nodeName) return false;
        var node = cy.getElementById(nodeName);
        return Boolean(node && node.length > 0);
    };

    function bringIntoViewIfNeeded(cy, node, canvasId) {
        if (!cy || !node || typeof node.renderedBoundingBox !== 'function' ||
                typeof cy.width !== 'function' || typeof cy.height !== 'function') {
            return;
        }
        var box = node.renderedBoundingBox();
        var width = cy.width();
        var height = cy.height();
        var visible = box.x1 >= VIEWPORT_MARGIN && box.y1 >= VIEWPORT_MARGIN &&
            box.x2 <= width - VIEWPORT_MARGIN &&
            box.y2 <= height - VIEWPORT_MARGIN;
        if (visible) return;

        if (window.SkillTree &&
                typeof window.SkillTree.centerCanvasOnNode === 'function') {
            window.SkillTree.centerCanvasOnNode(canvasId, node, PAN_DURATION_MS);
        } else if (typeof cy.animate === 'function') {
            cy.animate({ center: { eles: node } }, { duration: PAN_DURATION_MS });
        } else if (typeof cy.center === 'function') {
            cy.center(node);
        }
    }

    function clearTimers(run) {
        if (run.holdTimer !== null) clearTimeout(run.holdTimer);
        if (run.cleanupTimer !== null) clearTimeout(run.cleanupTimer);
        run.holdTimer = null;
        run.cleanupTimer = null;
    }

    function finish(node, canvasId, run) {
        var k = key(canvasId, node.id());
        if (active[k] !== run) return;
        clearTimers(run);
        delete active[k];
        // The element can be gone if the graph was regenerated mid-pulse.
        try {
            node.removeClass('locate-pulse');
            node.removeStyle('width');
            node.removeStyle('height');
        } catch (e) { /* nothing left to clear */ }
    }

    function runPulse(node, canvasId) {
        var k = key(canvasId, node.id());
        var previous = active[k];
        if (previous) {
            // Locate clicked again mid-pulse. Retire the old run's timers and
            // drop its inline size so the base dimensions below read off the
            // stylesheet rather than off a half-finished animation.
            clearTimers(previous);
            delete active[k];
            try {
                node.removeStyle('width');
                node.removeStyle('height');
            } catch (e) { /* ignore */ }
        }

        var originalW = node.width();
        var originalH = node.height();
        var run = {holdTimer: null, cleanupTimer: null};
        active[k] = run;

        // Runs whatever becomes of the animations below — including the case
        // where another script stops or discards them.
        run.cleanupTimer = setTimeout(function () {
            finish(node, canvasId, run);
        }, PULSE_CLEANUP_MS);

        node.addClass('locate-pulse');
        node.animate(
            { style: { 'width': originalW * PULSE_SCALE, 'height': originalH * PULSE_SCALE } },
            {
                duration: PULSE_EXPAND_MS,
                queue: false,
                complete: function () {
                    if (active[k] !== run) return;
                    run.holdTimer = setTimeout(function () {
                        run.holdTimer = null;
                        if (active[k] !== run) return;
                        node.animate(
                            { style: { 'width': originalW, 'height': originalH } },
                            {
                                duration: PULSE_CONTRACT_MS,
                                queue: false,
                                complete: function () {
                                    finish(node, canvasId, run);
                                },
                            }
                        );
                    }, PULSE_HOLD_MS);
                },
            }
        );
    }

    function isMainCanvas(canvasId) {
        var registry = window.SkillTree.canvases || [];
        return registry.some(function (item) {
            return item.key === 'main' && item.cytoscapeId === canvasId;
        });
    }

    // The Nodes canvas loads on its first visit and lays out behind its
    // first-paint cover. A pulse before that would be spent on nodes still
    // piled at the origin, or on no nodes at all.
    var FIRST_PAINT_WAIT_TRIES = 150;  // 15 s, the first-paint cover's backstop

    function tryLocate(nodeName, canvasId, attempt, firstPaintWaits) {
        attempt = attempt || 0;
        firstPaintWaits = firstPaintWaits || 0;
        var paint = window.SkillTree.canvasFirstPaintDone;
        if (isMainCanvas(canvasId) && typeof paint === 'function' && !paint()
                && firstPaintWaits < FIRST_PAINT_WAIT_TRIES) {
            setTimeout(function () {
                tryLocate(nodeName, canvasId, attempt, firstPaintWaits + 1);
            }, 100);
            return;
        }
        var cy = getCyInstance(canvasId);
        if (!cy) {
            if (attempt < 20) setTimeout(function () { tryLocate(nodeName, canvasId, attempt + 1); }, 100);
            return;
        }
        // A just-opened tab can have its nodes before Cytoscape has a usable
        // viewport. Wait for visibility so the pulse and any recentering are
        // not spent on a zero-sized hidden canvas.
        if (typeof cy.width === 'function' && typeof cy.height === 'function' &&
                (cy.width() <= 0 || cy.height() <= 0)) {
            if (attempt < 20) setTimeout(function () { tryLocate(nodeName, canvasId, attempt + 1); }, 100);
            return;
        }
        var node = cy.getElementById(nodeName);
        if (!node || node.length === 0) {
            // Node may not yet be in the stylesheet-rendered elements (tab
            // just switched). Retry a few times.
            if (attempt < 20) setTimeout(function () { tryLocate(nodeName, canvasId, attempt + 1); }, 100);
            return;
        }

        bringIntoViewIfNeeded(cy, node, canvasId);
        runPulse(node, canvasId);
    }

    window.locateNodeOnGraph = function (nodeName, canvasId) {
        if (!nodeName) return;
        canvasId = canvasId || 'cytoscape-graph';
        // Small delay allows any in-progress tab switch to mount the canvas first.
        setTimeout(function () { tryLocate(nodeName, canvasId, 0); }, 50);
    };

    window.SkillTree.resolveLocateRequest = function (request) {
        var registry = window.SkillTree.canvases || [];
        var canvas = registry.find(function (item) {
            return item.tabId === request.activeTab;
        });
        var needsNavigation = false;
        if (!canvas) {
            canvas = registry.find(function (item) { return item.key === 'main'; });
            needsNavigation = true;
        }
        // The Nodes canvas loads on its first visit. Before then it has no
        // nodes at all, which says nothing about this one; the server has
        // already checked that it exists.
        var unloaded = needsNavigation && canvas && canvasIsEmpty(canvas.cytoscapeId);
        if (!canvas || (!unloaded && !window.SkillTree.canvasHasNode(
                canvas.cytoscapeId, request.name))) {
            return {
                status: 'missing', name: request.name, request: request.request,
                view: canvas ? canvas.key : 'canvas',
                canvasId: canvas ? canvas.cytoscapeId : null
            };
        }
        if (!needsNavigation) {
            window.locateNodeOnGraph(request.name, canvas.cytoscapeId);
        }
        return {
            status: needsNavigation ? 'navigate' : 'located',
            name: request.name, request: request.request,
            view: canvas.key, canvasId: canvas.cytoscapeId,
            targetTab: canvas.tabId
        };
    };
})();
