/**
 * Which left sidebar is open: the editor, Goals, Events or none. They share one
 * slot, and left-panel-store says which holds it.
 *
 * Nothing else writes that store or the sidebars' classes. CSS does the slide,
 * because the browser runs a transform animation off the main thread.
 * engine/sidebars.py registers it, and says why it's registered twice.
 *
 * Clicks arrive here directly, so a sidebar starts to move without waiting for
 * the server. A close that depends on the unsaved-changes check comes from the
 * server as left-panel-request, and it only closes the sidebar it names: by the
 * time it lands, the user may have opened another.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.left_panel = window.dash_clientside.left_panel || {};

(function () {
    // The tab the last run saw, so leaving Events is told from any other change.
    var lastTab = null;

    function toggled(current, panel) {
        return current === panel ? null : panel;
    }

    function closed(current, panel) {
        return current === panel ? null : current;
    }

    // The Events tab opens its sidebar on arrival when its true empty state is
    // showing, and closes it on the way out. An event being composed also has
    // no selected event, so the visible empty state tells the two apart.
    function afterTabChange(current, tab, previous, state) {
        if (previous === 'tab-events' && tab !== 'tab-events') {
            return closed(current, 'events');
        }
        var empty = !state.emptyStyle || state.emptyStyle.display !== 'none';
        return tab === 'tab-events' && !state.selectedEvent && empty ? 'events' : current;
    }

    function next(current, id, value, state) {
        if (id === 'main-tabs') {
            var previous = lastTab;
            lastTab = value;
            return afterTabChange(current, value, previous, state);
        }
        if (!value) return current;
        switch (id) {
            case 'btn-goals-toggle': return toggled(current, 'goals');
            case 'btn-details-goals-close': return closed(current, 'goals');
            case 'btn-events-sidebar-toggle': return toggled(current, 'events');
            case 'btn-events-sidebar-close': return closed(current, 'events');
            // On an open editor this is a close, which asks the server first
            // (advance). Nothing changes here.
            case 'btn-add': return 'editor';
            case 'btn-goals-sidebar-new':
            case 'btn-bridge-create':
            case 'edit-trigger-input':
            case 'details-edit-trigger-input':
                return 'editor';
            case 'details-add-choice-input':
                return value.indexOf('new|') === 0 && state.selectedNode ? 'editor' : current;
            case 'dormant-add-choice-input':
                return value.indexOf('new|') === 0 && state.selectedEvent ? 'editor' : current;
            case 'left-panel-request': return closed(current, value.close);
            default: return current;
        }
    }

    // Only what changes: every output Dash writes costs a few store updates too.
    function classIfChanged(current, panel, name, open, closed) {
        if ((current === name) === (panel === name)) {
            return window.dash_clientside.no_update;
        }
        return panel === name ? open : closed;
    }

    function sidebarClass(current, panel, name) {
        return classIfChanged(current, panel, name, 'left-sidebar is-open', 'left-sidebar');
    }

    window.dash_clientside.left_panel.next = next;

    // Takes the Inputs, whose values it reads from what fired, then the States.
    window.dash_clientside.left_panel.advance = function () {
        var states = Array.prototype.slice.call(arguments, -9);
        var current = states[0] || null;
        var state = {selectedEvent: states[1], emptyStyle: states[2], selectedNode: states[3]};
        var goalListSources = states.slice(4);
        var ctx = window.dash_clientside.callback_context;
        var NO = window.dash_clientside.no_update;
        var panel = current;
        var closeAsk = NO;
        (ctx.triggered || []).forEach(function (fired) {
            var id = fired.prop_id.split('.')[0];
            // Only here is it known that this click found the editor open. The
            // unsaved-changes check runs on the server, and by the time it runs
            // the store may already say what the click did.
            if (id === 'btn-add' && fired.value && panel === 'editor') closeAsk = Date.now();
            panel = next(panel, id, fired.value, state);
        });
        if (panel === current) return [NO, NO, NO, NO, NO, closeAsk];
        // Plain calls, not callbacks on the store: each callback costs about a
        // dozen store updates, all before the browser paints the slide's first
        // frame.
        window.dash_clientside.goals.follow_left_panel.apply(null, [panel].concat(goalListSources));
        window.dash_clientside.events.follow_left_panel(panel);
        return [sidebarClass(current, panel, 'editor'),
                sidebarClass(current, panel, 'goals'),
                sidebarClass(current, panel, 'events'),
                classIfChanged(current, panel, 'events',
                               'events-tab-inner is-beside-sidebar', 'events-tab-inner'),
                panel,
                closeAsk];
    };
})();
