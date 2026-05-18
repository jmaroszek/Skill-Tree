/**
 * Draggable resize handle between the Events tab event-detail panel and the
 * event graph. Mirrors the vertical drag in details_resize.js.
 */
(function () {
    'use strict';

    function init() {
        var handle = document.getElementById('events-v-drag');
        var leftEl = document.getElementById('events-detail-panel');
        var rightEl = document.getElementById('events-detail-graph-container');
        if (!handle || !leftEl || !rightEl) {
            // Dash hasn't rendered the Events tab yet — retry shortly.
            setTimeout(init, 300);
            return;
        }
        if (handle.__dragWired) return;
        handle.__dragWired = true;

        handle.addEventListener('mouseenter', function () {
            handle.style.backgroundColor = '#495057';
        });
        handle.addEventListener('mouseleave', function () {
            handle.style.backgroundColor = 'transparent';
        });

        function refitGraph() {
            var cyEl = document.getElementById('events-detail-graph');
            if (cyEl && cyEl._cyreg && cyEl._cyreg.cy) {
                cyEl._cyreg.cy.resize();
            }
        }

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
                    var minWidth = 360;
                    var newLeft = Math.max(minWidth, Math.min(totalWidth - minWidth, startLeftWidth + delta));
                    var newRight = totalWidth - newLeft;
                    // Switch to fixed pixel widths and drop flex so the sizes stick.
                    leftEl.style.flex = 'none';
                    leftEl.style.width = newLeft + 'px';
                    leftEl.style.minWidth = '0';
                    leftEl.style.maxWidth = 'none';
                    rightEl.style.flex = 'none';
                    rightEl.style.width = newRight + 'px';
                    rightEl.style.minWidth = '0';
                },
                onEnd: refitGraph,
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
