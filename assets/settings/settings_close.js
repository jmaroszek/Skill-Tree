/** All Settings dismissal paths request one acknowledged save before hiding. */
(function () {
    'use strict';
    var pending = null;
    var quietSince = 0;

    function modal() { return document.getElementById('settings-modal'); }
    function topmost() {
        var root = modal();
        return Boolean(root && Array.from(document.querySelectorAll('.modal.show')).at(-1) ===
            root.closest('.modal'));
    }
    function freeze(value) {
        var content = modal() && modal().querySelector('.modal-content');
        if (content) content.inert = value;
        var button = document.getElementById('btn-settings-close');
        if (button) button.disabled = value;
    }
    function requestClose() {
        if (pending || !topmost() || document.querySelector('dialog[open]')) return;
        // Blur flushes native/debounced field edits. Wait for structural edits,
        // dependent time-field updates and opening loads to finish before Dash
        // captures the form's State. Freeze the draft throughout this wait/save.
        if (document.activeElement && modal().contains(document.activeElement)) {
            document.activeElement.blur();
        }
        var id = Date.now() + ':' + Math.random();
        pending = {id: id, started: Date.now()};
        freeze(true);
        quietSince = 0;
        setTimeout(function () { settle(id); }, 0);
    }
    function settle(id) {
        if (!pending || pending.id !== id) return;
        if (Date.now() - pending.started > 20000) {
            freeze(false);
            pending = null;
            window.dash_clientside.set_props('settings-save-status', {
                children: "Settings are still loading. Please try closing again."});
            return;
        }
        if (document.querySelector('._dash-loading-callback')) quietSince = 0;
        else if (!quietSince) quietSince = Date.now();
        if (quietSince && Date.now() - quietSince >= 150) {
            window.dash_clientside.set_props('settings-save-status', {children: ''});
            window.dash_clientside.set_props('settings-close-request', {data: pending.id});
            quietSince = 0;
            setTimeout(function () { checkResponse(id); }, 250);
        } else setTimeout(function () { settle(id); }, 25);
    }
    function checkResponse(id) {
        if (!pending || pending.id !== id) return;
        if (document.querySelector('._dash-loading-callback')) quietSince = 0;
        else if (!quietSince) quietSince = Date.now();
        if (quietSince && Date.now() - quietSince >= 1000) {
            // A rejected network request or an unexpected Dash error may end
            // without our result. Keep the draft usable and allow a retry.
            freeze(false);
            pending = null;
            window.dash_clientside.set_props('settings-save-status', {
                children: "Couldn't confirm settings were saved. Please try closing again."});
        } else setTimeout(function () { checkResponse(id); }, 250);
    }
    window.SkillTree.settingsClose = {
        finished: function (result) {
            if (!pending || result !== pending.id) return;
            freeze(false);
            pending = null;
            // Bootstrap focus stays in the dialog after a failed save. Return
            // to a useful control if freezing moved focus to the document body.
            if (topmost() && document.activeElement === document.body) {
                window.SkillTree.keyboardFocus.focus(document.getElementById('btn-settings-close'));
            }
        }
    };
    window.SkillTree.keyboardFocus.register({id: 'settings-modal',
        triggerId: 'btn-settings-toggle', closeId: 'btn-settings-close',
        isOpen: function (el) { return Boolean(el.closest('.modal.show')); }});
    window.SkillTree.keyboardFocus.register({id: 'modal-migration',
        triggerId: 'btn-settings-close', closeId: 'btn-migration-cancel',
        isOpen: function (el) { return Boolean(el.closest('.modal.show')); }});

    var pressedOutside = false;
    document.addEventListener('mousedown', function (e) {
        pressedOutside = topmost() && !e.target.closest('.modal-dialog');
    }, true);
    document.addEventListener('click', function (e) {
        // Its native X must run the same draft-preserving Cancel callback as
        // Escape/the footer; merely hiding the dialog leaves a stale pending save.
        if (e.target.closest('#modal-migration .btn-close')) {
            e.preventDefault();
            e.stopImmediatePropagation();
            document.getElementById('btn-migration-cancel').click();
            return;
        }
        if (!topmost()) return;
        var button = e.target.closest('#btn-settings-close, #btn-settings-toggle');
        var outside = pressedOutside && !e.target.closest('.modal-dialog');
        pressedOutside = false;
        if (!button && !outside) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        requestClose();
    }, true);
}());
