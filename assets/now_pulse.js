/**
 * Continuous border-width pulse for `.now` nodes on every Cytoscape canvas.
 *
 * Pattern mirrors `locate_node.js`: walk each canvas, find matching nodes,
 * drive a recursive `.animate()` loop. Differences from locate:
 *   - persistent (every Now node pulses for as long as the class is set)
 *   - per-node self-termination via `hasClass('now')` check on each cycle
 *   - keyed registry to avoid double-starting the same node
 *
 * A 1s periodic scan picks up newly-flagged-Now nodes after element updates
 * without requiring an explicit clientside-callback hook. The cost is trivial
 * (three cy lookups + a forEach per second).
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

    var pulsing = new Set();  // keys: "canvasId|nodeId"

    function getCyInstance(canvasId) {
        var wrapper = document.getElementById(canvasId);
        if (!wrapper || !wrapper._cyreg || !wrapper._cyreg.cy) return null;
        return wrapper._cyreg.cy;
    }

    function cleanupNode(node) {
        // Force-stop any in-flight animations and clear the inline border
        // override. Cytoscape's class-removal alone is not enough: the
        // animate() call sets border-width as an inline style override that
        // persists until removeStyle.
        try { node.stop(true, true); } catch (e) {}
        try { node.removeStyle('border-width'); } catch (e) {}
    }

    function pulseStep(node, canvasId, expanding) {
        var key = canvasId + '|' + node.id();
        // Class removed (user cleared Now, or elements regenerated without it)?
        // Exit the loop and clear any inline override so the static rule resumes.
        if (!node.hasClass('now')) {
            pulsing.delete(key);
            cleanupNode(node);
            return;
        }
        var target = expanding ? BORDER_MAX : BORDER_MIN;
        node.animate(
            { style: { 'border-width': target } },
            {
                duration: PULSE_HALF_DURATION_MS,
                easing: 'ease-in-out-sine',
                complete: function () {
                    pulseStep(node, canvasId, !expanding);
                },
            }
        );
    }

    function startPulse(node, canvasId) {
        var key = canvasId + '|' + node.id();
        if (pulsing.has(key)) return;
        pulsing.add(key);
        pulseStep(node, canvasId, true);
    }

    function scanCanvas(canvasId) {
        var cy = getCyInstance(canvasId);
        if (!cy) return;
        var now = cy.nodes('.now');
        var liveKeys = new Set();
        now.forEach(function (node) {
            liveKeys.add(canvasId + '|' + node.id());
            startPulse(node, canvasId);
        });
        // Drop stale registry entries for this canvas AND forcefully stop
        // any animation still running on the corresponding node. The
        // recursive pulseStep loop alone is unreliable if Cytoscape replaces
        // the element on re-render — the in-closure node reference may go
        // stale and the cleanup branch never fires. Doing it from the scan
        // closes that gap.
        Array.from(pulsing).forEach(function (key) {
            if (key.indexOf(canvasId + '|') === 0 && !liveKeys.has(key)) {
                pulsing.delete(key);
                var nodeId = key.substring(canvasId.length + 1);
                var node = cy.getElementById(nodeId);
                if (node && node.length) cleanupNode(node);
            }
        });
    }

    function scanAll() {
        CANVAS_IDS.forEach(scanCanvas);
    }

    setInterval(scanAll, SCAN_INTERVAL_MS);
})();
