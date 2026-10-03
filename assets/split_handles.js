/**
 * Drag handles that resize the two panels on either side of them.
 *
 * A handle is a div with the split-handle class (ui_kit.split_handle) placed
 * between the two panels it resizes: its previous and next siblings. The
 * Details tab has three, and the Events tab one.
 *
 *   - split-handle-cols drags sideways. Both panels get fixed pixel widths.
 *   - split-handle-rows drags up and down. The panels share the height by
 *     flex-grow instead, so the split keeps its proportions when the window
 *     changes height.
 *
 * data-min-size is the fewest pixels a drag leaves either panel.
 *
 * One mousedown listener on the document serves every handle, so a handle
 * works as soon as Dash renders it. When a drag ends, each canvas inside the
 * resized pair is told its size changed. The handle's look, hover included,
 * is the .split-handle rules in theme.css.
 */
(function () {
    'use strict';

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function describeHandle(handle) {
        var first = handle.previousElementSibling;
        var second = handle.nextElementSibling;
        if (!first || !second) return;
        var rows = handle.classList.contains('split-handle-rows');
        var size = rows ? first.offsetHeight : first.offsetWidth;
        var total = size + (rows ? second.offsetHeight : second.offsetWidth);
        if (!total) return;
        handle.setAttribute('aria-valuemin', '0');
        handle.setAttribute('aria-valuemax', '100');
        handle.setAttribute('aria-valuenow', Math.round(100 * size / total));
        handle.setAttribute('aria-valuetext', Math.round(size) + ' pixels');
    }
    window.SkillTree.describeSplitHandle = describeHandle;
    document.addEventListener('focusin', function (e) {
        if (e.target.matches && e.target.matches('.split-handle')) describeHandle(e.target);
    });

    function sizeColumns(first, second, startX, minSize) {
        var startFirst = first.offsetWidth;
        var total = startFirst + second.offsetWidth;
        function fix(panel, width) {
            // Pixel widths with flex off, so the sizes stick.
            panel.style.flex = 'none';
            panel.style.width = width + 'px';
            panel.style.minWidth = '0';
            panel.style.maxWidth = 'none';
        }
        return function (ev) {
            var width = clamp(startFirst + ev.clientX - startX, minSize, total - minSize);
            fix(first, width);
            fix(second, total - width);
        };
    }

    // Padding and borders sit outside the space flex-grow shares out, since
    // both panels have a zero flex-basis. Taking them off first makes each
    // panel land on exactly the height asked for.
    function verticalChrome(panel) {
        var cs = window.getComputedStyle(panel);
        return (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0)
            + (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0);
    }

    function sizeRows(first, second, startY, minSize) {
        var startFirst = first.offsetHeight;
        var total = startFirst + second.offsetHeight;
        var firstChrome = verticalChrome(first);
        var secondChrome = verticalChrome(second);
        return function (ev) {
            var height = clamp(startFirst + ev.clientY - startY, minSize, total - minSize);
            first.style.flex = Math.max(0, height - firstChrome) + ' 1 0';
            second.style.flex = Math.max(0, total - height - secondChrome) + ' 1 0';
        };
    }

    // Cytoscape only notices a new container size on its own a little later.
    function resizeCanvasesIn(container) {
        if (!container) return;
        (window.SkillTree.canvases || []).forEach(function (canvas) {
            var el = document.getElementById(canvas.cytoscapeId);
            var cy = el && container.contains(el) ? window.SkillTree.getCy(el) : null;
            if (cy) cy.resize();
        });
    }

    document.addEventListener('mousedown', function (e) {
        if (e.button !== 0 || !e.target || !e.target.closest) return;
        var handle = e.target.closest('.split-handle');
        if (!handle || !window.SkillTree || !window.SkillTree.drag) return;
        var first = handle.previousElementSibling;
        var second = handle.nextElementSibling;
        if (!first || !second) return;
        e.preventDefault();

        var rows = handle.classList.contains('split-handle-rows');
        var minSize = parseFloat(handle.getAttribute('data-min-size')) || 0;
        window.SkillTree.drag.start({
            cursor: rows ? 'ns-resize' : 'col-resize',
            onMove: rows
                ? sizeRows(first, second, e.clientY, minSize)
                : sizeColumns(first, second, e.clientX, minSize),
            onEnd: function () { resizeCanvasesIn(handle.parentElement); describeHandle(handle); },
        });
    });

    document.addEventListener('keydown', function (e) {
        var handle = e.target;
        if (!handle.matches || !handle.matches('.split-handle')) return;
        var rows = handle.classList.contains('split-handle-rows');
        var backward = rows ? 'ArrowUp' : 'ArrowLeft';
        var forward = rows ? 'ArrowDown' : 'ArrowRight';
        if (![backward, forward, 'Home', 'End'].includes(e.key)) return;
        var first = handle.previousElementSibling;
        var second = handle.nextElementSibling;
        if (!first || !second) return;
        e.preventDefault();
        var min = parseFloat(handle.dataset.minSize) || 0;
        var delta = (e.shiftKey ? 50 : 10) * (e.key === backward ? -1 : 1);
        if (e.key === 'Home') delta = -100000;
        if (e.key === 'End') delta = 100000;
        if (rows) sizeRows(first, second, 0, min)({clientY: delta});
        else sizeColumns(first, second, 0, min)({clientX: delta});
        resizeCanvasesIn(handle.parentElement);
        describeHandle(handle);
    });
})();
