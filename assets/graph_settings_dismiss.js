// Close any open graph-settings panel, or the scoring profile info popover,
// when the user clicks outside of it. Works by simulating a click on the
// panel's toggle button so Dash's existing toggle callback keeps its State
// in sync with the DOM.
(function () {
    const PANELS = window.SkillTree.canvases.map(function (canvas) {
        return [canvas.settingsPanelId, canvas.settingsToggleId];
    }).concat([['popover-hp-profile-info', 'btn-hp-profile-info']]);
    window.SkillTree.keyboardFocus.register({id: 'popover-hp-profile-info',
        modalId: 'settings-modal',
        triggerId: 'btn-hp-profile-info', isOpen: function (el) {
            return window.SkillTree.keyboardFocus.visible(el);
        }, dismiss: function () { document.getElementById('btn-hp-profile-info').click(); }});

    function handleOutsideClick(e) {
        for (const [panelId, btnId] of PANELS) {
            const panel = document.getElementById(panelId);
            if (!panel) continue;
            if (getComputedStyle(panel).display === 'none') continue;
            if (panel.contains(e.target)) continue;
            const btn = document.getElementById(btnId);
            if (btn && btn.contains(e.target)) continue;
            if (!btn) continue;
            btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
        }
    }

    // Use mousedown (capture) to run before any stopPropagation from child handlers
    // (e.g. Cytoscape's canvas event layer).
    document.addEventListener('mousedown', handleOutsideClick, true);
})();
