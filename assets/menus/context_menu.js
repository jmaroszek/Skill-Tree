/**
 * Node context menu, multi-select, and group delete for the Skill Tree canvases.
 *
 * One menu serves every place a node appears: the canvases, and the rows and
 * cards that carry node_menu_attributes (ui/components/menus.py) — Next
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
        // The icon says where the first link will open: a globe for the
        // browser and a plain arrow for a file. This mirrors
        // resource_links.resolve_target closely enough for an icon; the
        // server still decides on click.
        function _resourceIcon(link) {
            link = (link || '').trim();
            if (/^(https?:\/\/|www\.)/i.test(link)) return 'globe';
            var isPath = /^[a-z]:[\\/]|^[\\/]/i.test(link) || link.indexOf('\\') >= 0;
            if (!isPath && /^[a-z0-9-]+(\.[a-z0-9-]+)+(\/.*)?$/i.test(link) &&
                    !/\.(pdf|docx?|xlsx?|pptx?|txt|md|csv|png|jpe?g|gif|zip)$/i.test(link)) {
                return 'globe';
            }
            return 'box-arrow-up-right';
        }

        // One slot per possible Resource section (layout.py), in order.
        var resourceItems = Array.from(
            document.querySelectorAll('[id^="ctx-menu-resource-"]'));
        var linksDivider = document.getElementById('ctx-menu-links-divider');
        var toggleNowItem = document.getElementById('ctx-menu-toggle-now');
        var priorityItem = document.getElementById('ctx-menu-priority');
        var priorityDivider = document.getElementById('ctx-menu-priority-divider');
        var toggleDoneItem = document.getElementById('ctx-menu-toggle-done');
        var addToEventItem = document.getElementById('ctx-menu-add-to-event');
        var deleteItem = document.getElementById('ctx-menu-delete');
        var pairItems = ['ctx-menu-pair-divider', 'ctx-menu-link-soft',
            'ctx-menu-link-hard', 'ctx-menu-bridge'].map(function (id) {
            return document.getElementById(id);
        });
        var edgeMenu = document.getElementById('edge-context-menu');
        // Keep the leading Bootstrap icons in place when a contextual action
        // changes its label (including multi-select forms).
        var toggleNowLabel = toggleNowItem && toggleNowItem.querySelector('.ctx-menu-label');
        var toggleDoneLabel = toggleDoneItem && toggleDoneItem.querySelector('.ctx-menu-label');
        var addToEventLabel = addToEventItem && addToEventItem.querySelector('.ctx-menu-label');
        var deleteLabel = deleteItem && deleteItem.querySelector('.ctx-menu-label');

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

        // The order a canvas's nodes were picked in, newest last. Cytoscape
        // keeps no such order, and a bridge starts at the node picked first.
        var ORDER_KEY = 'skillTreeSelectionOrder';

        function _pickedInOrder(cy) {
            var selected = [];
            cy.$('node:selected').forEach(function (node) { selected.push(node.id()); });
            var order = cy.scratch(ORDER_KEY) || [];
            // Nodes picked some other way, such as a box selection, came first.
            var known = order.filter(function (id) { return selected.indexOf(id) >= 0; });
            var unknown = selected.filter(function (id) { return known.indexOf(id) < 0; });
            return unknown.concat(known);
        }

        function showMenu(x, y, nodeData) {
            _currentNodeData = nodeData;

            var targets = _currentTargetNodes();
            var targetCount = targets.length || 1;
            // Done and sleeping nodes can't join Now (graph_manager's
            // _normalize_activity), so they sit out of the Now action, and
            // a sleeping node can't be marked Done. Rows and cards carry no
            // dormant flag; sleeping nodes never appear there.
            var asleep = function (node) { return Number(node.dormant) > 0; };
            var nowTargets = targets.filter(function (node) {
                return Number(node.now) > 0 || (node.status !== 'Done' && !asleep(node));
            });
            var nowCount = nowTargets.length;
            var allNow = nowCount > 0 && nowTargets.every(function (node) {
                return Number(node.now) > 0;
            });
            var doneTargets = targets.filter(function (node) { return !asleep(node); });
            var doneCount = doneTargets.length;
            var allDone = doneCount > 0 && doneTargets.every(function (node) {
                return node.status === 'Done';
            });
            toggleNowItem.style.display = nowCount > 0 ? '' : 'none';
            toggleDoneItem.style.display = targets.length > 0 && doneCount === 0 ? 'none' : '';
            toggleNowLabel.textContent = nowCount > 1
                ? (allNow ? 'Remove ' + nowCount + ' from Now' : 'Add ' + nowCount + ' to Now')
                : (allNow ? 'Remove from Now' : 'Add to Now');
            toggleDoneItem.querySelector('.ctx-menu-icon').className =
                'bi bi-' + (allDone ? 'arrow-counterclockwise' : 'check-circle') + ' ctx-menu-icon';
            toggleDoneLabel.textContent = doneCount > 1
                ? (allDone ? 'Reopen ' + doneCount : 'Mark ' + doneCount + ' Done')
                : (allDone ? 'Reopen' : 'Mark Done');
            toggleNowItem.querySelector('.ctx-menu-icon').className =
                'bi bi-' + (allNow ? 'pause-circle' : 'play-circle') + ' ctx-menu-icon';
            addToEventLabel.textContent = targetCount > 1
                ? 'Add ' + targetCount + ' to Event…'
                : 'Add to Event…';
            deleteLabel.textContent = targetCount > 1
                ? 'Delete ' + targetCount + '…'
                : 'Delete…';
            // A priority is one unfinished Goal's rank, so it has no bulk
            // form, and a Done Goal has none to set. The section goes with
            // its divider, leaving every other node's menu exactly as it is.
            // A link or a bridge goes between exactly two nodes, so they are
            // offered only when the menu acts on two. A row or card is always
            // one node.
            var showPair = !!_menuCy && targets.length === 2;
            pairItems.forEach(function (el) {
                if (el) el.style.display = showPair ? '' : 'none';
            });
            var showPriority = targetCount === 1 && nodeData.type === 'Goal'
                && nodeData.status !== 'Done';
            priorityItem.style.display = showPriority ? '' : 'none';
            if (priorityDivider) priorityDivider.style.display = showPriority ? '' : 'none';

            var resourceLinks = nodeData.resource_links || {};
            if (typeof resourceLinks === 'string') {
                try { resourceLinks = JSON.parse(resourceLinks); } catch (_) { resourceLinks = {}; }
            }
            // The node editor always renders every section, in order, with
            // its current name, so it is where the slots learn theirs.
            var sections = Array.from(
                document.querySelectorAll('#editor-resources [data-resource-id]'));
            var hasResources = false;
            resourceItems.forEach(function (item, i) {
                var section = sections[i];
                var id = section && section.dataset.resourceId;
                var visible = !!(id && resourceLinks[id] && resourceLinks[id].length);
                item.style.display = visible ? '' : 'none';
                if (!visible) return;
                hasResources = true;
                item.dataset.resourceId = id;
                var label = section.querySelector('label');
                item.querySelector('.ctx-menu-label').textContent =
                    'Open ' + (label ? label.textContent : 'Resource');
                item.querySelector('.ctx-menu-icon').className = 'bi bi-' +
                    _resourceIcon(resourceLinks[id][0]) +
                    ' ctx-menu-icon';
            });

            // Collapse the upper divider when neither link is present, so the
            // remaining (lower) Hr doesn't sit doubled-up against this one.
            if (linksDivider) {
                linksDivider.style.display = hasResources ? '' : 'none';
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
            if (_menuSource !== 'main' && _currentNodeData && _currentNodeData.id) {
                // Anywhere but the Nodes canvas: open the editor in place without switching tabs.
                // Dormant nodes included -- the one editor handles them.
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
            // Sleeping nodes sit out, as the label counted them.
            var targetIds = _currentTargetNodes().filter(function (node) {
                return !(Number(node.dormant) > 0);
            }).map(function (node) { return node.id; });
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

        // Records the order nodes are picked in. Cytoscape does the picking
        // itself: a click selects one node, and a click with Ctrl, Cmd or
        // Shift held adds or removes one, after the `tap` handlers have run.
        // Toggling here as well undid its toggle, so a held click could never
        // drop a node.
        //
        // A node the app selected, such as the one a save or a search just
        // showed, was never picked. A held click adds it rather than
        // dropping it, so it can start a multi-selection.
        function trackSelectionOrder(cy) {
            var additive = false;
            var wasSelected = false;
            var keep = false;
            var pointer = false;
            var appSelected = new Set();
            cy.on('tapstart', function () { pointer = true; });
            cy.on('tapend', function () {
                setTimeout(function () { pointer = false; }, 0);
            });
            cy.on('select', 'node', function (evt) {
                if (!pointer) appSelected.add(evt.target.id());
            });
            cy.on('unselect', 'node', function (evt) {
                if (!keep) appSelected.delete(evt.target.id());
            });
            cy.on('tapstart', 'node', function (evt) {
                var oe = evt.originalEvent;
                additive = !!(oe && (oe.ctrlKey || oe.metaKey || oe.shiftKey));
                wasSelected = evt.target.selected();
                keep = additive && wasSelected && appSelected.has(evt.target.id());
                if (keep) wasSelected = false;
                // A canvas that moves on a click (Details) leaves a held one
                // alone, so it only changes the selection.
                window.SkillTree.additiveTap = additive;
            });
            cy.on('tap', 'node', function (evt) {
                var id = evt.target.id();
                if (!evt.originalEvent) {
                    // Enter on a focused node (keyboard_navigation.js) selects
                    // it before tapping and never takes one away.
                    additive = !!window.SkillTree.additiveTap;
                    wasSelected = false;
                    keep = false;
                }
                // A tapped node is the user's pick, however it got selected.
                if (!keep) appSelected.delete(id);
                if (!additive) {
                    cy.scratch(ORDER_KEY, [id]);
                    return;
                }
                var order = (cy.scratch(ORDER_KEY) || []).filter(function (other) { return other !== id; });
                if (!wasSelected) order.push(id);
                cy.scratch(ORDER_KEY, order);
                if (keep) {
                    // Cytoscape toggles the node off after this handler.
                    var picked = evt.target;
                    setTimeout(function () {
                        keep = false;
                        picked.select();
                        appSelected.delete(id);
                    }, 0);
                }
            });
        }

        function bindCyEvents(cy) {
            _mainCy = cy;

            trackSelectionOrder(cy);

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

            cy.on('cxttap', 'edge', showEdgeMenu);

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
            // A selection can outlive its tab. Delete belongs only to the
            // focused Nodes canvas, never a form, modal or another tab.
            if (document.activeElement !== document.getElementById(MAIN_CANVAS.cytoscapeId) ||
                    document.querySelector('.modal.show')) return;
            var selected = _mainCy.$('node:selected');
            if (selected.length === 0) return;
            e.preventDefault();
            var names = [];
            selected.forEach(function (node) { names.push(node.id()); });
            if (names.length === 0) return;
            requestGroupDelete(names);
        });

        // Prevent browser context menu on the main cytoscape container (once).
        if (cyWrapper) {
            cyWrapper.addEventListener('contextmenu', function (e) { e.preventDefault(); });
        }

        // --- Right-click on a node shown as a row or card ---
        // Next suggestions, Now cards and Goals sidebar cards carry
        // node_menu_attributes (ui/components/menus.py). Document-level
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
                resource_links: rowEl.getAttribute('data-resource-links') || '{}',
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

        // A link that starts another app, or reaches another computer, comes
        // back with a question (resource_links.NeedsConfirmation). A yes sends
        // the same request again, confirmed.
        function openResource(request) {
            fetch('/open-resource', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(request),
            }).then(function (response) { return response.json(); })
              .then(function (data) {
                  if (data.confirm) {
                      if (window.confirm(data.confirm)) {
                          openResource(Object.assign({}, request, { confirmed: true }));
                      }
                  } else if (!data.ok) {
                      alert('Could not open Resource: ' + (data.error || 'unknown'));
                  }
              }).catch(function (err) { console.error('Open Resource failed:', err); });
        }

        resourceItems.forEach(function (item) {
            menus.onItem(item.id, function () {
                if (!_currentNodeData || !item || !item.dataset.resourceId) return;
                openResource({ node: _currentNodeData.id,
                    section: item.dataset.resourceId, index: 0 });
            });
        });

        menus.onItem('ctx-menu-delete', function () {
            if (_currentNodeData && _currentNodeData.id) {
                requestGroupDelete(_currentTargetIds());
            }
        });

        // --- Bridge ---
        // Two nodes selected: Start is the one picked first. The dialog
        // reorders them if a link already runs between the two.
        menus.onItem('ctx-menu-bridge', function () {
            if (!_menuCy) return;
            var ids = _pickedInOrder(_menuCy);
            if (ids.length !== 2) return;
            _setHiddenInput('bridge-open-input', JSON.stringify(ids));
        });

        // --- Link two nodes ---
        // The node picked first leads to the other, as a bridge's Start does.
        // The server keeps a link already between them in its own order.
        function sendPairLink(edgeType) {
            if (!_menuCy) return;
            var ids = _pickedInOrder(_menuCy);
            if (ids.length !== 2) return;
            _setHiddenInput('link-action-input', JSON.stringify(['pair'].concat(ids, [edgeType])));
        }
        menus.onItem('ctx-menu-link-soft', function () { sendPairLink('Needs_Soft'); });
        menus.onItem('ctx-menu-link-hard', function () { sendPairLink('Needs_Hard'); });

        // --- Link menu ---
        // A link offers to take a node in the middle of it, to change its
        // type or direction, or to go. A Synergy has neither a strength nor a
        // direction, so it offers only the first and the last. Insert keeps
        // a Synergy where it is; the new node joins both ends.
        var _currentEdgeData = null;
        var edgeTypeItem = document.getElementById('ctx-menu-edge-type');
        var edgeTypeLabel = edgeTypeItem && edgeTypeItem.querySelector('.ctx-menu-label');
        var edgeTypeIcon = edgeTypeItem && edgeTypeItem.querySelector('.ctx-menu-icon');
        var edgeReverseItem = document.getElementById('ctx-menu-edge-reverse');
        var edgeChangeDivider = document.getElementById('ctx-menu-edge-change-divider');

        function showEdgeMenu(evt) {
            var data = evt.target.data();
            if (!edgeMenu) return;
            evt.originalEvent.preventDefault();
            if (window.SkillTree && window.SkillTree.tooltip) {
                window.SkillTree.tooltip.hide();
            }
            _currentEdgeData = data;
            var directional = data.type === 'Needs_Hard' || data.type === 'Needs_Soft';
            [edgeTypeItem, edgeReverseItem, edgeChangeDivider].forEach(function (el) {
                if (el) el.style.display = directional ? '' : 'none';
            });
            // A step down to Soft or up to Hard: what changes is the link's
            // strength, which is true whatever else feeds the node.
            var toSoft = data.type === 'Needs_Hard';
            if (edgeTypeLabel) edgeTypeLabel.textContent = toSoft ? 'Make Soft' : 'Make Hard';
            if (edgeTypeIcon) {
                edgeTypeIcon.className = 'bi bi-' + (toSoft ? 'arrow-down-circle' : 'arrow-up-circle') +
                    ' ctx-menu-icon';
            }
            menus.open(edgeMenu, evt.originalEvent.clientX, evt.originalEvent.clientY);
        }

        function sendLinkAction(action) {
            if (!_currentEdgeData) return;
            _setHiddenInput('link-action-input', JSON.stringify([action,
                _currentEdgeData.source, _currentEdgeData.target, _currentEdgeData.type]));
        }

        menus.onItem('ctx-menu-edge-bridge', function () {
            if (!_currentEdgeData) return;
            _setHiddenInput('bridge-open-input', JSON.stringify(
                [_currentEdgeData.source, _currentEdgeData.target, _currentEdgeData.type]));
        });
        menus.onItem('ctx-menu-edge-type', function () {
            if (!_currentEdgeData) return;
            sendLinkAction(_currentEdgeData.type === 'Needs_Hard' ? 'soft' : 'hard');
        });
        menus.onItem('ctx-menu-edge-reverse', function () { sendLinkAction('reverse'); });
        menus.onItem('ctx-menu-edge-remove', function () { sendLinkAction('remove'); });

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
                trackSelectionOrder(cy);

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
                cy.on('cxttap', 'edge', showEdgeMenu);
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
