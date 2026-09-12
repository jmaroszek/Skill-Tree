/**
 * Node context menu, double-click-to-edit, and group delete for the Skill Tree canvas.
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

        var editItem = document.getElementById('ctx-menu-edit');
        var detailsItem = document.getElementById('ctx-menu-details');
        var explainItem = document.getElementById('ctx-menu-explain');
        var websiteItem = document.getElementById('ctx-menu-website');
        var obsidianItem = document.getElementById('ctx-menu-obsidian');
        var driveItem = document.getElementById('ctx-menu-drive');
        var linksDivider = document.getElementById('ctx-menu-links-divider');
        var toggleNowItem = document.getElementById('ctx-menu-toggle-now');
        var toggleDoneItem = document.getElementById('ctx-menu-toggle-done');
        var addToEventItem = document.getElementById('ctx-menu-add-to-event');
        var deleteItem = document.getElementById('ctx-menu-delete');

        if (!cyWrapper || !menu || !websiteItem || !obsidianItem || !deleteItem || !detailsItem) {
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

        function hideMenu() {
            menu.style.display = 'none';
        }

        function _currentTargetNodes() {
            if (!_currentNodeData || !_currentNodeData.id) return [];
            var sourceCy = _menuCy || _mainCy;
            if (!sourceCy) return [_currentNodeData];

            var selected = sourceCy.$('node:selected');
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
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
            menu.style.display = 'block';
            
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

        function _setHiddenInput(inputId, value) {
            var input = document.getElementById(inputId);
            if (input) {
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeInputValueSetter.call(input, value + '|' + Date.now());
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }

        function triggerEdit() {
            hideMenu();
            if (_menuSource === 'events' && _currentNodeData && _currentNodeData.dormant && _currentNodeData.id) {
                // Events tab dormant node: route to the dormant-specific modal
                // instead of the generic sidebar editor (which refuses dormant nodes).
                _setHiddenInput('dormant-edit-trigger-input', _currentNodeData.id);
            } else if ((_menuSource === 'details' || _menuSource === 'events' || _menuSource === 'next') && _currentNodeData && _currentNodeData.id) {
                // On the details, events, or next tab: open the editor in place without switching tabs.
                // edit-trigger-input would force a switch to tab-canvas (see handle_edit_trigger).
                _setHiddenInput('details-edit-trigger-input', _currentNodeData.id);
            } else if (_currentNodeData && _currentNodeData.id) {
                // Main canvas or goals tab: use edit-trigger-input which carries the
                // node ID explicitly, avoiding reliance on tapNodeData.
                _setHiddenInput('edit-trigger-input', _currentNodeData.id);
            } else {
                _clickDashBtn('btn-edit-node');
            }
        }

        function triggerToggleDone() {
            hideMenu();
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
            hideMenu();
            if (!_currentNodeData || !_currentNodeData.id) return;
            var targetIds = _currentTargetIds();
            _setHiddenInput('toggle-now-trigger-input', JSON.stringify(targetIds) + '|' + Date.now());
        }

        function triggerAddToEvent() {
            hideMenu();
            if (!_currentNodeData || !_currentNodeData.id) return;
            var targetIds = _currentTargetIds();
            _setHiddenInput('dormant-existing-trigger-input', JSON.stringify(targetIds));
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
        // Writes to the request input, which a Dash callback picks up to
        // open the native-style confirm modal. The modal's "Delete" button
        // then forwards the names to `group-delete-input` for the real delete.
        function requestGroupDelete(nodeNames) {
            var input = document.getElementById('group-delete-request-input');
            if (input) {
                // Use React's native value setter to ensure Dash picks up the change
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                // Timestamp forces a fresh value even when the names repeat
                nativeInputValueSetter.call(input, JSON.stringify(nodeNames) + '|' + Date.now());
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
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

        // --- Right-click context menu on Next-tab suggestion rows and Now cards ---
        // Document-level delegation survives Dash re-renders of the table.
        document.addEventListener('contextmenu', function (evt) {
            var rowEl = evt.target.closest && (evt.target.closest('.suggestion-bar-row') || evt.target.closest('.now-card'));
            if (!rowEl) return;
            var nodeName = null;
            try {
                var parsed = JSON.parse(rowEl.id);
                nodeName = parsed && parsed.index;
            } catch (e) {
                return;
            }
            if (!nodeName) return;
            evt.preventDefault();
            if (window.SkillTree && window.SkillTree.tooltip) {
                window.SkillTree.tooltip.hide();
            }
            var nodeData = {
                id: nodeName,
                obsidian_path: rowEl.getAttribute('data-obsidian-path') || null,
                google_drive_path: rowEl.getAttribute('data-google-drive-path') || null,
                website: rowEl.getAttribute('data-website') || null,
                status: rowEl.getAttribute('data-status') || null,
                now: Number(rowEl.getAttribute('data-now') || 0),
            };
            _menuSource = 'next';
            // Suggestion-bar rows aren't tied to a cy — clear so bulk-aware
            // handlers (Add to event, etc.) don't read a stale main-canvas
            // selection and incorrectly act on multiple nodes.
            _menuCy = null;
            showMenu(evt.clientX, evt.clientY, nodeData);
        });

        document.addEventListener('click', function (e) {
            if (!menu.contains(e.target)) hideMenu();
        });
        document.addEventListener('scroll', hideMenu);
        window.addEventListener('resize', hideMenu);

        if (editItem) editItem.addEventListener('click', triggerEdit);

        if (detailsItem) {
            detailsItem.addEventListener('click', function () {
                hideMenu();
                if (_currentNodeData && _currentNodeData.id) {
                    _setHiddenInput('details-navigate-trigger-input', _currentNodeData.id);
                }
            });
        }

        if (explainItem) {
            explainItem.addEventListener('click', function () {
                hideMenu();
                if (_currentNodeData && _currentNodeData.id) {
                    _setHiddenInput('details-explain-trigger-input', _currentNodeData.id);
                }
            });
        }

        if (toggleNowItem) toggleNowItem.addEventListener('click', triggerToggleNow);

        if (toggleDoneItem) toggleDoneItem.addEventListener('click', triggerToggleDone);

        if (addToEventItem) addToEventItem.addEventListener('click', triggerAddToEvent);

        if (websiteItem) {
            websiteItem.addEventListener('click', function () {
                hideMenu();
                if (_currentNodeData) {
                    var link = _getFirstLink(_currentNodeData.website);
                    if (link) window.open(link, '_blank');
                }
            });
        }

        if (obsidianItem) {
            obsidianItem.addEventListener('click', function () {
                if (_currentNodeData) openInObsidian(_getFirstLink(_currentNodeData.obsidian_path));
            });
        }

        if (driveItem) {
            driveItem.addEventListener('click', function () {
                hideMenu();
                if (_currentNodeData) {
                    var link = _getFirstLink(_currentNodeData.google_drive_path);
                    if (link) window.open(link, '_blank');
                }
            });
        }

        if (deleteItem) {
            deleteItem.addEventListener('click', function () {
                hideMenu();
                if (_currentNodeData && _currentNodeData.id) {
                    requestGroupDelete(_currentTargetIds());
                }
            });
        }

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
