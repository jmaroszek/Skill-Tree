/**
 * The node editor form's clientside callbacks: links changed elsewhere, and
 * the Inherit locks. features/editor/callbacks.py registers them.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.editor_form = window.dash_clientside.editor_form || {};

// The answer is applied against the editor as it is when it lands. If another
// node has loaded, or the user has changed a picker since, it is stale and
// is dropped rather than written into the form.
window.dash_clientside.editor_form.follow_relationships = function (follow, name, snapshot, needsHard, needsSoft, suppHard, suppSoft, helps) {
    var NO = window.dash_clientside.no_update;
    var keys = ['e_needs_h', 'e_needs_s', 'e_supp_h', 'e_supp_s', 'e_helps'];
    var form = {e_needs_h: needsHard, e_needs_s: needsSoft, e_supp_h: suppHard,
                e_supp_s: suppSoft, e_helps: helps};
    var unchanged = [NO, NO, NO, NO, NO, NO];
    if (!follow || !snapshot || follow.name !== name || snapshot.name !== name) {
        return unchanged;
    }
    var same = function (a, b) {
        return JSON.stringify(a || []) === JSON.stringify(b || []);
    };
    for (var key in follow.seen) {
        if (!same(follow.seen[key].snapshot, snapshot[key])
                || !same(follow.seen[key].form, form[key])) {
            return unchanged;
        }
    }
    var out = keys.map(function (key) {
        return key in follow.values ? follow.values[key] : NO;
    });
    out.push(Object.assign({}, snapshot, follow.snapshot));
    return out;
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
