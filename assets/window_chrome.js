/* Tells the Electron shell when a modal's backdrop is fading in or out, so it
   can dim the window buttons with it. The OS draws them above the page, out of
   reach of the backdrop. The backdrop gets .show when its fade-in begins and
   loses it when its fade-out begins, which is earlier than body.modal-open
   clears. */
(function () {
    if (!window.skillTreeDesktop || !window.skillTreeDesktop.setModalOpen) return;

    var reported = false;
    var watched = new WeakSet();
    var classWatcher = new MutationObserver(report);

    function report() {
        var open = !!document.querySelector('.modal-backdrop.show');
        if (open === reported) return;
        reported = open;
        window.skillTreeDesktop.setModalOpen(open);
    }

    // Backdrops are added to <body>; each gets .show on the next frame.
    function watchBackdrops() {
        document.querySelectorAll('.modal-backdrop').forEach(function (el) {
            if (watched.has(el)) return;
            watched.add(el);
            classWatcher.observe(el, { attributes: true, attributeFilter: ['class'] });
        });
        report();
    }

    new MutationObserver(watchBackdrops).observe(document.body, { childList: true });
})();
