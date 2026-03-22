/**
 * Node context menu and double-click-to-edit for the Skill Tree canvas.
 */
(function () {

    var _currentNodeData = null;

    function initContextMenu() {
        var cyWrapper = document.getElementById('cytoscape-graph');
        var menu = document.getElementById('node-context-menu');
        
        var editItem = document.getElementById('ctx-menu-edit');
        var depsItem = document.getElementById('ctx-menu-deps');
        var synsItem = document.getElementById('ctx-menu-syns');
        var obsidianItem = document.getElementById('ctx-menu-obsidian');
        var driveItem = document.getElementById('ctx-menu-drive');
        var toggleDoneItem = document.getElementById('ctx-menu-toggle-done');

        if (!cyWrapper || !menu || !obsidianItem) {
            setTimeout(initContextMenu, 300);
            return;
        }

        function getCy() {
            return (cyWrapper._cyreg && cyWrapper._cyreg.cy) ? cyWrapper._cyreg.cy : null;
        }

        function hideMenu() {
            menu.style.display = 'none';
        }

        function showMenu(x, y, nodeData) {
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
            menu.style.display = 'block';
            
            _currentNodeData = nodeData;

            if (nodeData.obsidian_path) {
                obsidianItem.style.opacity = '1';
                obsidianItem.style.cursor = 'pointer';
                obsidianItem.style.pointerEvents = 'auto';
            } else {
                obsidianItem.style.opacity = '0.4';
                obsidianItem.style.cursor = 'default';
                obsidianItem.style.pointerEvents = 'none';
            }
            
            if (nodeData.google_drive_path) {
                driveItem.style.opacity = '1';
                driveItem.style.cursor = 'pointer';
                driveItem.style.pointerEvents = 'auto';
            } else {
                driveItem.style.opacity = '0.4';
                driveItem.style.cursor = 'default';
                driveItem.style.pointerEvents = 'none';
            }

            var rect = menu.getBoundingClientRect();
            if (rect.right > window.innerWidth) menu.style.left = (x - rect.width) + 'px';
            if (rect.bottom > window.innerHeight) menu.style.top = (y - rect.height) + 'px';
        }

        function _clickDashBtn(btnId) {
            var btn = document.getElementById(btnId);
            if (btn) {
                btn.dispatchEvent(new MouseEvent('click', { view: window, bubbles: true, cancelable: true }));
            }
        }

        function triggerEdit() {
            hideMenu();
            _clickDashBtn('btn-edit-node');
        }

        function triggerToggleDone() {
            hideMenu();
            _clickDashBtn('btn-toggle-done-node');
        }

        function openInObsidian(path) {
            if (!path) return;
            hideMenu();
            fetch('/open-obsidian?path=' + encodeURIComponent(path))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.ok) alert('Could not open Obsidian: ' + (data.error || 'unknown'));
                })
                .catch(function (err) { console.error('Open in Obsidian failed:', err); });
        }
        
        function switchTab(tabId) {
            hideMenu();
            var tabBtn = document.querySelector(`button#${tabId}`);
            if (tabBtn) tabBtn.click();
        }

        function bindCyEvents() {
            var cy = getCy();
            if (!cy) {
                setTimeout(bindCyEvents, 500);
                return;
            }

            var lastTapTime = 0;
            var lastTapNode = null;

            cy.on('tap', 'node', function (evt) {
                var now = Date.now();
                if (lastTapNode === evt.target && now - lastTapTime < 400) {
                    if (evt.originalEvent && evt.originalEvent.preventDefault) {
                        evt.originalEvent.preventDefault();
                    }
                    cy.$('node:selected').unselect();
                    evt.target.select();
                    triggerEdit();
                    lastTapTime = 0;
                } else {
                    lastTapTime = now;
                    lastTapNode = evt.target;
                }
            });

            cy.on('cxttap', 'node', function (evt) {
                evt.originalEvent.preventDefault();
                
                cy.$('node:selected').unselect();
                evt.target.select();
                
                var nodeData = evt.target.data();
                var pos = evt.originalEvent;
                showMenu(pos.clientX, pos.clientY, nodeData);
            });

            cy.on('tap', function (evt) {
                if (evt.target === cy) hideMenu();
            });

            cyWrapper.addEventListener('contextmenu', function (e) {
                e.preventDefault();
            });
        }

        document.addEventListener('click', function (e) {
            if (!menu.contains(e.target)) hideMenu();
        });
        document.addEventListener('scroll', hideMenu);
        window.addEventListener('resize', hideMenu);

        if (editItem) editItem.addEventListener('click', triggerEdit);
        if (toggleDoneItem) toggleDoneItem.addEventListener('click', triggerToggleDone);
        
        if (depsItem) depsItem.addEventListener('click', function() { switchTab('tab-dependencies'); });
        if (synsItem) synsItem.addEventListener('click', function() { switchTab('tab-synergies'); });
        
        if (obsidianItem) {
            obsidianItem.addEventListener('click', function () {
                if (_currentNodeData) openInObsidian(_currentNodeData.obsidian_path);
            });
        }
        
        if (driveItem) {
            driveItem.addEventListener('click', function () {
                hideMenu();
                if (_currentNodeData && _currentNodeData.google_drive_path) {
                    window.open(_currentNodeData.google_drive_path, '_blank');
                }
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
