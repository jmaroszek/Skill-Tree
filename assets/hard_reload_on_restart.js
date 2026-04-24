/**
 * Hard-reload the browser whenever the Dev server restarts.
 *
 * Dash's built-in soft hot-reload leaves the Cytoscape canvas wired to a
 * detached cy instance after Python edits — pan/zoom/select stop working
 * until F5. We short-circuit that by polling a server-boot-id endpoint
 * (generated fresh each time the Python process starts) and issuing a
 * full reload on mismatch.
 *
 * Paired with `dev_tools_hot_reload=False` in app.py so Dash's own
 * polling doesn't race with ours.
 */
(function () {
    var bootId = null;

    function check() {
        fetch('/_server_boot_id')
            .then(function (r) { return r.text(); })
            .then(function (id) {
                id = (id || '').trim();
                if (!id) return;
                if (bootId === null) {
                    bootId = id;
                } else if (id !== bootId) {
                    window.location.reload();
                }
            })
            .catch(function () { /* werkzeug mid-restart — ignore */ });
    }

    check();
    setInterval(check, 2000);
})();
