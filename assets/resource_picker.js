/* Native desktop picker. The Python tkinter picker remains the browser fallback. */
(function () {
    var FILE_BROWSE_TYPE = 'resource-browse';
    var FOLDER_BROWSE_TYPE = 'resource-section-root-browse';

    // React ignores a plain `el.value = ...`; the native setter plus an
    // input event is what makes Dash see the new value.
    function setInputValue(input, value) {
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // Settings root folder: the chosen folder goes straight into its field.
    async function pickFolder(id) {
        var input = document.getElementById(JSON.stringify(
            { index: id.index, type: 'resource-section-root' }));
        if (!input) return;
        var picked = await window.skillTreeDesktop.pickFile({
            title: 'Select folder',
            defaultPath: input.value || undefined,
            directory: true,
        });
        if (picked) setInputValue(input, picked);
    }

    // Node editor link: Python stores it relative to the section's root.
    async function pickFile(id) {
        var sectionId = String(id.index).split(':')[0];
        var section = Array.from(document.querySelectorAll('#editor-resources [data-resource-id]'))
            .find(function (el) { return el.dataset.resourceId === sectionId; });
        var label = section && section.querySelector('label');
        var picked = await window.skillTreeDesktop.pickFile({
            title: 'Select ' + (label ? label.textContent : 'Resource') + ' file',
            defaultPath: section && section.dataset.resourceRoot || undefined,
            markdown: !!section && section.dataset.resourceKind === 'obsidian',
        });
        if (!picked) return;
        var input = document.getElementById('electron-file-picked-input');
        if (!input) return;
        setInputValue(input, JSON.stringify({ index: id.index, path: picked,
                                              nonce: Date.now() }));
    }

    document.addEventListener('click', async function (event) {
        if (!window.skillTreeDesktop || !window.skillTreeDesktop.pickFile) return;
        var button = event.target.closest && event.target.closest('button[id]');
        if (!button) return;
        var id;
        try { id = JSON.parse(button.id); } catch (_) { return; }
        if (!id) return;
        var folder = id.type === FOLDER_BROWSE_TYPE;
        if (!folder && id.type !== FILE_BROWSE_TYPE) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        try {
            await (folder ? pickFolder(id) : pickFile(id));
        } catch (error) {
            console.error('Native file picker failed:', error);
        }
    }, true);
})();
