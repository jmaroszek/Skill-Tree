/**
 * Clientside toggle for the Goals sidebar.
 *
 * Moved off the server to eliminate the ~50-150ms round-trip on each
 * open/close. Mirrors the events_sidebar.js pattern: on open, closes
 * peer left-side sidebars (editor, events) via the sidebar mutex, and
 * bumps goals-ui-refresh-trigger so render_goal_list rebuilds the card list.
 * A finished close bumps it too, and the closed sidebar drops its cards.
 *
 * The sidebar slides with `transform`, which the browser animates off the
 * main thread. The refresh waits until the slide is done, so the rebuilt
 * list doesn't land mid-slide.
 *
 * The last list built is remembered. If nothing it was built from has
 * changed, a reopen slides in with it instead of the spinner. Putting it
 * back takes a few milliseconds. The rebuild still runs after the slide, so
 * anything the key misses is corrected then.
 */
// NOTE: 350px must match config.SIDEBAR_WIDTH, and SLIDE_MS the 0.3s
// transition in sidebars_layout.py.
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.goals = window.dash_clientside.goals || {};

(function () {
    var OPEN = "translateX(0px)";
    var CLOSED = "translateX(-350px)";
    var SLIDE_MS = 300;
    var BASE_SIDEBAR_STYLE = {
        position: "absolute",
        top: "0",
        left: "0",
        width: "350px",
        height: "100%",
        zIndex: 100,
        overflowX: "hidden",
        overflowY: "auto",
        borderRight: "1px solid #495057",
        transition: "transform 0.3s ease",
        transform: CLOSED,
        willChange: "transform",
        backgroundColor: "#212529",
        display: "flex",
        flexDirection: "column"
    };
    var pendingRefresh = null;
    // {key, json} of the last built list.
    var remembered = null;

    // What a built list depends on: the graph, priorities, search, sort and
    // manual order. Selection only moves the outline, which a clientside
    // callback redraws when the cards mount.
    function listKey(version, refresh, search, sort, order) {
        return JSON.stringify([version, refresh, search || '', sort || null, order || null]);
    }

    function isCover(children) {
        return !!(children && !Array.isArray(children) && children.props
                  && children.props.className === 'loading-cover');
    }

    window.dash_clientside.goals.remember_list = function (
        children, version, refresh, search, sort, order
    ) {
        if (children && !isCover(children)) {
            remembered = {key: listKey(version, refresh, search, sort, order),
                          json: JSON.stringify(children)};
        }
    };

    function cancelRefresh() {
        clearTimeout(pendingRefresh);
        pendingRefresh = null;
    }

    function triggerId() {
        var cb = window.dash_clientside && window.dash_clientside.callback_context;
        if (!cb) return null;
        if (cb.triggered_id) return cb.triggered_id;
        var t = cb.triggered;
        if (t && t.length > 0 && t[0].prop_id) {
            return t[0].prop_id.split('.')[0];
        }
        return null;
    }

    window.dash_clientside.goals.toggle_sidebar = function (
        _toggleN, _closeN,
        currentStyle, editorStyle, eventsStyle, refresh,
        version, detailsRefresh, search, sort, order
    ) {
        var NO = window.dash_clientside.no_update;
        var trigger = triggerId();
        if (!trigger) return [NO, NO, NO];

        var style = Object.assign({}, BASE_SIDEBAR_STYLE, currentStyle || {});
        var nextEditor = NO;
        var nextEvents = NO;

        function doOpen() {
            style.transform = OPEN;
            cancelRefresh();
            var key = listKey(version, detailsRefresh, search, sort, order);
            if (remembered && remembered.key === key) {
                var json = remembered.json;
                // After this callback returns, so the slide starts first.
                setTimeout(function () {
                    var list = document.getElementById('details-goal-list-container');
                    if (list && list.querySelector('.goal-card')) return;
                    window.dash_clientside.set_props('details-goal-list-container',
                                                     {children: JSON.parse(json)});
                }, 0);
            }
            var nextRefresh = (refresh || 0) + 1;
            pendingRefresh = setTimeout(function () {
                pendingRefresh = null;
                window.dash_clientside.set_props("goals-ui-refresh-trigger", { data: nextRefresh });
            }, SLIDE_MS);
            if (editorStyle && editorStyle.transform === OPEN) {
                nextEditor = Object.assign({}, editorStyle, { transform: CLOSED });
            }
            if (eventsStyle && eventsStyle.transform === OPEN) {
                nextEvents = Object.assign({}, eventsStyle, { transform: CLOSED });
            }
        }

        function doClose() {
            style.transform = CLOSED;
            cancelRefresh();
        }

        if (trigger === "btn-goals-toggle") {
            if (style.transform === OPEN) {
                doClose();
            } else {
                doOpen();
            }
        } else if (trigger === "btn-details-goals-close") {
            doClose();
        } else {
            return [NO, NO, NO];
        }

        return [style, nextEditor, nextEvents];
    };

    // Once a close slide finishes, swap the cards for the loading cover.
    // Dash re-checks every mounted component on each store update, so a
    // hidden list slows everything else, the Details graph's opening
    // animation most of all. The toggle is not the only thing that closes
    // the sidebar (the editor and Events slide it shut), so this listens for
    // the slide rather than the click. A close reversed mid-slide cancels its
    // transition, and no transitionend arrives.
    document.addEventListener('transitionend', function (evt) {
        var sidebar = evt.target;
        if (!sidebar || sidebar.id !== 'details-goal-sidebar') return;
        if (evt.propertyName !== 'transform') return;
        if (sidebar.style.transform !== CLOSED) return;
        window.dash_clientside.set_props("goals-ui-refresh-trigger", { data: Date.now() });
    }, true);
})();

/**
 * Clicking a goal card opens it in the Details tab, the same as View Details
 * in its right-click menu. The rank badge keeps its own popover
 * (goal_rank_popover.js, which stops the click) and the drag handle only drags.
 */
(function () {
    document.addEventListener('click', function (evt) {
        if (evt.button !== 0 || !evt.target.closest) return;
        var card = evt.target.closest('.goal-card');
        if (!card || evt.target.closest('.goal-drag-handle, .goal-rank-trigger')) return;
        var name = card.getAttribute('data-goal-name');
        var menus = window.SkillTree && window.SkillTree.menus;
        if (!name || !menus) return;
        menus.send('details-navigate-trigger-input', name + '|' + Date.now());
    });
})();
