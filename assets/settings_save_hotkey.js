/** One save shortcut, scoped to the editor that currently has focus. */
(function () {
    'use strict';
    document.addEventListener('keydown', function (e) {
        if (e.defaultPrevented || e.isComposing || !(e.ctrlKey || e.metaKey) ||
                e.shiftKey || e.altKey || e.key.toLowerCase() !== 's') return;
        var target = e.target;
        var modal = target.closest('.modal.show');
        var buttonId;
        if (modal) {
            if (target.closest('#settings-modal')) buttonId = 'btn-settings-save';
        } else if (!document.querySelector('.modal.show, dialog[open]')) {
            if (target.closest('#sidebar-editor-container:not([inert])')) buttonId = 'btn-save';
            else if (target.closest('#events-detail-panel')) buttonId = 'btn-event-save';
        }
        var button = buttonId && document.getElementById(buttonId);
        if (!button || button.disabled || !window.SkillTree.keyboardFocus.visible(button)) return;
        e.preventDefault();
        e.stopPropagation();
        button.click();
    }, true);
}());
