// Ctrl+S (Cmd+S on Mac) inside the Settings modal triggers the Save button.
// Restores the hotkey from when Settings was a tab.
(function () {
    document.addEventListener('keydown', function (e) {
        const isSaveCombo = (e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey
            && (e.key === 's' || e.key === 'S');
        if (!isSaveCombo) return;

        const modal = document.getElementById('settings-modal');
        if (!modal) return;
        // dbc.Modal renders with display:none when closed; check both visibility and class.
        const visible = modal.offsetParent !== null
            || modal.classList.contains('show')
            || modal.style.display === 'block';
        if (!visible) return;

        const btn = document.getElementById('btn-settings-save');
        if (!btn) return;

        e.preventDefault();
        e.stopPropagation();
        btn.click();
    }, true);
})();
