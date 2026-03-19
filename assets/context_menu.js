/**
 * Node context menu and double-click-to-edit for the Skill Tree canvas.
 *
 * - Double-tap (dblclick) a node → triggers the editor
 * - Right-click (cxttap) a node → shows a context menu with "Edit"
 *
 * Both actions programmatically click a hidden button (#btn-edit-node)
 * to open the Dash Offcanvas editor via callback.
 */
(function () {

    function initContextMenu() {
        var cyWrapper = document.getElementById('cytoscape-graph');
        var menu = document.getElementById('node-context-menu');
        var editBtn = document.getElementById('btn-edit-node');

        if (!cyWrapper || !menu || !editBtn) {
            setTimeout(initContextMenu, 300);
            return;
        }

        function getCy() {
            return (cyWrapper._cyreg && cyWrapper._cyreg.cy) ? cyWrapper._cyreg.cy : null;
        }

        function hideMenu() {
            menu.style.display = 'none';
        }

        function showMenu(x, y) {
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
            menu.style.display = 'block';

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
                var pos = evt.originalEvent;
                showMenu(pos.clientX, pos.clientY);
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

        bindCyEvents();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initContextMenu);
    } else {
        initContextMenu();
    }
})();
