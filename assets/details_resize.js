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
        var leftPanel = document.getElementById('details-left-panel') || document.getElementById('details-node-summary');
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

        function refitDetailsMiniGraph() {
            var cyEl = document.getElementById('details-mini-graph');
            if (cyEl && cyEl._cyreg && cyEl._cyreg.cy) {
                cyEl._cyreg.cy.resize();
            }
        }

        // --- Horizontal drag (upper/lower split) ---
        hDrag.addEventListener('mousedown', function (e) {
            e.preventDefault();
            if (!window.SkillTree || !window.SkillTree.drag) return;
            var startY = e.clientY;
            var cs1 = window.getComputedStyle(upper);
            var cs2 = window.getComputedStyle(lower);
            var startUpperFlex = parseFloat(cs1.flexGrow) || 1.5;
            var startLowerFlex = parseFloat(cs2.flexGrow) || 0.75;

            window.SkillTree.drag.start({
                cursor: 'ns-resize',
                onMove: function (ev) {
                    var parent = upper.parentElement;
                    if (!parent) return;
                    var totalHeight = parent.offsetHeight;
                    if (totalHeight === 0) return;
                    var delta = ev.clientY - startY;
                    var totalFlex = startUpperFlex + startLowerFlex;
                    var flexDelta = (delta / totalHeight) * totalFlex;
                    var newUpperFlex = Math.max(0.3, startUpperFlex + flexDelta);
                    var newLowerFlex = Math.max(0.3, startLowerFlex - flexDelta);
                    upper.style.flex = newUpperFlex + ' 1 0';
                    lower.style.flex = newLowerFlex + ' 1 0';
                },
                onEnd: refitDetailsMiniGraph,
            });
        });

        // --- Vertical drag helper ---
        function initVerticalDrag(handle, leftEl, rightEl) {
            if (!handle || !leftEl || !rightEl) return;
            handle.addEventListener('mousedown', function (e) {
                e.preventDefault();
                if (!window.SkillTree || !window.SkillTree.drag) return;
                var startX = e.clientX;
                var startLeftWidth = leftEl.offsetWidth;
                var startRightWidth = rightEl.offsetWidth;

                window.SkillTree.drag.start({
                    cursor: 'col-resize',
                    onMove: function (ev) {
                        var delta = ev.clientX - startX;
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
                    },
                    onEnd: refitDetailsMiniGraph,
                });
            });
        }

        initVerticalDrag(vDragUpper, leftPanel, depGraph);
        initVerticalDrag(vDragLower, subtasks, simSection);
    }

    // Fullscreen toggle is centralized in fullscreen.js (initCanvasFullscreen).

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDetailsResizeHandles);
    } else {
        initDetailsResizeHandles();
    }
})();
