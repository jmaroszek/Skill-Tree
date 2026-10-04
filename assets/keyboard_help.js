/** A local, explicit shortcut reference. Native dialog owns its focus trap. */
(function () {
    'use strict';
    var dialog, opener;
    var shortcuts = [
        ['Tab / Shift+Tab', 'Move through controls. Open panels keep focus until Escape or Close.'],
        ['Enter / Space', 'Activate a button or card.'],
        ['Left / Right, Home / End on tabs', 'Choose a tab; Enter or Space opens it.'],
        ['Arrows, Home / End on cards', 'Browse a list. Tab leaves the list or reaches the current card’s controls.'],
        ['Escape', 'Dismiss the innermost menu or panel and return focus. Draft checks still apply.'],
        ['Ctrl+S / Cmd+S', 'Save the focused node editor, event editor, or Settings.'],
        ['Shift+F10 / Menu key', 'Open actions for a card or graph node.'],
        ['Arrows, Home / End in menus', 'Choose an action. Right / Left enters or leaves a submenu.'],
        ['Alt+arrows', 'Reorder a Now card or a goal, event, context, or subcontext reorder handle.'],
        ['Arrows on a graph', 'Move toward a node in that direction. Page Up / Down browses all nodes by name.'],
        ['Home / End on a graph', 'Focus the first or last node by name.'],
        ['Enter / Shift+Enter on a graph', 'Select the focused node, or add it to the selection. The blue halo marks focus; white borders mark selection.'],
        ['Escape on a graph', 'Clear graph focus and selection before leaving fullscreen.'],
        ['Delete on the Nodes graph', 'Ask to delete selected nodes.'],
        ['+ / −, 0 on a graph', 'Zoom in / out, or fit the graph.'],
        ['Arrows on dividers', 'Resize the adjacent panels. Shift takes larger steps; Home / End goes to a limit.'],
    ];
    function open() {
        if (!dialog) {
            dialog = document.createElement('dialog');
            dialog.className = 'keyboard-help';
            dialog.setAttribute('aria-labelledby', 'keyboard-help-title');
            var title = document.createElement('h4');
            title.id = 'keyboard-help-title'; title.textContent = 'Keyboard controls';
            title.tabIndex = -1;
            title.setAttribute('autofocus', '');
            dialog.appendChild(title);
            var table = document.createElement('table');
            shortcuts.forEach(function (shortcut) {
                var row = table.insertRow();
                var key = document.createElement('th');
                key.scope = 'row'; key.textContent = shortcut[0];
                row.appendChild(key); row.insertCell().textContent = shortcut[1];
            });
            dialog.appendChild(table);
            var close = document.createElement('button');
            close.className = 'btn btn-secondary'; close.textContent = 'Close';
            close.addEventListener('click', function () { dialog.close(); });
            dialog.appendChild(close);
            dialog.addEventListener('close', function () { window.SkillTree.keyboardFocus.focus(opener); });
            document.body.appendChild(dialog);
        }
        if (dialog.open) return;
        opener = document.activeElement;
        dialog.showModal();
        dialog.scrollTop = 0;
        window.SkillTree.keyboardFocus.focus(document.getElementById('keyboard-help-title'));
    }
    document.addEventListener('keydown', function (e) {
        if (dialog && dialog.open && (e.key === 'Tab' || e.key === 'Escape')) {
            // Bootstrap's underlying modal also listens for these keys. The
            // reference owns them until it closes, including the one-button
            // Tab cycle that browsers otherwise allow to visit browser chrome.
            e.preventDefault(); e.stopImmediatePropagation();
            if (e.key === 'Escape') dialog.close();
            else {
                var items = window.SkillTree.keyboardFocus.controls(dialog);
                var index = items.indexOf(document.activeElement);
                var next = index < 0 ? (e.shiftKey ? items.length - 1 : 0)
                    : (index + (e.shiftKey ? -1 : 1) + items.length) % items.length;
                window.SkillTree.keyboardFocus.focus(items[next]);
            }
            return;
        }
        if (e.key === 'F1' && !e.ctrlKey && !e.altKey && !e.metaKey) {
            e.preventDefault(); e.stopImmediatePropagation(); open();
        }
    }, true);
}());
