/**
 * Draggable resize handles for the Details tab quadrants.
 *
 * Three handles:
 *   1. Horizontal (details-h-drag) — resize upper vs lower section height
 *   2. Vertical upper (details-v-drag-upper) — resize node summary vs dep graph width
 *   3. Vertical lower (details-v-drag-lower) — resize subtasks vs simulation width
 */
(function () {
    'use strict';

    function initDetailsResizeHandles() {
        var hDrag = document.getElementById('details-h-drag');
        var vDragUpper = document.getElementById('details-v-drag-upper');
        var vDragLower = document.getElementById('details-v-drag-lower');
        var upper = document.getElementById('details-upper-section');
        var lower = document.getElementById('details-lower-section');
        var nodeSummary = document.getElementById('details-node-summary');
        var depGraph = document.getElementById('details-dep-graph-container');
        var subtasks = document.getElementById('details-subtasks-section');
        var simSection = document.getElementById('details-sim-section');

        if (!hDrag || !upper || !lower) {
            setTimeout(initDetailsResizeHandles, 300);
            return;
        }

        // --- Hover highlight ---
        [hDrag, vDragUpper, vDragLower].forEach(function (el) {
            if (!el) return;
            el.addEventListener('mouseenter', function () {
                el.style.backgroundColor = '#495057';
            });
            el.addEventListener('mouseleave', function () {
                el.style.backgroundColor = 'transparent';
            });
        });

        // --- Horizontal drag (upper/lower split) ---
        (function () {
            var dragging = false;
            var startY = 0;
            var startUpperFlex = 0;
            var startLowerFlex = 0;

            hDrag.addEventListener('mousedown', function (e) {
                e.preventDefault();
                dragging = true;
                startY = e.clientY;
                // Read the current flex values
                var cs1 = window.getComputedStyle(upper);
                var cs2 = window.getComputedStyle(lower);
                startUpperFlex = parseFloat(cs1.flexGrow) || 1.5;
                startLowerFlex = parseFloat(cs2.flexGrow) || 0.75;
                document.body.style.cursor = 'ns-resize';
                document.body.style.userSelect = 'none';
            });

            document.addEventListener('mousemove', function (e) {
                if (!dragging) return;
                var parent = upper.parentElement;
                if (!parent) return;
                var totalHeight = parent.offsetHeight;
                if (totalHeight === 0) return;

                var delta = e.clientY - startY;
                var totalFlex = startUpperFlex + startLowerFlex;
                var flexDelta = (delta / totalHeight) * totalFlex;

                var newUpperFlex = Math.max(0.3, startUpperFlex + flexDelta);
                var newLowerFlex = Math.max(0.3, startLowerFlex - flexDelta);

                upper.style.flex = newUpperFlex + ' 1 0';
                lower.style.flex = newLowerFlex + ' 1 0';
            });

            document.addEventListener('mouseup', function () {
                if (!dragging) return;
                dragging = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';

                // Tell Cytoscape to recalculate
                var cyEl = document.getElementById('details-mini-graph');
                if (cyEl && cyEl._cyreg && cyEl._cyreg.cy) {
                    cyEl._cyreg.cy.resize();
                }
            });
        })();

        // --- Vertical drag helper ---
        function initVerticalDrag(handle, leftEl, rightEl) {
            if (!handle || !leftEl || !rightEl) return;

            var dragging = false;
            var startX = 0;
            var startLeftWidth = 0;
            var startRightWidth = 0;

            handle.addEventListener('mousedown', function (e) {
                e.preventDefault();
                dragging = true;
                startX = e.clientX;
                startLeftWidth = leftEl.offsetWidth;
                startRightWidth = rightEl.offsetWidth;
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';
            });

            document.addEventListener('mousemove', function (e) {
                if (!dragging) return;
                var delta = e.clientX - startX;
                var totalWidth = startLeftWidth + startRightWidth;
                var minWidth = 150;

                var newLeft = Math.max(minWidth, Math.min(totalWidth - minWidth, startLeftWidth + delta));
                var newRight = totalWidth - newLeft;

                // Use pixel widths and remove flex so sizes stick
                leftEl.style.flex = 'none';
                leftEl.style.width = newLeft + 'px';
                leftEl.style.minWidth = '0';
                leftEl.style.maxWidth = 'none';

                rightEl.style.flex = 'none';
                rightEl.style.width = newRight + 'px';
                rightEl.style.minWidth = '0';
            });

            document.addEventListener('mouseup', function () {
                if (!dragging) return;
                dragging = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';

                // Tell mini-graph Cytoscape to recalculate
                var cyEl = document.getElementById('details-mini-graph');
                if (cyEl && cyEl._cyreg && cyEl._cyreg.cy) {
                    cyEl._cyreg.cy.resize();
                }
            });
        }

        initVerticalDrag(vDragUpper, nodeSummary, depGraph);
        initVerticalDrag(vDragLower, subtasks, simSection);
    }

    // --- Fullscreen toggle for details dependency graph ---
    function initDetailsFullscreen() {
        var btn = document.getElementById('btn-details-graph-fullscreen');
        var container = document.getElementById('details-dep-graph-container');

        if (!btn || !container) {
            setTimeout(initDetailsFullscreen, 300);
            return;
        }

        btn.addEventListener('click', function () {
            container.classList.toggle('canvas-fullscreen');
            setTimeout(function () {
                var cyEl = document.getElementById('details-mini-graph');
                if (cyEl && cyEl._cyreg && cyEl._cyreg.cy) {
                    cyEl._cyreg.cy.resize();
                    cyEl._cyreg.cy.fit();
                }
            }, 50);
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && container.classList.contains('canvas-fullscreen')) {
                container.classList.remove('canvas-fullscreen');
                setTimeout(function () {
                    var cyEl = document.getElementById('details-mini-graph');
                    if (cyEl && cyEl._cyreg && cyEl._cyreg.cy) {
                        cyEl._cyreg.cy.resize();
                        cyEl._cyreg.cy.fit();
                    }
                }, 50);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initDetailsResizeHandles();
            initDetailsFullscreen();
        });
    } else {
        initDetailsResizeHandles();
        initDetailsFullscreen();
    }
})();
