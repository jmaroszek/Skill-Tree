/**
 * Show a notice (skilltree/ui/notices.py): the line under the editor's Save,
 * and for an error the dialog too. No notice blanks the line, so one action's
 * message doesn't outlive the next action. engine/callbacks.py registers it,
 * and ui/toast.py clears the line a few seconds after it last changed.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.notices = window.dash_clientside.notices || {};

window.dash_clientside.notices.show = function (notice, _closeClicks) {
    var NO = window.dash_clientside.no_update;
    var ctx = window.dash_clientside.callback_context;
    var closing = ((ctx && ctx.triggered) || []).some(function (fired) {
        return fired.prop_id.indexOf('btn-close-error.') === 0;
    });
    if (closing) return [NO, false, NO];
    if (!notice) return ['', NO, NO];
    if (notice.kind === 'error') return [notice.text, true, notice.text];
    return [notice.text, NO, NO];
};
