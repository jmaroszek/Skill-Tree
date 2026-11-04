/**
 * Clicking "New event" puts the cursor in the event name field.
 *
 * The click only asks the server to open an empty form, so the field shows a
 * moment later. Wait for it to be visible, then focus it. A keyboard press
 * (detail 0) takes the sidebar-aware path in keyboard_navigation.js instead.
 */
(function () {
    document.addEventListener('click', function (e) {
        if (e.detail === 0 || !e.target.closest('#btn-new-event')) return;
        var deadline = Date.now() + 5000;
        (function attempt() {
            var name = document.getElementById('event-name');
            if (name && name.offsetParent !== null) { name.focus(); return; }
            if (Date.now() < deadline) setTimeout(attempt, 50);
        })();
    });
})();
