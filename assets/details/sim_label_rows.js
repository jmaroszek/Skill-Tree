/* Keep the Time Simulation chart's P10, P50 and P90 labels apart.
 *
 * The labels share one row above the plot while they fit. A label that
 * would overlap one already placed rises to the lowest row where it fits.
 * In practice P50 lifts above a close P10, and P90 takes a third row only
 * for a near-certain estimate, where it overlaps both.
 *
 * Plotly doesn't keep annotations apart, and the server can't: it never
 * learns how wide the chart is, and the Details panel can be dragged from
 * 250px to most of the window. So this measures the labels where Plotly drew
 * them, after every draw. That includes the resize redraw a panel drag
 * causes. The server always sends one row. A new figure resets the rows,
 * and the draw that follows places them again.
 */
(function () {
    'use strict';

    var GAP_PX = 6;
    var attached = new WeakSet();

    // Each label's row, given its drawn horizontal extent.
    function rowsFor(extents) {
        var order = extents.map(function (_, i) { return i; });
        order.sort(function (a, b) { return extents[a].left - extents[b].left; });
        var rowEnds = [];
        var rows = new Array(extents.length);
        order.forEach(function (i) {
            var row = 0;
            while (row < rowEnds.length && extents[i].left < rowEnds[row] + GAP_PX) row++;
            rowEnds[row] = extents[i].right;
            rows[i] = row;
        });
        return rows;
    }

    function place(gd) {
        var notes = (gd.layout && gd.layout.annotations) || [];
        if (!notes.length || !window.Plotly) return;
        var extents = [];
        var rowPx = 0;
        for (var i = 0; i < notes.length; i++) {
            var drawn = gd.querySelector('.annotation[data-index="' + i + '"]');
            var box = drawn && drawn.getBoundingClientRect();
            // A hidden chart measures zero. It is placed when it is shown.
            if (!box || !box.width) return;
            extents.push({left: box.left, right: box.right});
            rowPx = Math.max(rowPx, Math.ceil(box.height));
        }
        var rows = rowsFor(extents);
        var shifts = notes.map(function (note) { return note.yshift || 0; });
        var wanted = rows.map(function (row) { return row * rowPx; });
        if (wanted.every(function (shift, i) { return shift === shifts[i]; })) return;

        // The server's top margin holds one row. Each extra row adds one.
        var margin = (gd.layout.margin && gd.layout.margin.t) || 0;
        var update = {'margin.t': margin + (Math.max.apply(null, wanted) -
                                            Math.max.apply(null, shifts))};
        wanted.forEach(function (shift, i) { update['annotations[' + i + '].yshift'] = shift; });
        window.Plotly.relayout(gd, update);
    }

    // Placing rows redraws the chart, and that draw finds nothing to change.
    function attach(gd) {
        if (attached.has(gd)) return;
        attached.add(gd);
        gd.on('plotly_afterplot', function () { place(gd); });
        place(gd);
    }

    // Called with each new figure. Plotly draws the chart after the callback
    // returns, so this waits for the plot to exist.
    function watch(id) {
        var tries = 0;
        (function look() {
            var gd = document.querySelector('#' + id + ' .js-plotly-plot');
            if (gd && typeof gd.on === 'function') {
                attach(gd);
            } else if (++tries < 300) {
                requestAnimationFrame(look);
            }
        })();
    }

    var SkillTree = window.SkillTree = window.SkillTree || {};
    SkillTree.simLabelRows = {watch: watch, rowsFor: rowsFor};
})();
