/**
 * Hide the "open link" icon button whenever its paired input is empty.
 *
 * Applies to External Resources rows rendered by `render_link_rows`
 * (obsidian / drive / website inputs in the node editor and in the
 * details-tab add-node form). The Python store only updates on
 * add / remove / browse, so this JS watches live typing via the
 * `input` event and sweeps the DOM on mutations for initial render
 * and store-driven re-renders.
 */
(function () {
    var LINK_TYPES = [
        'obsidian-link',
        'drive-link',
        'website-link',
        'details-add-obsidian-link',
        'details-add-drive-link',
        'details-add-website-link',
    ];

    function isLinkInput(el) {
        if (!el || el.tagName !== 'INPUT') return false;
        var id = el.id || '';
        for (var i = 0; i < LINK_TYPES.length; i++) {
            if (id.indexOf('"type":"' + LINK_TYPES[i] + '"') !== -1) return true;
        }
        return false;
    }

    function updateRow(input) {
        var row = input.closest('.d-flex');
        if (!row) return;
        var buttons = row.querySelectorAll('button');
        var openBtn = null;
        for (var i = 0; i < buttons.length; i++) {
            var bid = buttons[i].id || '';
            // Match only the "open" button in this row (ids look like
            // {"index":0,"type":"btn-obsidian-open"}).
            if (bid.indexOf('-open"') !== -1) {
                openBtn = buttons[i];
                break;
            }
        }
        if (!openBtn) return;
        var hasValue = (input.value || '').trim().length > 0;
        openBtn.classList.toggle('d-none', !hasValue);
    }

    document.addEventListener('input', function (e) {
        if (isLinkInput(e.target)) updateRow(e.target);
    });

    var sweepScheduled = false;
    function scheduleSweep() {
        if (sweepScheduled) return;
        sweepScheduled = true;
        requestAnimationFrame(function () {
            sweepScheduled = false;
            var inputs = document.querySelectorAll('input');
            for (var i = 0; i < inputs.length; i++) {
                if (isLinkInput(inputs[i])) updateRow(inputs[i]);
            }
        });
    }

    var observer = new MutationObserver(scheduleSweep);
    observer.observe(document.body, { childList: true, subtree: true });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scheduleSweep);
    } else {
        scheduleSweep();
    }
})();
