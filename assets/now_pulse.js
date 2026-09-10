/**
 * Continuous border-width pulse for `.now` nodes on every Cytoscape canvas.
 *
 * Pattern mirrors `locate_node.js`: walk each canvas, find matching nodes,
 * drive a recursive animation loop. Differences from locate:
 *   - persistent (every Now node pulses for as long as the class is set)
 *   - per-node self-termination via `hasClass('now')` check on each cycle
 *   - keyed registry to avoid double-starting the same node
 *   - pulses only on the canvas the user can actually see
 *
 * A short periodic scan (SCAN_INTERVAL_MS) picks up newly-flagged-Now nodes
 * after element updates without requiring an explicit clientside-callback
 * hook. The cost is trivial: three cy lookups plus a forEach over a tiny set.
 */
(function () {
    var CANVAS_IDS = ['cytoscape-graph', 'details-mini-graph', 'events-detail-graph'];
    // Half-period of the pulse: 1s up + 1s down = 2s full cycle.
    var PULSE_HALF_DURATION_MS = 1000;
    // Short scan interval so a Now-clear feels instant; the scan itself
    // is cheap (three lookups + a forEach on a tiny set).
    var SCAN_INTERVAL_MS = 250;
    var BORDER_MIN = 5;
    var BORDER_MAX = 7;

    // key "canvasId|nodeId" -> the run pulsing that node, holding the one
    // animation we own so it can be stopped without touching any other.
    var pulsing = new Map();

    function getCyInstance(canvasId) {
        var wrapper = document.getElementById(canvasId);
        if (!wrapper || !wrapper._cyreg || !wrapper._cyreg.cy) return null;
        return wrapper._cyreg.cy;
    }

    // All three canvases stay mounted at once — the inactive tabs are only
    // hidden by an ancestor's display:none. Cytoscape can't see that, so a
    // pulse left running on a hidden canvas keeps its animation ticking and
    // redrawing the full graph every frame, stealing time from whatever the
    // visible tab is animating. getClientRects() is empty for a display:none
    // subtree and non-empty for a fixed-position one, so it reads correctly
    // whether the canvas is off-tab or in fullscreen.
    function isCanvasVisible(canvasId) {
        var wrapper = document.getElementById(canvasId);
        return !!wrapper && wrapper.getClientRects().length > 0;
    }

    function cleanupNode(key, node) {
        // Stop ONLY the border animation this module started, never the whole
        // element. `node.stop()` reaches every animation on the node: it wipes
        // the queue without running those callbacks, and force-completes what
        // is currently running by setting its duration to 0. A layout's own
        // per-node position tween lives there, so a sweep landing mid-layout
        // used to snap that node straight to its final spot — and anything
        // waiting on the queue it cleared never heard back. Holding our own
        // Animation lets us stop exactly one.
        var run = pulsing.get(key);
        pulsing.delete(key);
        if (run && run.ani) {
            try { run.ani.stop(); } catch (e) {}
        }
        // The animation set border-width as an inline bypass, which outlives
        // the class. Clear it so the static rule takes over again.
        if (node) {
            try { node.removeStyle('border-width'); } catch (e) {}
        }
    }

    function pulseStep(node, canvasId, expanding) {
        var key = canvasId + '|' + node.id();
        var run = pulsing.get(key);
        if (!run) return;
        // Class removed (user cleared Now, or elements regenerated without it)?
        // Exit the loop and clear any inline override so the static rule resumes.
        if (!node.hasClass('now')) {
            cleanupNode(key, node);
            return;
        }
        var target = expanding ? BORDER_MAX : BORDER_MIN;
        // animation() rather than animate(): animate() queues behind whatever
        // is already running on the node, so during a layout tween the pulse
        // would wait out the tween instead of continuing through it.
        var ani = node.animation({
            style: { 'border-width': target },
            duration: PULSE_HALF_DURATION_MS,
            easing: 'ease-in-out-sine',
            complete: function () {
                if (pulsing.get(key) !== run) return;
                pulseStep(node, canvasId, !expanding);
            }
        });
        run.ani = ani;
        ani.play();
    }

    function startPulse(node, canvasId) {
        var key = canvasId + '|' + node.id();
        if (pulsing.has(key)) return;
        pulsing.set(key, { ani: null });
        pulseStep(node, canvasId, true);
    }

    function scanCanvas(canvasId) {
        var cy = getCyInstance(canvasId);
        if (!cy) return;
        // A hidden canvas is treated as having no Now nodes: nothing starts,
        // and the stale-key sweep below stops and clears anything still
        // running from when it was visible. Coming back into view, the next
        // scan finds the nodes again and restarts the pulse.
        var now = isCanvasVisible(canvasId) ? cy.nodes('.now') : cy.collection();
        var liveKeys = new Set();
        now.forEach(function (node) {
            liveKeys.add(canvasId + '|' + node.id());
            startPulse(node, canvasId);
        });
        // Drop stale registry entries for this canvas and stop the pulse we
        // started on each. The recursive pulseStep loop alone is unreliable if
        // Cytoscape replaces the element on re-render — the in-closure node
        // reference may go stale and the cleanup branch never fires. Doing it
        // from the scan closes that gap. The node may already be gone, in
        // which case there is no inline style left to clear.
        Array.from(pulsing.keys()).forEach(function (key) {
            if (key.indexOf(canvasId + '|') === 0 && !liveKeys.has(key)) {
                var nodeId = key.substring(canvasId.length + 1);
                var node = cy.getElementById(nodeId);
                cleanupNode(key, (node && node.length) ? node : null);
            }
        });
    }

    function scanAll() {
        CANVAS_IDS.forEach(scanCanvas);
    }

    setInterval(scanAll, SCAN_INTERVAL_MS);
})();
