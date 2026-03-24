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

    function initScrollSensitivity() {
        var cyWrapper = document.getElementById('cytoscape-graph');
        if (!cyWrapper) {
            setTimeout(initScrollSensitivity, 300);
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
    function initRightClickPan() {
        var cyWrapper = document.getElementById('cytoscape-graph');
        if (!cyWrapper) {
            setTimeout(initRightClickPan, 300);
            return;
        }

        function getCy() {
            return (cyWrapper._cyreg && cyWrapper._cyreg.cy) ? cyWrapper._cyreg.cy : null;
        }

        var isPanning = false;
        var lastX = 0;
        var lastY = 0;
        var panStartedOnNode = false;

        cyWrapper.addEventListener('mousedown', function (e) {
            // Only handle right-click (button 2)
            if (e.button !== 2) return;

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

            if (nearNode) {
                panStartedOnNode = true;
                return;
            }

            panStartedOnNode = false;
            isPanning = true;
            lastX = e.clientX;
            lastY = e.clientY;
            cyWrapper.style.cursor = 'grabbing';
            e.preventDefault();
        });

        document.addEventListener('mousemove', function (e) {
            if (!isPanning) return;

            var cy = getCy();
            if (!cy) return;

            var dx = e.clientX - lastX;
            var dy = e.clientY - lastY;
            lastX = e.clientX;
            lastY = e.clientY;

            cy.panBy({ x: dx, y: dy });
        });

        document.addEventListener('mouseup', function (e) {
            if (e.button !== 2) return;
            if (isPanning) {
                isPanning = false;
                cyWrapper.style.cursor = '';
            }
            panStartedOnNode = false;
        });
    }

    // --- Fullscreen toggle ---
    function initFullscreen() {
        var btn = document.getElementById('btn-fullscreen');
        var container = document.getElementById('canvas-container');

        if (!btn || !container) {
            setTimeout(initFullscreen, 300);
            return;
        }

        btn.addEventListener('click', function () {
            container.classList.toggle('canvas-fullscreen');

            // Force Cytoscape to recalculate its viewport after resize
            setTimeout(function () {
                var cy = container.querySelector('#cytoscape-graph');
                if (cy && cy._cyreg && cy._cyreg.cy) {
                    cy._cyreg.cy.resize();
                    cy._cyreg.cy.fit();
                }
            }, 50);
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && container.classList.contains('canvas-fullscreen')) {
                container.classList.remove('canvas-fullscreen');

                setTimeout(function () {
                    var cy = container.querySelector('#cytoscape-graph');
                    if (cy && cy._cyreg && cy._cyreg.cy) {
                        cy._cyreg.cy.resize();
                        cy._cyreg.cy.fit();
                    }
                }, 50);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initScrollSensitivity();
            initFullscreen();
            initRightClickPan();
        });
    } else {
        initScrollSensitivity();
        initFullscreen();
        initRightClickPan();
    }
})();
