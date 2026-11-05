/**
 * Rating Accuracy's legend: a click on a context, or Enter or Space on it,
 * shows or hides that context, so a few can be compared. A double-click shows
 * only that context, and a double-click on it then shows them all again.
 *
 * A hidden context's average dots go, and the gray bars are redrawn from the
 * contexts still shown: each context's counts per whole-point change come in
 * the chart's data-bins, as {rng, rows: {Value: {Health: [counts]}}}, the
 * counts running from -rng to +rng. The three rows keep one height scale.
 * The server draws every context shown, so this runs only on a click, and a
 * new chart from the server starts with every context shown again.
 */
(function () {
    function signed(t) { return (t > 0 ? '+' : '−') + Math.abs(t); }

    // The tooltip text charts.py gives a bar, for counts it never saw.
    function binTip(label, t, rng, n, total) {
        var name = t === 0 ? label + ' unchanged'
            : label + ' ' + signed(t)
              + (t === rng ? ' or more' : t === -rng ? ' or less' : '');
        return name + '\n' + n + ' reflection' + (n === 1 ? '' : 's')
            + ' (' + Math.round(100 * n / total) + '% of the row)';
    }

    // Each row's counts summed over the shown contexts, and the tallest bar.
    function sumBins(data, shown) {
        var rows = {}, tallest = 0;
        Object.keys(data.rows).forEach(function (label) {
            var sum = new Array(2 * data.rng + 1).fill(0);
            Object.keys(data.rows[label]).forEach(function (ctx) {
                if (!shown[ctx]) return;
                data.rows[label][ctx].forEach(function (n, i) { sum[i] += n; });
            });
            sum.forEach(function (n) { tallest = Math.max(tallest, n); });
            rows[label] = sum;
        });
        return {rows: rows, tallest: tallest};
    }

    function redraw(card) {
        var chart = card.querySelector('.drift-chart');
        if (!chart) return;
        var data = JSON.parse(chart.getAttribute('data-bins'));
        var shown = {};
        card.querySelectorAll('.dr-toggle').forEach(function (item) {
            shown[item.getAttribute('data-context')] =
                item.getAttribute('aria-pressed') !== 'false';
        });
        var sums = sumBins(data, shown);
        chart.querySelectorAll('.dr-bin').forEach(function (bar) {
            var label = bar.getAttribute('data-row');
            var t = Number(bar.getAttribute('data-t'));
            var counts = sums.rows[label];
            var n = counts[t + data.rng];
            if (!n) {
                bar.style.display = 'none';
                bar.removeAttribute('data-tip');
                return;
            }
            var total = counts.reduce(function (a, b) { return a + b; }, 0);
            bar.style.display = '';
            bar.style.height = (88 * n / sums.tallest).toFixed(1) + '%';
            bar.setAttribute('data-tip', binTip(label, t, data.rng, n, total));
        });
        chart.querySelectorAll('.dr-mean').forEach(function (dot) {
            dot.hidden = !shown[dot.getAttribute('data-context')];
        });
    }

    function toggle(item) {
        item.setAttribute('aria-pressed',
                          String(item.getAttribute('aria-pressed') === 'false'));
        redraw(item.closest('.drift-card'));
    }

    // Which contexts stay shown after a double-click on ``name``: only that
    // one, or, when it already stands alone, every context again.
    function isolated(name, shown) {
        var alone = Object.keys(shown).every(function (ctx) {
            return shown[ctx] === (ctx === name);
        });
        var next = {};
        Object.keys(shown).forEach(function (ctx) { next[ctx] = alone || ctx === name; });
        return next;
    }

    // The double-click's own two clicks have already toggled the entry twice,
    // so the legend is back where it was when this runs.
    function isolate(item) {
        var card = item.closest('.drift-card');
        var items = card.querySelectorAll('.dr-toggle');
        var shown = {};
        items.forEach(function (i) {
            shown[i.getAttribute('data-context')] = i.getAttribute('aria-pressed') !== 'false';
        });
        var next = isolated(item.getAttribute('data-context'), shown);
        items.forEach(function (i) {
            i.setAttribute('aria-pressed', String(next[i.getAttribute('data-context')]));
        });
        redraw(card);
    }

    document.addEventListener('click', function (e) {
        var item = e.target.closest && e.target.closest('.dr-toggle');
        if (item) toggle(item);
    });
    document.addEventListener('dblclick', function (e) {
        var item = e.target.closest && e.target.closest('.dr-toggle');
        if (item) isolate(item);
    });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var item = e.target.closest && e.target.closest('.dr-toggle');
        if (!item) return;
        e.preventDefault();
        toggle(item);
    });

    window.SkillTree = window.SkillTree || {};
    window.SkillTree.driftLegend = {binTip: binTip, sumBins: sumBins};
    // The scatter's legend (rating_dist.js) isolates a trace the same way.
    window.SkillTree.isolateLegend = isolated;
})();
