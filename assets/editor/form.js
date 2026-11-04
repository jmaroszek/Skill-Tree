/**
 * The node editor form's clientside callbacks: what changed elsewhere, and
 * the Inherit locks. features/editor/merge.py and fields.py register them.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.editor_form = window.dash_clientside.editor_form || {};

// An answer from merge_outside_changes, applied against the editor as it is
// when it lands. If another node has loaded, all of it is stale. A group whose
// field or baseline has changed since is dropped whole, and the others land.
// Moving only its baseline would read what the user hasn't seen as their edit:
// a link added elsewhere would look removed by them, and Save would remove it.
window.dash_clientside.editor_form.apply_merge = function (answer, name, snapshot) {
    var dc = window.dash_clientside;
    if (!answer) throw dc.PreventUpdate;
    // A dict's keys can come back from the server in another order.
    var comparable = function (value) {
        if (Array.isArray(value)) return value.map(comparable);
        if (value && typeof value === 'object') {
            var sorted = {};
            Object.keys(value).sort().forEach(function (key) { sorted[key] = comparable(value[key]); });
            return sorted;
        }
        return value === undefined ? null : value;
    };
    var same = function (a, b) {
        return JSON.stringify(comparable(a)) === JSON.stringify(comparable(b));
    };
    var form = {};
    var values = arguments;
    answer.reads.forEach(function (key, i) { form[key] = values[3 + i]; });
    var fields = {};
    var baseline = null;
    if (snapshot && answer.name === name && snapshot.name === name) {
        answer.groups.forEach(function (group) {
            var stale = Object.keys(group.baseline).some(function (key) {
                return !same(group.seen_form[key], form[key])
                    || !same(group.seen_baseline[key], snapshot[key]);
            });
            if (stale) return;
            Object.assign(fields, group.fields);
            baseline = Object.assign(baseline || Object.assign({}, snapshot), group.baseline);
        });
    }
    return answer.writes.map(function (key) {
        return key in fields ? fields[key] : dc.no_update;
    }).concat([baseline || dc.no_update]);
};

// A Goal's or Milestone's time is the sum of its children's, so Inherit stays
// on. In the browser, a click that turns it off bounces back in the same paint.
window.dash_clientside.editor_form.lock_time_mode = function (time_mode_val, node_type) {
    var no_update = window.dash_clientside.no_update;
    var hidden = {display: "none"};
    var visible = {display: "block", color: "var(--st-danger-text)", fontSize: "var(--st-fs-base)"};
    var note = {display: "block", color: "var(--st-text-dim)", fontSize: "var(--st-fs-base)"};
    var ctx = window.dash_clientside.callback_context;
    var triggered = (ctx && ctx.triggered) || [];
    var ids = triggered.map(function(t) { return t.prop_id.split('.')[0]; });
    var only_time_mode = ids.length === 1 && ids[0] === 'node-time-mode';
    var only_type = ids.length === 1 && ids[0] === 'node-type';
    var store = window.SkillTree = window.SkillTree || {};
    var prev = store.editorTypeForTime;
    store.editorTypeForTime = node_type;
    var inherited_on = !!(time_mode_val && time_mode_val.indexOf('inherited') >= 0);

    if (node_type !== 'Goal' && node_type !== 'Milestone') {
        if (only_type && inherited_on && (prev === 'Goal' || prev === 'Milestone')) {
            if (node_type === 'Learn') {
                return [no_update, note, "Inherit came with the " + prev +
                        ". Keep it if this Learn is a header over its children; " +
                        "turn it off to give it its own estimate."];
            }
            return [[], hidden, ""];
        }
        return [time_mode_val, hidden, ""];
    }
    if (inherited_on) {
        if (only_time_mode) return [no_update, no_update, no_update];
        return [no_update, hidden, ""];
    }
    var msg = "Inherit mode is required for " + node_type + " nodes — " +
              "their time is the sum of their children's.";
    if (only_time_mode) return [['inherited'], visible, msg];
    return [['inherited'], hidden, ""];
};

// A Milestone's own ratings never enter scoring, so its value Inherit stays on.
window.dash_clientside.editor_form.lock_value_mode = function (value_mode_val, node_type) {
    var no_update = window.dash_clientside.no_update;
    var hidden = {display: "none"};
    var visible = {display: "block", color: "var(--st-danger-text)", fontSize: "var(--st-fs-base)"};
    var note = {display: "block", color: "var(--st-text-dim)", fontSize: "var(--st-fs-base)"};
    var ctx = window.dash_clientside.callback_context;
    var triggered = (ctx && ctx.triggered) || [];
    var ids = triggered.map(function(t) { return t.prop_id.split('.')[0]; });
    var only_value_mode = ids.length === 1 && ids[0] === 'node-value-mode';
    var only_type = ids.length === 1 && ids[0] === 'node-type';
    var store = window.SkillTree = window.SkillTree || {};
    var prev = store.editorTypeForValue;
    store.editorTypeForValue = node_type;
    var inherited_on = !!(value_mode_val && value_mode_val.indexOf('inherited') >= 0);

    if (node_type !== 'Milestone') {
        // A former Milestone gets its own ratings back, as the time
        // lock above gives back an estimate. A Learn may stay a
        // header that passes value through.
        if (only_type && inherited_on && prev === 'Milestone') {
            if (node_type === 'Learn') {
                return [no_update, note, "Inherit came with the Milestone. " +
                        "Keep it if this Learn only passes value through; " +
                        "turn it off to rate it."];
            }
            return [[], hidden, ""];
        }
        return [no_update, hidden, ""];
    }
    if (inherited_on) {
        if (only_value_mode) return [no_update, no_update, no_update];
        return [no_update, hidden, ""];
    }
    var msg = "Inherit is required for Milestone nodes — they are " +
              "checkpoints, so their own ratings don't affect scoring.";
    if (only_value_mode) return [['inherited'], visible, msg];
    return [['inherited'], hidden, ""];
};
