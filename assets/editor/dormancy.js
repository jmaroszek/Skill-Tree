/**
 * The editor's Dormant section: what it collects into node-dormancy-form,
 * and which of its fields show. features/editor/dormancy.py registers them.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.editor_dormancy = window.dash_clientside.editor_dormancy || {};

// The section as one dict, which Save and the unsaved-changes check read.
window.dash_clientside.editor_dormancy.collect_form = function (dormant, event, eventName, delayOn, delayValue, delayUnit,
         wakeDate, now, snapshot) {
    function on(v) { return !!(v && v.indexOf('on') >= 0); }
    var saved = (snapshot && snapshot.dormancy) || {};
    var scheduled = saved.wake_date != null && !!event && event === saved.event;
    var delay = 0;
    if (!scheduled && on(delayOn)) {
        delay = (delayValue === undefined || delayValue === '') ? null : delayValue;
    }
    return {
        dormant: !!(dormant && dormant.indexOf('dormant') >= 0),
        event: event || null,
        event_name: eventName || '',
        delay_value: delay,
        delay_unit: delayUnit || 'days',
        // A cleared date stays '' rather than null, so Save can tell
        // a wake date that was emptied from no wake date at all.
        wake_date: scheduled ? (wakeDate || '') : null,
        now: on(now)
    };
};

// Now and Done hide while Dormant is on, and Dormant while Now or Done is.
window.dash_clientside.editor_dormancy.show_fields = function (dormant, now, done, event, delayOn, snapshot) {
    var hide = {display: 'none'}, show = {};
    var isDormant = !!(dormant && dormant.indexOf('dormant') >= 0);
    var isBusy = !!(now && now.length) || !!(done && done.length);
    var saved = (snapshot && snapshot.dormancy) || {};
    var scheduled = saved.wake_date != null && !!event && event === saved.event;
    var waking = !!saved.dormant && !isDormant;
    var warning = '';
    if (waking) {
        warning = saved.event
            ? 'Saving wakes this node and removes it from ' + saved.event + '.'
            : 'Saving wakes this node.';
    }
    return [
        isDormant ? hide : show,
        isDormant ? hide : show,
        (isBusy && !isDormant) ? hide : show,
        isDormant ? show : hide,
        event === '__new__' ? show : hide,
        event ? show : hide,
        scheduled ? show : hide,
        scheduled ? hide : show,
        (!scheduled && delayOn && delayOn.length) ? show : hide,
        waking ? show : hide,
        warning
    ];
};
