/**
 * Details Back and Forward: the history of visited nodes, kept in the
 * browser. features/details/callbacks.py registers it.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.details_nav = window.dash_clientside.details_nav || {};

// Push a newly selected node, step Back or Forward, or drop nodes that are gone.
window.dash_clientside.details_nav.step = function (selected, backClicks, fwdClicks, options, history, navIndex) {
    var context = window.dash_clientside.callback_context;
    var trigger = context && context.triggered_id;
    history = (history || []).slice();
    navIndex = navIndex === null || navIndex === undefined ? -1 : Number(navIndex);
    if (trigger === 'btn-details-nav-back') {
        if (navIndex > 0) navIndex -= 1;
    } else if (trigger === 'btn-details-nav-forward') {
        if (navIndex < history.length - 1) navIndex += 1;
    } else if (trigger === 'details-selected-node-store' && selected) {
        // Only push a new node, not a back/forward replay.
        if (navIndex < 0 || (navIndex < history.length &&
                             history[navIndex] !== selected)) {
            history = history.slice(0, navIndex + 1);
            history.push(selected);
            navIndex = history.length - 1;
        } else if (!history.length) {
            history.push(selected);
            navIndex = 0;
        }
    } else if (trigger === 'details-node-select') {
        // The node list changed. Drop the nodes deleted or renamed
        // since, so Back and Forward never land on a dead entry, and
        // merge the neighbors that leaves side by side.
        var alive = {};
        (options || []).forEach(function (o) { alive[o.value] = true; });
        var kept = [], keptIndex = -1;
        history.forEach(function (name, i) {
            if (!alive[name]) return;
            if (kept[kept.length - 1] !== name) kept.push(name);
            if (i <= navIndex) keptIndex = kept.length - 1;
        });
        history = kept;
        navIndex = keptIndex;
    }
    return [history, navIndex, navIndex <= 0, navIndex >= history.length - 1];
};
