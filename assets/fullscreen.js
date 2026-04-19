/**
 * Fullscreen toggle, scroll sensitivity, and right-click-to-pan for the Skill Tree canvas.
 *
 * Pure JS — no Dash callback needed.
 */
(function () {

    // --- Scroll sensitivity ---
    // Cytoscape's built-in zoom is disabled (userZoomingEnabled=False).
    // We handle wheel events ourselves with cy.zoom() for gradual control.
    var ZOOM_FACTOR = 1.1;  // per-tick multiplier (closer to 1 = slower)

    function initScrollSensitivity(selector) {
        var cyWrapper = document.querySelector(selector);
        if (!cyWrapper) {
            setTimeout(function() { initScrollSensitivity(selector); }, 300);
            return;
        }

        function getCy() {
            return (cyWrapper._cyreg && cyWrapper._cyreg.cy) ? cyWrapper._cyreg.cy : null;
        }

        cyWrapper.addEventListener('wheel', function (e) {
            e.preventDefault();
            var cy = getCy();
            if (!cy) return;

            var rect = cyWrapper.getBoundingClientRect();
            var renderedPosition = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };

            var direction = e.deltaY > 0 ? -1 : 1;  // scroll down = zoom out
            var newZoom = cy.zoom() * Math.pow(ZOOM_FACTOR, direction);

            // Clamp to Cytoscape's min/max
            newZoom = Math.max(cy.minZoom(), Math.min(cy.maxZoom(), newZoom));

            cy.zoom({
                level: newZoom,
                renderedPosition: renderedPosition
            });
        }, { passive: false });
    }

    // --- Right-click panning ---
    // userPanningEnabled is set to False in Cytoscape config.
    // We manually pan on right-click drag on the canvas background.
    function initRightClickPan(selector) {
        var cyWrapper = document.querySelector(selector);
        if (!cyWrapper) {
            setTimeout(function() { initRightClickPan(selector); }, 300);
            return;
        }

        function getCy() {
            return (cyWrapper._cyreg && cyWrapper._cyreg.cy) ? cyWrapper._cyreg.cy : null;
        }

        cyWrapper.addEventListener('mousedown', function (e) {
            // Only handle right-click (button 2)
            if (e.button !== 2) return;
            if (!window.SkillTree || !window.SkillTree.drag) return;

            var cy = getCy();
            if (!cy) return;

            // Check if the mousedown is on a node — if so, don't pan (let context menu handle it)
            var rect = cyWrapper.getBoundingClientRect();
            var rendPos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
            var modelPos = {
                x: (rendPos.x - cy.pan().x) / cy.zoom(),
                y: (rendPos.y - cy.pan().y) / cy.zoom()
            };
            var nearNode = cy.nodes().some(function (node) {
                var bb = node.boundingBox();
                return modelPos.x >= bb.x1 && modelPos.x <= bb.x2 &&
                       modelPos.y >= bb.y1 && modelPos.y <= bb.y2;
            });
            if (nearNode) return;

            var lastX = e.clientX;
            var lastY = e.clientY;
            cyWrapper.style.cursor = 'grabbing';
            e.preventDefault();

            window.SkillTree.drag.start({
                // Cursor is scoped to cyWrapper, not body; don't override body cursor.
                userSelect: false,
                onMove: function (ev) {
                    var c = getCy();
                    if (!c) return;
                    var dx = ev.clientX - lastX;
                    var dy = ev.clientY - lastY;
                    lastX = ev.clientX;
                    lastY = ev.clientY;
                    c.panBy({ x: dx, y: dy });
                },
                onEnd: function () {
                    cyWrapper.style.cursor = '';
                },
            });
        });
    }

    // --- Fullscreen toggle (generic, used by every canvas) ---
    function initCanvasFullscreen(btnId, containerId, cyId) {
        var btn = document.getElementById(btnId);
        var container = document.getElementById(containerId);

        if (!btn || !container) {
            setTimeout(function () { initCanvasFullscreen(btnId, containerId, cyId); }, 300);
            return;
        }

        function refit() {
            setTimeout(function () {
                var cy = document.getElementById(cyId);
                if (cy && cy._cyreg && cy._cyreg.cy) {
                    cy._cyreg.cy.resize();
                    cy._cyreg.cy.fit();
                }
            }, 50);
        }

        btn.addEventListener('click', function () {
            container.classList.toggle('canvas-fullscreen');
            refit();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && container.classList.contains('canvas-fullscreen')) {
                container.classList.remove('canvas-fullscreen');
                refit();
            }
        });
    }

    // --- Center graph when it becomes visible ---
    function centerGraph(selector) {
        var el = document.querySelector(selector);
        if (!el || !el._cyreg || !el._cyreg.cy) {
            return;
        }
        el._cyreg.cy.resize();
        el._cyreg.cy.fit(null, 30);
        el._cyreg.cy.center();
    }

    // Watch for the canvas tab becoming visible and center the graph.
    // The Nodes tab isn't the default, so the graph container starts hidden
    // and cy.fit()/cy.center() won't work until it's displayed.
    var graphCentered = false;
    function watchCanvasVisibility() {
        var container = document.getElementById('canvas-tab-content');
        if (!container) {
            setTimeout(watchCanvasVisibility, 300);
            return;
        }

        var observer = new MutationObserver(function () {
            if (container.offsetParent !== null && !graphCentered) {
                // Container just became visible
                setTimeout(function () { centerGraph('#cytoscape-graph'); }, 100);
                setTimeout(function () { centerGraph('#cytoscape-graph'); }, 600);
                graphCentered = true;
            }
        });
        observer.observe(container, { attributes: true, attributeFilter: ['style'] });

        // Also handle case where Nodes tab is the first tab opened
        if (container.offsetParent !== null) {
            setTimeout(function () { centerGraph('#cytoscape-graph'); }, 500);
            graphCentered = true;
        }
    }

    function initAll() {
        initScrollSensitivity('#cytoscape-graph');
        initScrollSensitivity('#goal-mini-graph');
        initScrollSensitivity('#details-mini-graph');
        initScrollSensitivity('#events-detail-graph');
        initCanvasFullscreen('btn-fullscreen', 'canvas-container', 'cytoscape-graph');
        initCanvasFullscreen('btn-details-graph-fullscreen', 'details-dep-graph-container', 'details-mini-graph');
        initCanvasFullscreen('btn-events-graph-fullscreen', 'events-detail-graph-container', 'events-detail-graph');
        initRightClickPan('#cytoscape-graph');
        initRightClickPan('#goal-mini-graph');
        initRightClickPan('#details-mini-graph');
        initRightClickPan('#events-detail-graph');
        watchCanvasVisibility();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
