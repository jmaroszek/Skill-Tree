/**
 * obsidian.js
 * Handles the Browse (📁) and Open (🔗) buttons in the node editor
 * for linking and opening Obsidian files.
 */
(function () {
    function initObsidianButtons() {
        var browseBtn = document.getElementById('btn-obsidian-browse');
        var openBtn = document.getElementById('btn-obsidian-open');

        if (!browseBtn || !openBtn) {
            setTimeout(initObsidianButtons, 300);
            return;
        }

        browseBtn.addEventListener('click', function () {
            fetch('/browse-obsidian')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.path) {
                        var input = document.getElementById('node-obsidian-path');
                        if (input) {
                            // Update the underlying React/Dash input value
                            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            ).set;
                            nativeInputValueSetter.call(input, data.path);
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    }
                })
                .catch(function (err) { console.error('Browse failed:', err); });
        });

        openBtn.addEventListener('click', function () {
            var input = document.getElementById('node-obsidian-path');
            var path = input ? input.value.trim() : '';
            if (!path) {
                alert('No Obsidian file path set for this node.');
                return;
            }
            fetch('/open-obsidian?path=' + encodeURIComponent(path))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.ok) {
                        alert('Could not open Obsidian: ' + (data.error || 'unknown error'));
                    }
                })
                .catch(function (err) { console.error('Open failed:', err); });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initObsidianButtons);
    } else {
        initObsidianButtons();
    }
})();
