/**
 * Node context menu, multi-select, and group delete for the Skill Tree canvases.
 *
 * One menu serves every place a node appears: the canvases, and the rows and
 * cards that carry node_menu_attributes (callback_helpers.py) — Next
 * suggestions, Now cards and Goals sidebar cards. menus.js positions and
 * closes it.
 */
(function () {

    var _currentNodeData = null;
    var _menuSource = 'main';

    // bindCyEvents gives the Nodes canvas the full handler set. Every other
    // canvas in the registry shares bindMiniGraphMenu.
    var MAIN_CANVAS = window.SkillTree.canvases.filter(function (canvas) {
        return canvas.key === 'main';
    })[0];
    // Canvases where right-clicking a node also selects it, as on Nodes.
    var SELECT_ON_RIGHT_CLICK = { events: true };

    function initContextMenu() {
        var cyWrapper = document.getElementById(MAIN_CANVAS.cytoscapeId);
        var menu = document.getElementById('node-context-menu');

        // Menu items are clicked through menus.onItem; these are the ones
        // whose label or visibility depends on the node.
        var websiteItem = document.getElementById('ctx-menu-website');
        var obsidianItem = document.getElementById('ctx-menu-obsidian');
        var driveItem = document.getElementById('ctx-menu-drive');
        var linksDivider = document.getElementById('ctx-menu-links-divider');
        var toggleNowItem = document.getElementById('ctx-menu-toggle-now');
        var priorityItem = document.getElementById('ctx-menu-priority');
        var priorityDivider = document.getElementById('ctx-menu-priority-divider');
        var toggleDoneItem = document.getElementById('ctx-menu-toggle-done');
        var addToEventItem = document.getElementById('ctx-menu-add-to-event');
        var deleteItem = document.getElementById('ctx-menu-delete');

        if (!cyWrapper || !menu || !window.SkillTree.menus) {
            setTimeout(initContextMenu, 300);
            return;
        }

        function _getFirstLink(pathData) {
            if (!pathData) return null;
            try {
                var parsed = JSON.parse(pathData);
                if (Array.isArray(parsed)) return parsed[0] || null;
            } catch(e) {}
            return pathData;
        }

        var menus = window.SkillTree.menus;

        function hideMenu() {
            menus.hideAll();
        }

        // A row or card isn't part of any canvas's selection, so it always
        // acts on its own node alone.
        function _currentTargetNodes() {
            if (!_currentNodeData || !_currentNodeData.id) return [];
            if (!_menuCy) return [_currentNodeData];

            var selected = _menuCy.$('node:selected');
            var includesCurrent = false;
            selected.forEach(function (node) {
                if (node.id() === _currentNodeData.id) includesCurrent = true;
            });
            if (selected.length <= 1 || !includesCurrent) {
                return [_currentNodeData];
            }

            var nodes = [];
            selected.forEach(function (node) { nodes.push(node.data()); });
            return nodes;
        }

        function _currentTargetIds() {
            return _currentTargetNodes().map(function (node) { return node.id; });
        }

        function showMenu(x, y, nodeData) {
            _currentNodeData = nodeData;

            var targets = _currentTargetNodes();
            var targetCount = targets.length || 1;
            var allNow = targets.length > 0 && targets.every(function (node) {
                return Number(node.now) > 0;
            });
            var allDone = targets.length > 0 && targets.every(function (node) {
                return node.status === 'Done';
            });
            toggleNowItem.textContent = targetCount > 1
                ? (allNow ? 'Remove ' + targetCount + ' from Now' : 'Add ' + targetCount + ' to Now')
                : (allNow ? 'Remove from Now' : 'Add to Now');
            toggleDoneItem.textContent = targetCount > 1
                ? (allDone ? 'Reopen ' + targetCount : 'Mark ' + targetCount + ' Done')
                : (allDone ? 'Reopen' : 'Mark Done');
            addToEventItem.textContent = targetCount > 1
                ? 'Add ' + targetCount + ' to Event…'
                : 'Add to Event…';
            deleteItem.textContent = targetCount > 1
                ? 'Delete ' + targetCount + '…'
                : 'Delete…';
            // A priority is one Goal's rank, so it has no bulk form. The
            // section goes with its divider, leaving every other node's menu
            // exactly as it is.
            var showPriority = targetCount === 1 && nodeData.type === 'Goal';
            priorityItem.style.display = showPriority ? '' : 'none';
            if (priorityDivider) priorityDivider.style.display = showPriority ? '' : 'none';

            var hasWebsite = _getFirstLink(nodeData.website);
            websiteItem.style.display = hasWebsite ? '' : 'none';

            var hasObsidian = _getFirstLink(nodeData.obsidian_path);
            obsidianItem.style.display = hasObsidian ? '' : 'none';

            var hasDrive = _getFirstLink(nodeData.google_drive_path);
            driveItem.style.display = hasDrive ? '' : 'none';

            // Collapse the upper divider when neither link is present, so the
            // remaining (lower) Hr doesn't sit doubled-up against this one.
            if (linksDivider) {
                linksDivider.style.display = (hasWebsite || hasObsidian || hasDrive) ? '' : 'none';
            }

            menus.open(menu, x, y);
        }

        function _clickDashBtn(btnId) {
            var btn = document.getElementById(btnId);
            if (btn) {
                btn.dispatchEvent(new MouseEvent('click', { view: window, bubbles: true, cancelable: true }));
            }
        }

        function _setHiddenInput(inputId, value) {
            menus.send(inputId, value + '|' + Date.now());
        }

        function triggerEdit() {
            if (_menuSource === 'events' && _currentNodeData && _currentNodeData.dormant && _currentNodeData.id) {
                // Events tab dormant node: route to the dormant-specific modal
                // instead of the generic sidebar editor (which refuses dormant nodes).
                _setHiddenInput('dormant-edit-trigger-input', _currentNodeData.id);
            } else if (_menuSource !== 'main' && _currentNodeData && _currentNodeData.id) {
                // Anywhere but the Nodes canvas: open the editor in place without switching tabs.
                // edit-trigger-input would force a switch to tab-canvas (see handle_edit_trigger).
                _setHiddenInput('details-edit-trigger-input', _currentNodeData.id);
            } else if (_currentNodeData && _currentNodeData.id) {
                // Nodes canvas: use edit-trigger-input which carries the
                // node ID explicitly, avoiding reliance on tapNodeData.
                _setHiddenInput('edit-trigger-input', _currentNodeData.id);
            } else {
                _clickDashBtn('btn-edit-node');
            }
        }

        function triggerToggleDone() {
            // Always prefer the explicit-ID trigger: on the main canvas a right-click
            // does not update cytoscape's tapNodeData, so btn-toggle-done-node would
            // act on whichever node was last left-clicked (not the one right-clicked).
            if (!_currentNodeData || !_currentNodeData.id) {
                _clickDashBtn('btn-toggle-done-node');
                return;
            }
            var targetIds = _currentTargetIds();
            _setHiddenInput('toggle-done-trigger-input', JSON.stringify(targetIds) + '|' + Date.now());
        }

        function triggerToggleNow() {
            if (!_currentNodeData || !_currentNodeData.id) return;
            var targetIds = _currentTargetIds();
            _setHiddenInput('toggle-now-trigger-input', JSON.stringify(targetIds) + '|' + Date.now());
        }

        function triggerAddToEvent() {
            if (!_currentNodeData || !_currentNodeData.id) return;
            var targetIds = _currentTargetIds();
            _setHiddenInput('dormant-existing-trigger-input', JSON.stringify(targetIds));
        }

        function openInObsidian(path) {
            if (!path) return;
            fetch('/open-obsidian?path=' + encodeURIComponent(path))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.ok) alert('Could not open Obsidian: ' + (data.error || 'unknown'));
                })
                .catch(function (err) { console.error('Open in Obsidian failed:', err); });
        }
        
        // --- Group Delete via Delete key ---
        // Writes to the request input, which a Dash callback picks up to
        // open the native-style confirm modal. The modal's "Delete" button
        // then forwards the names to `group-delete-input` for the real delete.
        function requestGroupDelete(nodeNames) {
            // Timestamp forces a fresh value even when the names repeat
            _setHiddenInput('group-delete-request-input', JSON.stringify(nodeNames));
        }

        // Most-recent main-canvas cy, updated on each re-bind. Document-level
        // handlers (keydown, click, etc.) close over this single variable so
        // they don't need to be re-registered when dash-cytoscape swaps cy.
        var _mainCy = null;
        // The cy instance that raised the currently-displayed context menu.
        // Used by handlers that need to read the active selection on whichever
        // canvas the user right-clicked (main canvas or any mini-graph), so
        // bulk-mode actions work on the Details and Events tabs too.
        var _menuCy = null;

        // Adds Ctrl/Cmd+click additive multi-select to a Cytoscape instance.
        // Default tap behavior (selectionType='single') unselects others when
        // tapping a node. We capture the prior selection in `tapstart` if a
        // modifier is held, then restore those nodes in `tap` after Cytoscape
        // has done its single-select. Toggling: if the clicked node was already
        // selected, we deselect it on the second click.
        function enableCtrlClickMultiSelect(cy) {
            var prevSelection = null;
            var clickedId = null;
            var wasSelected = false;
            cy.on('tapstart', 'node', function (evt) {
                var oe = evt.originalEvent;
                if (oe && (oe.ctrlKey || oe.metaKey)) {
                    prevSelection = cy.$('node:selected').map(function (n) { return n.id(); });
                    clickedId = evt.target.id();
                    wasSelected = evt.target.selected();
                } else {
                    prevSelection = null;
                }
            });
            cy.on('tap', 'node', function (evt) {
                if (prevSelection === null) return;
                var prev = prevSelection;
                var cid = clickedId;
                var wasSel = wasSelected;
                prevSelection = null;
                // Re-select the previously-selected nodes that Cytoscape's
                // default single-select just cleared.
                prev.forEach(function (id) {
                    if (id !== cid) cy.getElementById(id).select();
                });
                // Toggle: if the clicked node was already selected pre-tap, deselect it.
                if (wasSel) evt.target.unselect();
            });
        }

        function bindCyEvents(cy) {
            _mainCy = cy;

            enableCtrlClickMultiSelect(cy);

            // --- Right-click context menu on nodes ---
            cy.on('cxttap', 'node', function (evt) {
                evt.originalEvent.preventDefault();

                // Hide tooltip AND reset its internal flags — otherwise a
                // queued show-timer or MutationObserver can re-surface the
                // tooltip behind the menu.
                if (window.SkillTree && window.SkillTree.tooltip) {
                    window.SkillTree.tooltip.hide();
                }

                // Don't clear multi-selection if right-clicking a selected node
                if (!evt.target.selected()) {
                    cy.$('node:selected').unselect();
                    evt.target.select();
                }

                var nodeData = evt.target.data();
                var pos = evt.originalEvent;
                _menuSource = 'main';
                _menuCy = cy;
                showMenu(pos.clientX, pos.clientY, nodeData);
            });

            // Click on background hides context menu and clears selection
            cy.on('tap', function (evt) {
                if (evt.target === cy) {
                    hideMenu();
                    _setHiddenInput('background-click-input', 'click');
                }
            });
        }

        // Document-level listeners below are attached ONCE. They reference
        // _mainCy so they always see the current cy instance without re-
        // registration on every rebind (previous versions registered a new
        // keydown handler per bindCyEvents call, which stacked up silently).

        // --- Delete key for group delete ---
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Delete' && e.key !== 'Backspace') return;
            if (!_mainCy) return;
            var activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
            if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') {
                return;
            }
            var selected = _mainCy.$('node:selected');
            if (selected.length === 0) return;
            e.preventDefault();
            var names = [];
            selected.forEach(function (node) { names.push(node.id()); });
            if (names.length === 0) return;
            requestGroupDelete(names);
        });

        // --- Ctrl+S to save (settings tab or node editor) ---
        document.addEventListener('keydown', function (e) {
            if (!((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === 's')) return;
            e.preventDefault();
            var settingsModal = document.getElementById('settings-modal');
            var settingsOpen = settingsModal && (
                settingsModal.classList.contains('show') ||
                settingsModal.getAttribute('aria-modal') === 'true' ||
                settingsModal.style.display === 'block'
            );
            if (settingsOpen) {
                _clickDashBtn('btn-settings-save');
            } else {
                _clickDashBtn('btn-save');
            }
        });

        // Prevent browser context menu on the main cytoscape container (once).
        if (cyWrapper) {
            cyWrapper.addEventListener('contextmenu', function (e) { e.preventDefault(); });
        }

        // --- Right-click on a node shown as a row or card ---
        // Next suggestions, Now cards and Goals sidebar cards carry
        // node_menu_attributes (callback_helpers.py). Document-level
        // delegation survives Dash re-renders of the lists.
        document.addEventListener('contextmenu', function (evt) {
            var rowEl = evt.target.closest && evt.target.closest('[data-node-menu]');
            if (!rowEl) return;
            evt.preventDefault();
            if (window.SkillTree && window.SkillTree.tooltip) {
                window.SkillTree.tooltip.hide();
            }
            var nodeData = {
                id: rowEl.getAttribute('data-node-menu'),
                type: rowEl.getAttribute('data-type') || null,
                obsidian_path: rowEl.getAttribute('data-obsidian-path') || null,
                google_drive_path: rowEl.getAttribute('data-google-drive-path') || null,
                website: rowEl.getAttribute('data-website') || null,
                status: rowEl.getAttribute('data-status') || null,
                now: Number(rowEl.getAttribute('data-now') || 0),
            };
            _menuSource = 'list';
            _menuCy = null;
            showMenu(evt.clientX, evt.clientY, nodeData);
        });

        menus.onItem('ctx-menu-edit', triggerEdit);

        menus.onItem('ctx-menu-details', function () {
            if (_currentNodeData && _currentNodeData.id) {
                _setHiddenInput('details-navigate-trigger-input', _currentNodeData.id);
            }
        });

        menus.onItem('ctx-menu-explain', function () {
            if (_currentNodeData && _currentNodeData.id) {
                _setHiddenInput('details-explain-trigger-input', _currentNodeData.id);
            }
        });

        menus.onItem('ctx-menu-toggle-now', triggerToggleNow);

        ['1', '2', '3', 'clear'].forEach(function (rank) {
            menus.onItem('ctx-menu-priority-' + rank, function () {
                if (_currentNodeData && _currentNodeData.id) {
                    _setHiddenInput('goal-priority-trigger-input', _currentNodeData.id + '|' + rank);
                }
            });
        });

        menus.onItem('ctx-menu-toggle-done', triggerToggleDone);

        menus.onItem('ctx-menu-add-to-event', triggerAddToEvent);

        menus.onItem('ctx-menu-website', function () {
            var link = _currentNodeData && _getFirstLink(_currentNodeData.website);
            if (link) window.open(link, '_blank');
        });

        menus.onItem('ctx-menu-obsidian', function () {
            if (_currentNodeData) openInObsidian(_getFirstLink(_currentNodeData.obsidian_path));
        });

        menus.onItem('ctx-menu-drive', function () {
            var link = _currentNodeData && _getFirstLink(_currentNodeData.google_drive_path);
            if (link) window.open(link, '_blank');
        });

        menus.onItem('ctx-menu-delete', function () {
            if (_currentNodeData && _currentNodeData.id) {
                requestGroupDelete(_currentTargetIds());
            }
        });

        function bindMiniGraphMenu(selector, sourceName, selectOnRightClick) {
            // Attach contextmenu-prevent on the wrapper once — wrapper DOM
            // persists across cy replacement.
            var wrapper = document.querySelector(selector);
            if (!wrapper) {
                setTimeout(function () { bindMiniGraphMenu(selector, sourceName, selectOnRightClick); }, 300);
                return;
            }
            wrapper.addEventListener('contextmenu', function (e) { e.preventDefault(); });

            function bind(cy) {
                enableCtrlClickMultiSelect(cy);

                cy.on('cxttap', 'node', function (evt) {
                    evt.originalEvent.preventDefault();
                    if (window.SkillTree && window.SkillTree.tooltip) {
                        window.SkillTree.tooltip.hide();
                    }
                    if (selectOnRightClick && !evt.target.selected()) {
                        cy.$('node:selected').unselect();
                        evt.target.select();
                    }
                    var nodeData = evt.target.data();
                    var pos = evt.originalEvent;
                    _menuSource = sourceName;
                    _menuCy = cy;
                    showMenu(pos.clientX, pos.clientY, nodeData);
                });
                cy.on('tap', function (evt) {
                    if (evt.target === cy) hideMenu();
                });
            }

            if (window.SkillTree && window.SkillTree.onCytoReady) {
                window.SkillTree.onCytoReady(selector, bind);
            } else {
                setTimeout(function () { bindMiniGraphMenu(selector, sourceName, selectOnRightClick); }, 100);
            }
        }

        // Main canvas binds via the same lifecycle hook so its handlers
        // follow cy replacement. The other canvases share bindMiniGraphMenu.
        if (window.SkillTree && window.SkillTree.onCytoReady) {
            window.SkillTree.onCytoReady('#' + MAIN_CANVAS.cytoscapeId, bindCyEvents);
        } else {
            // Rare: helper not yet loaded. Retry the whole init — cyto_lifecycle
            // is typically loaded alongside us, so this falls through quickly.
            setTimeout(initContextMenu, 100);
            return;
        }
        window.SkillTree.canvases.forEach(function (canvas) {
            if (canvas === MAIN_CANVAS) return;
            bindMiniGraphMenu('#' + canvas.cytoscapeId, canvas.key,
                              SELECT_ON_RIGHT_CLICK[canvas.key] === true);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initContextMenu);
    } else {
        initContextMenu();
    }
})();
