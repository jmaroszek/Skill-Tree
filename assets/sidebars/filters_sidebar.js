/**
 * Clientside toggle for the Filters sidebar.
 *
 * Moved off the server to eliminate the 500ms-2s round-trip that was
 * blocking the CSS transition start. The filters sidebar lives on the
 * right edge and does not overlap the left-side sidebars, so no
 * peer-sidebar mutex is required.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.filters = window.dash_clientside.filters || {};

(function () {
    var CLOSED = "right-sidebar";
    var OPEN = "right-sidebar is-open";

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

    window.dash_clientside.filters.toggle_sidebar = function (_toggleN, _closeN, current) {
        var trigger = triggerId();
        if (trigger === "btn-filters-toggle") return current === OPEN ? CLOSED : OPEN;
        if (trigger === "btn-close-filters") return CLOSED;
        return window.dash_clientside.no_update;
    };
})();

// Drop subcontext picks whose context is no longer selected. Clientside:
// Dash strips a server Output's layout value, which held the restored picks.
window.dash_clientside.filters.prune_subcontexts = function (ctx, current_subs) {
    if (!current_subs || current_subs.length === 0) {
        return window.dash_clientside.no_update;
    }
    const contexts = Array.isArray(ctx) ? ctx : (ctx ? [ctx] : []);
    const ctxSet = new Set(contexts);
    const SEP = '\u001f';
    const kept = current_subs.filter(v => {
        const sep = v.indexOf(SEP);
        if (sep < 0) return false;
        return ctxSet.has(v.slice(0, sep));
    });
    if (kept.length === current_subs.length) {
        return window.dash_clientside.no_update;
    }
    return kept;
};
