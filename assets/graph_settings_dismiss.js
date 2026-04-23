// Close any open graph-settings panel when the user clicks outside of it.
// Works by simulating a click on the panel's toggle button so Dash's
// existing toggle callback keeps its State in sync with the DOM.
(function () {
    const PANELS = [
        ['graph-settings-panel', 'btn-graph-settings'],
        ['details-graph-settings-panel', 'btn-details-graph-settings'],
        ['events-graph-settings-panel', 'btn-events-graph-settings'],
    ];

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
