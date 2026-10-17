// Enter in the Goals or Bottlenecks "shown" box commits the number and closes
// its popover. The input is debounced, so Dash already commits on Enter; this
// then clicks the gear so the popover's own toggle does the closing, and
// returns focus to the gear.
(function () {
    const GEARS = {
        'popover-analyze-goals': 'btn-analyze-goals-limit',
        'popover-analyze-bottlenecks': 'btn-analyze-bottlenecks-limit',
    };

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' || e.isComposing) return;
        const input = e.target;
        if (!input.matches || !input.matches('input[type="number"]')) return;
        const popover = input.closest('.popover');
        const gear = popover && document.getElementById(GEARS[popover.id]);
        if (!gear) return;
        // After React's own Enter handler has committed the value.
        setTimeout(function () {
            gear.click();
            gear.focus();
        }, 0);
    });
})();
