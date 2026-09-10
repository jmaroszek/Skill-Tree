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
    var MIN_ZOOM = 1.5;
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
        if (!wrapper || !wrapper._cyreg || !wrapper._cyreg.cy) return null;
        return wrapper._cyreg.cy;
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

    function tryLocate(nodeName, canvasId, attempt) {
        attempt = attempt || 0;
        var cy = getCyInstance(canvasId);
        if (!cy) {
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

        runPulse(node, canvasId);
    }

    window.locateNodeOnGraph = function (nodeName, canvasId) {
        if (!nodeName) return;
        canvasId = canvasId || 'cytoscape-graph';
        // Small delay allows any in-progress tab switch to mount the canvas first.
        setTimeout(function () { tryLocate(nodeName, canvasId, 0); }, 50);
    };
})();
