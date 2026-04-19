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

        // Target canvas height — set CANVAS_HEIGHT in config.py to adjust.
        var configEl = document.getElementById('canvas-height-config');
        var TARGET_CANVAS_HEIGHT = configEl ? parseInt(configEl.dataset.height, 10) : 760;
        var siblings = Array.from(handle.parentElement.children);
        var otherHeight = siblings
            .filter(function (el) { return el !== panel && !el.classList.contains('flex-grow-1'); })
            .reduce(function (sum, el) { return sum + el.offsetHeight; }, 0);
        var initialPanelH = handle.parentElement.offsetHeight - otherHeight - TARGET_CANVAS_HEIGHT;
        panel.style.height = Math.max(MIN_PANEL_HEIGHT, initialPanelH) + 'px';

        handle.addEventListener('mousedown', function (e) {
            e.preventDefault();
            if (!window.SkillTree || !window.SkillTree.drag) return;
            var startY = e.clientY;
            var startHeight = panel.offsetHeight;
            var ticking = false; // Prevents layout thrashing

            window.SkillTree.drag.start({
                cursor: 'ns-resize',
                onMove: function (ev) {
                    if (ticking) return;
                    window.requestAnimationFrame(function () {
                        var delta = startY - ev.clientY;
                        var maxHeight = window.innerHeight * MAX_PANEL_RATIO;
                        var newHeight = Math.min(maxHeight, Math.max(MIN_PANEL_HEIGHT, startHeight + delta));
                        panel.style.height = newHeight + 'px';
                        ticking = false;
                    });
                    ticking = true;
                },
                onEnd: function () {
                    // Tell Cytoscape to recalculate its viewport
                    var cyEl = document.getElementById('cytoscape-graph');
                    if (cyEl && cyEl._cyreg && cyEl._cyreg.cy) {
                        cyEl._cyreg.cy.resize();
                    }
                },
            });
        });
    }

    // Start trying once the page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();