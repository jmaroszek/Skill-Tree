/* Tells the Electron shell when a modal is open, so it can dim the window
   buttons. The OS draws them above the page, out of reach of the backdrop. */
(function () {
    if (!window.skillTreeDesktop || !window.skillTreeDesktop.setModalOpen) return;

    var reported = false;

    function report() {
        var open = document.body.classList.contains('modal-open');
        if (open === reported) return;
        reported = open;
        window.skillTreeDesktop.setModalOpen(open).catch(function () {});
    }

    new MutationObserver(report).observe(document.body, {
        attributes: true, attributeFilter: ['class'],
    });
})();
