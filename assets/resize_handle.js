/**
 * Draggable resize handle between the canvas and bottom panel.
 * Drag up/down to adjust the split between the graph canvas and the info panel.
 */
(function () {
    'use strict';

    var MIN_PANEL_HEIGHT = 150;
    var MAX_PANEL_RATIO = 0.6;

    function init() {
        var handle = document.getElementById('resize-handle');
        var panel = document.getElementById('bottom-panel-container');
        if (!handle || !panel) {
            // Dash hasn't rendered yet — retry shortly
            setTimeout(init, 200);
            return;
        }

        var dragging = false;
        var startY = 0;
        var startHeight = 0;

        handle.addEventListener('mousedown', function (e) {
            e.preventDefault();
            dragging = true;
            startY = e.clientY;
            startHeight = panel.offsetHeight;
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', function (e) {
            if (!dragging) return;
            var delta = startY - e.clientY;
            var maxHeight = window.innerHeight * MAX_PANEL_RATIO;
            var newHeight = Math.min(maxHeight, Math.max(MIN_PANEL_HEIGHT, startHeight + delta));
            panel.style.height = newHeight + 'px';
        });

        document.addEventListener('mouseup', function () {
            if (!dragging) return;
            dragging = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';

            // Tell Cytoscape to recalculate its viewport
            var cyEl = document.getElementById('cytoscape-graph');
            if (cyEl && cyEl._cyreg && cyEl._cyreg.cy) {
                cyEl._cyreg.cy.resize();
            }
        });
    }

    // Start trying once the page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
