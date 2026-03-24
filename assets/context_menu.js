/**
 * Node context menu, double-click-to-edit, and group delete for the Skill Tree canvas.
 */
(function () {

    var _currentNodeData = null;

    function initContextMenu() {
        var cyWrapper = document.getElementById('cytoscape-graph');
        var menu = document.getElementById('node-context-menu');
        
        var editItem = document.getElementById('ctx-menu-edit');
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
        
        // --- Group Delete via Delete key ---
        function triggerGroupDelete(nodeNames) {
            // Write selected node names as JSON into the hidden Dash input
            var input = document.getElementById('group-delete-input');
            if (input) {
                // Use React's native value setter to ensure Dash picks up the change
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                // Add timestamp to ensure value is always "new" even if deleting same nodes
                nativeInputValueSetter.call(input, JSON.stringify(nodeNames) + '|' + Date.now());
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }

        function bindCyEvents() {
            var cy = getCy();
            if (!cy) {
                setTimeout(bindCyEvents, 500);
                return;
            }

            // --- Double-click to edit ---
            // Use native dblclick on the container since Cytoscape's dbltap
            // can be unreliable with boxSelectionEnabled.
            cyWrapper.addEventListener('dblclick', function (e) {
                var rect = cyWrapper.getBoundingClientRect();
                var rendPos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
                var modelPos = {
                    x: (rendPos.x - cy.pan().x) / cy.zoom(),
                    y: (rendPos.y - cy.pan().y) / cy.zoom()
                };

                // Find the node under the cursor
                var hitNode = null;
                cy.nodes().forEach(function (node) {
                    var bb = node.boundingBox();
                    if (modelPos.x >= bb.x1 && modelPos.x <= bb.x2 &&
                        modelPos.y >= bb.y1 && modelPos.y <= bb.y2) {
                        hitNode = node;
                    }
                });

                if (hitNode) {
                    e.preventDefault();
                    e.stopPropagation();
                    cy.$('node:selected').unselect();
                    hitNode.select();
                    triggerEdit();
                }
            });

            // --- Right-click context menu on nodes ---
            cy.on('cxttap', 'node', function (evt) {
                evt.originalEvent.preventDefault();
                
                // Hide tooltip when opening context menu
                var tooltip = document.getElementById('hover-tooltip');
                if (tooltip) tooltip.style.display = 'none';
                
                // Don't clear multi-selection if right-clicking a selected node
                if (!evt.target.selected()) {
                    cy.$('node:selected').unselect();
                    evt.target.select();
                }
                
                var nodeData = evt.target.data();
                var pos = evt.originalEvent;
                showMenu(pos.clientX, pos.clientY, nodeData);
            });

            // Click on background hides context menu
            cy.on('tap', function (evt) {
                if (evt.target === cy) hideMenu();
            });

            // Prevent browser context menu on cytoscape container
            cyWrapper.addEventListener('contextmenu', function (e) {
                e.preventDefault();
            });

            // --- Delete key for group delete ---
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Delete' || e.key === 'Backspace') {
                    // Don't intercept if user is typing in an input/textarea
                    var activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
                    if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') {
                        return;
                    }

                    var selected = cy.$('node:selected');
                    if (selected.length > 0) {
                        e.preventDefault();
                        var names = [];
                        selected.forEach(function (node) {
                            names.push(node.id());
                        });
                        
                        if (names.length > 0) {
                            var confirmMsg = names.length === 1
                                ? 'Delete node "' + names[0] + '"?'
                                : 'Delete ' + names.length + ' selected nodes?';
                            if (confirm(confirmMsg)) {
                                triggerGroupDelete(names);
                            }
                        }
                    }
                }
            });

            // --- Ctrl+S to save node editor ---
            document.addEventListener('keydown', function (e) {
                if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                    e.preventDefault();
                    _clickDashBtn('btn-save');
                }
            });
        }

        document.addEventListener('click', function (e) {
            if (!menu.contains(e.target)) hideMenu();
        });
        document.addEventListener('scroll', hideMenu);
        window.addEventListener('resize', hideMenu);

        if (editItem) editItem.addEventListener('click', triggerEdit);
        if (toggleDoneItem) toggleDoneItem.addEventListener('click', triggerToggleDone);
        
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
