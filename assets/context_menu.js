/**
 * Node context menu and double-click-to-edit for the Skill Tree canvas.
 *
 * - Double-tap (dblclick) a node → triggers the editor
 * - Right-click (cxttap) a node → shows a context menu with "Edit" and "Open in Obsidian"
 *
 * Both actions programmatically click a hidden button (#btn-edit-node)
 * to open the Dash Offcanvas editor via callback.
 */
(function () {

    var _currentNodeObsidianPath = null;

    function initContextMenu() {
        var cyWrapper = document.getElementById('cytoscape-graph');
        var menu = document.getElementById('node-context-menu');
        var editBtn = document.getElementById('btn-edit-node');
        var obsidianItem = document.getElementById('ctx-menu-obsidian');

        if (!cyWrapper || !menu || !editBtn || !obsidianItem) {
            setTimeout(initContextMenu, 300);
            return;
        }

        function getCy() {
            return (cyWrapper._cyreg && cyWrapper._cyreg.cy) ? cyWrapper._cyreg.cy : null;
        }

        function hideMenu() {
            menu.style.display = 'none';
        }

        function showMenu(x, y, obsidianPath) {
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
            menu.style.display = 'block';

            // Style the Obsidian item based on whether a path exists
            if (obsidianPath) {
                obsidianItem.style.opacity = '1';
                obsidianItem.style.cursor = 'pointer';
                obsidianItem.style.pointerEvents = 'auto';
            } else {
                obsidianItem.style.opacity = '0.4';
                obsidianItem.style.cursor = 'default';
                obsidianItem.style.pointerEvents = 'none';
            }

            // Adjust if menu goes off-screen
            var rect = menu.getBoundingClientRect();
            if (rect.right > window.innerWidth) {
                menu.style.left = (x - rect.width) + 'px';
            }
            if (rect.bottom > window.innerHeight) {
                menu.style.top = (y - rect.height) + 'px';
            }
        }

        function triggerEdit() {
            hideMenu();
            // Click the hidden edit button to trigger the Dash callback
            editBtn.click();
        }

        function openInObsidian(path) {
            if (!path) return;
            hideMenu();
            fetch('/open-obsidian?path=' + encodeURIComponent(path))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.ok) {
                        alert('Could not open Obsidian: ' + (data.error || 'unknown error'));
                    }
                })
                .catch(function (err) { console.error('Open in Obsidian failed:', err); });
        }

        function bindCyEvents() {
            var cy = getCy();
            if (!cy) {
                setTimeout(bindCyEvents, 500);
                return;
            }

            // Double-click a node → open editor
            cy.on('dbltap', 'node', function (evt) {
                evt.originalEvent.preventDefault();
                triggerEdit();
            });

            // Right-click a node → show context menu
            cy.on('cxttap', 'node', function (evt) {
                evt.originalEvent.preventDefault();
                var nodeData = evt.target.data();
                _currentNodeObsidianPath = nodeData.obsidian_path || null;
                var pos = evt.originalEvent;
                showMenu(pos.clientX, pos.clientY, _currentNodeObsidianPath);
            });

            // Click anywhere else → hide context menu
            cy.on('tap', function (evt) {
                if (evt.target === cy) {
                    hideMenu();
                }
            });

            // Prevent browser context menu on the canvas
            cyWrapper.addEventListener('contextmenu', function (e) {
                e.preventDefault();
            });
        }

        // Hide menu on scroll, resize, or click outside
        document.addEventListener('click', function (e) {
            if (!menu.contains(e.target)) {
                hideMenu();
            }
        });
        document.addEventListener('scroll', hideMenu);
        window.addEventListener('resize', hideMenu);

        // "Edit" menu item click
        var editItem = document.getElementById('ctx-menu-edit');
        if (editItem) {
            editItem.addEventListener('click', triggerEdit);
        }

        // "Open in Obsidian" menu item click
        if (obsidianItem) {
            obsidianItem.addEventListener('click', function () {
                openInObsidian(_currentNodeObsidianPath);
            });
        }

        bindCyEvents();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initContextMenu);
    } else {
        initContextMenu();
    }
})();
