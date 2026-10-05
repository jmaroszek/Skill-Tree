/** Keyboard counterparts for custom cards, graph canvases and sortable lists.
 * Native form controls keep their own keys. Hidden sliding panels are inert;
 * opening/closing them preserves a useful place in the keyboard focus order.
 */
(function () {
    'use strict';
    var ST = window.SkillTree;
    var F = ST.keyboardFocus;
    var pendingFocus = null;
    var lastFocused = null;
    var pendingDestination = null;
    var pendingTabEntry = null;
    var custom = '.suggestion-bar-row, .now-card, .goal-card, .event-card, .goal-rank-trigger, .details-subtask-name-link, [id*="details-milestone-tile"]';
    var reorderHandles = '.goal-drag-handle, .event-drag-handle, .ctx-drag-handle:not(.ctx-drag-disabled), .ctx-chip-grip';
    var listItems = '.suggestion-bar-row, .now-card, .goal-card, .event-card';
    // Lists you browse with the arrow keys from a search box above them.
    var searchLists = {'details-goal-search': 'details-goal-sidebar', 'events-search-input': 'events-sidebar-container'};
    // Enter on a main tab lands on that tab's first useful control.
    var tabEntry = {Home: '.now-card, .suggestion-bar-row', Nodes: '#cytoscape-graph',
        Details: '#details-node-select', Events: '#events-search-input',
        Analyze: '.analyze-subtabs .nav-link.active'};
    var lastNowCard = null;
    var graphHelp = 'Arrows: move toward a node. Page Up/Down: browse by name. Home/End: first/last. Enter: select. Shift+Enter: add. Escape: clear selection. Alt+Enter: actions. +/−: zoom. 0: fit.';
    var feedback;

    function announce(message) {
        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'keyboard-feedback';
            feedback.setAttribute('role', 'status');
            feedback.setAttribute('aria-live', 'polite');
            document.body.appendChild(feedback);
        }
        feedback.textContent = message;
    }

    function sync() {
        document.querySelectorAll('.nav-tabs').forEach(function (bar) {
            var tabs = Array.from(bar.querySelectorAll('.nav-link:not(.disabled)'));
            var active = tabs.includes(document.activeElement) ? document.activeElement
                : tabs.find(function (t) { return t.classList.contains('active'); }) || tabs[0];
            bar.setAttribute('role', 'tablist');
            bar.querySelectorAll('.nav-link').forEach(function (t) {
                t.tabIndex = t === active ? 0 : -1;
                t.setAttribute('role', 'tab');
                t.setAttribute('aria-selected', String(t.classList.contains('active')));
            });
        });
        document.querySelectorAll(reorderHandles).forEach(function (handle) {
            if (handle.tabIndex === 0) return;
            handle.tabIndex = 0;
            handle.setAttribute('role', 'button');
            handle.setAttribute('aria-label', 'Reorder with Alt + arrow keys');
            handle.title = 'Alt + arrow keys to reorder';
        });
        var groups = new Set();
        document.querySelectorAll(listItems).forEach(function (row) { groups.add(row.parentElement); });
        groups.forEach(function (group) {
            var rows = listRows(group);
            var active = rows.find(function (r) { return r.contains(document.activeElement); }) ||
                rows.find(function (r) { return rowName(r) === group._keyboardRow; }) || rows[0];
            if (active) group._keyboardRow = rowName(active);
            rows.forEach(function (row) {
                // The few Now cards are each a Tab stop. Longer lists keep one
                // stop, so Tab leaves them in a single keypress.
                row.tabIndex = row === active || row.matches('.now-card') ? 0 : -1;
                row.setAttribute('aria-describedby', 'keyboard-list-help');
                row.querySelectorAll(reorderHandles + ', .goal-rank-trigger').forEach(function (item) {
                    item.tabIndex = row === active ? 0 : -1;
                });
            });
        });
        // Changing how many suggestions show is rare. Leave the stepper to the
        // mouse so Tab goes from the Now cards straight to the Next list.
        document.querySelectorAll('#btn-sugg-minus, #btn-sugg-plus').forEach(function (b) { b.tabIndex = -1; });
        associateHints();
        if (ST.describeSplitHandle) document.querySelectorAll('.split-handle').forEach(function (handle) {
            if (!handle.hasAttribute('aria-valuenow')) ST.describeSplitHandle(handle);
        });
        if (pendingFocus) {
            var candidates = document.querySelectorAll(pendingFocus.selector);
            var row = Array.from(candidates).find(function (el) {
                return el.getAttribute(pendingFocus.attribute) === pendingFocus.name;
            });
            if (row && (row !== pendingFocus.original || document.activeElement === document.body)) {
                var target = pendingFocus.handle ? row.querySelector(pendingFocus.handle) : row;
                // React may move the existing keyed card instead of replacing
                // it. That move also blurs its handle, so recover both cases.
                if (target && F.focus(target)) pendingFocus = null;
            } else if (Date.now() > pendingFocus.deadline) pendingFocus = null;
        }
        if (F.isKeyboard() && lastFocused && !lastFocused.isConnected && document.activeElement === document.body &&
                !document.querySelector('.modal.show')) {
            var replacement = lastFocused.id && document.getElementById(lastFocused.id);
            var name = lastFocused.getAttribute('data-node-menu');
            if (!replacement && name) replacement = Array.from(document.querySelectorAll('[data-node-menu]'))
                .find(function (el) { return el.getAttribute('data-node-menu') === name && el.getClientRects().length; });
            if (replacement) F.focus(replacement);
        }
        if (pendingTabEntry) {
            var entry = Array.from(document.querySelectorAll(pendingTabEntry.selector)).find(F.visible);
            if (entry && !document.querySelector('.modal.show') && F.focus(entry)) pendingTabEntry = null;
            else if (Date.now() > pendingTabEntry.deadline) pendingTabEntry = null;
        }
        if (pendingDestination) {
            var dest = pendingDestination;
            var field = document.querySelector(dest.selector);
            var panel = document.getElementById(dest.panel);
            var ready = F.visible(field) && (!dest.name || (dest.event ? field.value === dest.name
                : document.getElementById('details-node-name')?.textContent === dest.name));
            if (ready && panel && panel.inert && !document.querySelector('.modal.show')) {
                F.focus(field); pendingDestination = null;
            } else if (Date.now() > dest.deadline) pendingDestination = null;
        }
    }

    function rowName(row) {
        return row.getAttribute('data-node-menu') || row.getAttribute('data-event-name');
    }

    function listRows(group) {
        return Array.from(group.children).filter(function (row) { return row.matches(listItems); });
    }

    // Alt+Enter opens a card's or node's actions. The Menu key and Shift+F10
    // are the platform's own context-menu keys, so they keep working.
    function isActionsKey(e) {
        return (e.altKey && e.key === 'Enter' && !e.ctrlKey && !e.metaKey) ||
            e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10');
    }

    // Arrow keys that leave a list for its neighbour: Down from a Now card to
    // the Next list and Up back to that card; Up from the top of a sidebar
    // list to its search box.
    function crossList(row, rows, key) {
        if (row.matches('.now-card')) {
            return key === 'ArrowDown' ? document.querySelector('.suggestion-bar-row[tabindex="0"]') : null;
        }
        if (key !== 'ArrowUp' || rows.indexOf(row) !== 0) return null;
        if (row.matches('.suggestion-bar-row')) {
            var now = Array.from(document.querySelectorAll('.now-card'));
            return now.find(function (card) { return rowName(card) === lastNowCard; }) || now[0] || null;
        }
        var search = Object.keys(searchLists).find(function (id) {
            var panel = document.getElementById(searchLists[id]);
            return panel && panel.contains(row);
        });
        // Only the first list under the search box; later groups keep wrapping.
        var top = search && document.getElementById(searchLists[search]).querySelector(listItems);
        return top && top.parentElement === row.parentElement ? document.getElementById(search) : null;
    }

    function associateHints() {
        // A label's following field/group inherits its description for screen
        // readers, without adding a stop for the heading itself. Sections can
        // cover many fields. The visible tooltip stays hover-only.
        document.querySelectorAll('.keyboard-hint-label').forEach(function (wrapper) {
            var label = wrapper.querySelector('.hover-hint');
            if (!label) return;
            var sibling = wrapper.nextElementSibling;
            while (sibling) {
                var nextLabel = sibling.querySelector('.hover-hint');
                if (nextLabel && (label.tagName === 'LABEL' || nextLabel.tagName === 'H5')) break;
                var fields = sibling.matches('input, select, textarea, button') ? [sibling]
                    : Array.from(sibling.querySelectorAll('input:not([type=hidden]), select, textarea, button'));
                fields.forEach(function (field) {
                    var descriptions = new Set((field.getAttribute('aria-describedby') || '').split(' ').filter(Boolean));
                    descriptions.add(wrapper.getAttribute('data-keyboard-hint'));
                    field.setAttribute('aria-describedby', Array.from(descriptions).join(' '));
                });
                // Plain field labels end at the next field/heading; section
                // headings extend through their contents until another heading.
                if (fields.length && label.tagName === 'LABEL') break;
                if (sibling.querySelector('h5') || sibling.tagName === 'H5' || sibling.tagName === 'LABEL') break;
                sibling = sibling.nextElementSibling;
            }
        });
    }

    // Use the same persistence inputs as pointer dragging, including the
    // Contexts editor's structural remount. Never cross an event-group boundary.
    function reorder(target, direction) {
        var row, selector, attribute, input, handle;
        if (target.matches('.now-card')) {
            row = target; selector = '.now-card'; attribute = 'data-node-name'; input = 'now-drag-order-input';
        } else if (target.matches('.goal-drag-handle')) {
            row = target.closest('.goal-card'); selector = '.goal-card'; attribute = 'data-goal-name';
            input = 'details-goal-drag-order-input'; handle = '.goal-drag-handle';
        } else if (target.matches('.event-drag-handle')) {
            row = target.closest('.event-card'); selector = '.event-card'; attribute = 'data-event-name';
            input = 'event-drag-order-input'; handle = '.event-drag-handle';
        } else if (target.matches('.ctx-drag-handle:not(.ctx-drag-disabled), .ctx-chip-grip')) {
            var chip = target.matches('.ctx-chip-grip');
            row = target.closest(chip ? '.ctx-chip' : '.ctx-row');
            selector = chip ? '.ctx-chip' : '.ctx-row'; attribute = chip ? 'data-ctx-sub' : 'data-ctx-row';
            input = 'ctx-editor-drag-input'; handle = chip ? '.ctx-chip-grip' : '.ctx-drag-handle';
        }
        if (!row || !document.getElementById(input)) return false;
        var siblings = Array.from(row.parentElement.children).filter(function (el) { return el.matches(selector); });
        var other = siblings[siblings.indexOf(row) + direction];
        if (!other) return true;
        row.parentElement.insertBefore(row, direction < 0 ? other : other.nextSibling);
        var root = input === 'event-drag-order-input' ? document.getElementById('events-list-container') : row.parentElement;
        var order = Array.from(root.querySelectorAll(selector)).map(function (el) { return el.getAttribute(attribute); });
        if (input === 'ctx-editor-drag-input') order = _ctxLayoutFromDom(document.getElementById('ctx-editor-rows'));
        pendingFocus = {selector: selector, attribute: attribute, name: row.getAttribute(attribute),
            original: row, handle: handle, deadline: Date.now() + 5000};
        ST.setInputValue(document.getElementById(input), JSON.stringify(order));
        F.focus(target);
        announce('Moved to position ' + (siblings.indexOf(other) + 1));
        return true;
    }

    document.addEventListener('pointerdown', function () { pendingFocus = null; pendingTabEntry = null; }, true);
    // Tooltips open on mouse hover only, never on keyboard focus.
    document.addEventListener('focusin', function (e) {
        lastFocused = e.target;
        if (e.target.matches('.now-card')) lastNowCard = rowName(e.target);
        sync();
        if (F.isKeyboard() && e.target.matches(listItems + ', ' + reorderHandles)) {
            announce(e.target.matches(listItems) ? 'Arrows: browse this list. Enter: open. Alt+Enter: actions.'
                : 'Alt + arrow keys: reorder this item.');
        }
    });
    document.addEventListener('keydown', function (e) {
        if (e.defaultPrevented || e.isComposing) return;
        var target = e.target;
        if (!target.matches) return;
        if (target.matches('.nav-tabs .nav-link')) {
            if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
                e.preventDefault();
                var tabs = Array.from(target.closest('.nav-tabs').querySelectorAll('.nav-link:not(.disabled)'));
                var i = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1
                    : (tabs.indexOf(target) + (e.key === 'ArrowLeft' ? -1 : 1) + tabs.length) % tabs.length;
                tabs.forEach(function (t) { t.tabIndex = -1; });
                tabs[i].tabIndex = 0; F.focus(tabs[i]); return;
            }
            if (target.tagName === 'A' && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault(); target.click();
                var selector = target.closest('#main-tabs') && tabEntry[target.textContent.trim()];
                if (selector) {
                    pendingTabEntry = {selector: selector, deadline: Date.now() + 10000};
                    sync();
                }
                return;
            }
        }
        if (searchLists[target.id] && e.key === 'ArrowDown' && !e.altKey && !e.ctrlKey && !e.metaKey) {
            var first = document.getElementById(searchLists[target.id]).querySelector(listItems.split(', ')
                .map(function (item) { return item + '[tabindex="0"]'; }).join(', '));
            if (first) { e.preventDefault(); F.focus(first); }
            return;
        }
        if (e.altKey && ['ArrowUp', 'ArrowLeft', 'ArrowDown', 'ArrowRight'].includes(e.key)) {
            if (reorder(target, ['ArrowUp', 'ArrowLeft'].includes(e.key) ? -1 : 1)) {
                e.preventDefault(); return;
            }
        }
        var row = target.closest(listItems);
        if (row && !e.altKey && !e.ctrlKey && !e.metaKey &&
                ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
            var rows = listRows(row.parentElement);
            var bridge = crossList(row, rows, e.key);
            if (bridge) { e.preventDefault(); F.focus(bridge); return; }
            var index = e.key === 'Home' ? 0 : e.key === 'End' ? rows.length - 1
                : (rows.indexOf(row) + (['ArrowUp', 'ArrowLeft'].includes(e.key) ? -1 : 1) + rows.length) % rows.length;
            e.preventDefault(); F.focus(rows[index]); return;
        }
        if (isActionsKey(e) && target.matches('[data-node-menu], .event-card')) {
            e.preventDefault();
            var rect = target.getBoundingClientRect();
            target.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true,
                clientX: rect.left + 16, clientY: rect.top + 16}));
            return;
        }
        if ((e.key === 'Enter' || e.key === ' ') && !e.altKey && !e.ctrlKey && !e.metaKey && target.matches(custom)) {
            e.preventDefault(); target.click(); return;
        }
    });

    document.addEventListener('click', function (e) {
        if (e.detail !== 0 || !F.isKeyboard()) return;
        var row = e.target.closest('.goal-card, .event-card');
        if (row && e.target.closest('.goal-drag-handle, .goal-rank-trigger, .event-drag-handle')) return;
        var event = row?.matches('.event-card') || e.target.closest('#btn-new-event');
        if (!row && !event) return;
        var panel = event ? 'events-sidebar-container' : 'details-goal-sidebar';
        pendingDestination = {panel: panel, selector: event ? '#event-name' : '#details-node-select',
            name: row && rowName(row), event: event, deadline: Date.now() + 10000};
        document.getElementById(event ? 'btn-events-sidebar-close' : 'btn-details-goals-close').click();
    });

    ST.canvases.forEach(function (canvas) {
        var cursor = null;
        ST.onCytoReady('#' + canvas.cytoscapeId, function (cy) {
            var el = document.getElementById(canvas.cytoscapeId);
            el.classList.add('keyboard-graph');
            el.tabIndex = 0;
            el.setAttribute('role', 'group');
            el.setAttribute('aria-label', 'Graph. ' + graphHelp);
            // DOM listeners belong to the wrapper once; fetch the current cy
            // at use time so a Dash remount does not retain the old instance.
            if (el._keyboardBound) return;
            el._keyboardBound = true;
            el.addEventListener('focus', function () {
                if (F.isKeyboard()) announce(graphHelp);
            });
            el.addEventListener('keydown', function (e) {
                if (e.target !== el || e.ctrlKey || e.metaKey || (e.altKey && !isActionsKey(e))) return;
                var cy = ST.getCy(el);
                if (!cy) return;
                var nodes = cy.nodes().filter(function (n) { return n.visible(); }).toArray()
                    .sort(function (a, b) { return a.id().localeCompare(b.id()); });
                var node = nodes.find(function (n) { return n.id() === cursor; });
                if (!node) node = nodes.find(function (n) { return n.selected(); }) || nodes[0];
                if (['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End', 'PageUp', 'PageDown'].includes(e.key)) {
                    e.preventDefault();
                    if (!nodes.length) { announce('Graph is empty'); return; }
                    var i = nodes.indexOf(node);
                    if (e.key === 'Home') i = 0;
                    else if (e.key === 'End') i = nodes.length - 1;
                    else if (e.key === 'PageUp' || e.key === 'PageDown') {
                        if (cursor !== null) i = (i + (e.key === 'PageUp' ? -1 : 1) + nodes.length) % nodes.length;
                    } else if (cursor !== null || node.selected()) {
                        var position = node.renderedPosition();
                        var axis = ['ArrowLeft', 'ArrowRight'].includes(e.key) ? 'x' : 'y';
                        var otherAxis = axis === 'x' ? 'y' : 'x';
                        var direction = ['ArrowLeft', 'ArrowUp'].includes(e.key) ? -1 : 1;
                        var next = nodes.filter(function (candidate) {
                            return (candidate.renderedPosition()[axis] - position[axis]) * direction > 1;
                        }).sort(function (a, b) {
                            function cost(candidate) {
                                var p = candidate.renderedPosition();
                                var along = Math.abs(p[axis] - position[axis]);
                                var across = Math.abs(p[otherAxis] - position[otherAxis]);
                                return Math.hypot(along, across) + across * 2;
                            }
                            return cost(a) - cost(b) || a.id().localeCompare(b.id());
                        })[0];
                        if (next) i = nodes.indexOf(next);
                    }
                    node = nodes[i]; cursor = node.id();
                    cy.nodes('.keyboard-current').removeClass('keyboard-current');
                    node.addClass('keyboard-current');
                    revealNode(cy, node, el);
                    announceNode(cy, node, i, nodes.length);
                } else if ((e.key === 'Enter' || e.key === ' ') && !e.altKey && node) {
                    e.preventDefault(); cursor = node.id();
                    if (!e.shiftKey) cy.$('node:selected').unselect();
                    node.select(); node.emit('tap');
                    cy.nodes('.keyboard-current').removeClass('keyboard-current');
                    node.addClass('keyboard-current');
                    announceNode(cy, node, nodes.indexOf(node), nodes.length);
                } else if (e.key === 'Escape') {
                    e.preventDefault(); e.stopPropagation();
                    cursor = null;
                    cy.$('node:selected').unselect();
                    cy.nodes('.keyboard-current').removeClass('keyboard-current');
                    announce('Graph selection cleared. ' + graphHelp);
                } else if (isActionsKey(e) && node) {
                    e.preventDefault();
                    var pos = node.renderedPosition(), rect = el.getBoundingClientRect();
                    node.emit({type: 'cxttap', originalEvent: {preventDefault: function () {},
                        clientX: rect.left + pos.x, clientY: rect.top + pos.y}});
                } else if (['+', '=', '-', '0'].includes(e.key)) {
                    e.preventDefault();
                    if (e.key === '0') cy.fit(undefined, 30);
                    else cy.zoom({level: cy.zoom() * (e.key === '-' ? 0.8 : 1.25),
                        renderedPosition: {x: el.clientWidth / 2, y: el.clientHeight / 2}});
                }
            });
        });
    });

    function revealNode(cy, node, el) {
        var box = node.renderedBoundingBox({includeLabels: false});
        var pan = cy.pan(), dx = 0, dy = 0;
        if (box.x1 < 32) dx = 32 - box.x1;
        else if (box.x2 > el.clientWidth - 64) dx = el.clientWidth - 64 - box.x2;
        if (box.y1 < 32) dy = 32 - box.y1;
        else if (box.y2 > el.clientHeight - 60) dy = el.clientHeight - 60 - box.y2;
        if (dx || dy) cy.pan({x: pan.x + dx, y: pan.y + dy});
    }

    function announceNode(cy, node, index, count) {
        var selected = cy.$('node:selected').map(function (n) { return n.id(); });
        var summary = selected.slice(0, 3).join(', ');
        if (selected.length > 3) summary += ', and ' + (selected.length - 3) + ' more';
        announce('Focus: ' + node.id() + '. ' + node.data('type') + ', ' + node.data('status') +
            '. ' + (index + 1) + ' of ' + count + '. Selected: ' + (summary || 'none') +
            '. Enter selects the focused node.');
    }

    function start() {
        var help = document.createElement('span');
        help.id = 'keyboard-list-help';
        help.className = 'visually-hidden';
        help.textContent = 'Arrow keys browse this list. Home and End go to its ends. Enter opens an item. Alt+Enter opens actions.';
        document.body.appendChild(help);
        sync();
        new MutationObserver(sync).observe(document.body, {childList: true, subtree: true,
            attributes: true, attributeFilter: ['style', 'class']});
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
}());
