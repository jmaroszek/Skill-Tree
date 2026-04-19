/**
 * "Locate on graph" animation helper.
 *
 * Exposes `window.locateNodeOnGraph(nodeName, canvasId)` which finds the
 * given node on a Cytoscape canvas and runs a size+border pulse for
 * ~1.5 seconds. `canvasId` defaults to the main canvas ('cytoscape-graph');
 * pass 'details-mini-graph' (or any other Cytoscape wrapper DOM id) to
 * target an embedded mini-graph instead.
 */
(function () {

    var PULSE_SCALE = 3;
    var PULSE_EXPAND_MS = 350;
    var PULSE_HOLD_MS = 700;
    var PULSE_CONTRACT_MS = 400;
    var PAN_DURATION_MS = 400;
    var MIN_ZOOM = 1.5;

    function getCyInstance(canvasId) {
        var wrapper = document.getElementById(canvasId);
        if (!wrapper || !wrapper._cyreg || !wrapper._cyreg.cy) return null;
        return wrapper._cyreg.cy;
    }

    function runPulse(node) {
        var originalW = node.width();
        var originalH = node.height();
        node.addClass('locate-pulse');

        node.animate(
            { style: { 'width': originalW * PULSE_SCALE, 'height': originalH * PULSE_SCALE } },
            {
                duration: PULSE_EXPAND_MS,
                complete: function () {
                    setTimeout(function () {
                        node.animate(
                            { style: { 'width': originalW, 'height': originalH } },
                            {
                                duration: PULSE_CONTRACT_MS,
                                complete: function () {
                                    node.removeClass('locate-pulse');
                                    node.removeStyle('width');
                                    node.removeStyle('height');
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

        runPulse(node);
    }

    window.locateNodeOnGraph = function (nodeName, canvasId) {
        if (!nodeName) return;
        canvasId = canvasId || 'cytoscape-graph';
        // Small delay allows any in-progress tab switch to mount the canvas first.
        setTimeout(function () { tryLocate(nodeName, canvasId, 0); }, 50);
    };
})();
