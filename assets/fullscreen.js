/**
 * Fullscreen toggle + scroll sensitivity for the Skill Tree canvas.
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
        });
    } else {
        initScrollSensitivity();
        initFullscreen();
    }
})();
