/* Native desktop picker. The Python tkinter picker remains the browser fallback. */
(function () {
    document.addEventListener('click', async function (event) {
        if (!window.skillTreeDesktop || !window.skillTreeDesktop.pickFile) return;
        var button = event.target.closest && event.target.closest('button[id]');
        if (!button) return;
        var id;
        try { id = JSON.parse(button.id); } catch (_) { return; }
        if (!id || !['btn-obsidian-browse', 'btn-drive-browse', 'btn-website-browse',
                       'custom-resource-browse'].includes(id.type)) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        var sectionId = id.type === 'btn-obsidian-browse' ? 'obsidian'
            : id.type === 'btn-drive-browse' ? 'drive'
            : id.type === 'btn-website-browse' ? 'website'
            : String(id.index).split(':')[0];
        var section = Array.from(document.querySelectorAll('[data-resource-id]'))
            .find(function (el) { return el.dataset.resourceId === sectionId; });
        var label = section && section.querySelector('label');
        try {
            var picked = await window.skillTreeDesktop.pickFile({
                title: 'Select ' + (label ? label.textContent : 'Resource') + ' file',
                defaultPath: section && section.dataset.resourceRoot || undefined,
                markdown: sectionId === 'obsidian',
            });
            if (!picked) return;
            var input = document.getElementById('electron-file-picked-input');
            if (!input) return;
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, JSON.stringify({ section: sectionId, index: id.index,
                                                  path: picked, nonce: Date.now() }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
        } catch (error) {
            console.error('Native file picker failed:', error);
        }
    }, true);
})();
