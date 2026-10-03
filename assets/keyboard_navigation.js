/** Keyboard counterparts for custom cards, graph canvases and sortable lists.
 * Native form controls keep their own keys. Hidden sliding panels are inert;
 * opening/closing them preserves a useful place in the keyboard focus order.
 */
(function () {
    'use strict';
    var ST = window.SkillTree;
    var panels = [
        ['sidebar-editor-container', 'btn-add', 'btn-close-editor'],
        ['details-goal-sidebar', 'btn-goals-toggle', 'btn-details-goals-close'],
        ['events-sidebar-container', 'btn-events-sidebar-toggle', 'btn-events-sidebar-close'],
        ['sidebar-filters-container', 'btn-filters-toggle', 'btn-close-filters'],
    ];
    var keyboard = false;
    var pendingFocus = null;
    var lastFocused = null;
    var tooltipFocusIntent = false;
    var custom = '.suggestion-bar-row, .now-card, .goal-card, .event-card, .goal-rank-trigger, .details-subtask-name-link, [id*="details-milestone-tile"]';
    var reorderHandles = '.goal-drag-handle, .event-drag-handle, .ctx-drag-handle:not(.ctx-drag-disabled), .ctx-chip-grip';
    var graphHelp = 'Arrow keys: browse nodes. Home/End: first/last. Enter: select. Shift+Enter: add to selection. Shift+F10: actions. +/−: zoom. 0: fit.';
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
        // Bootstrap's anchor tabs have no href and otherwise fall out of the
        // browser's tab order. Native button tabs already handle activation.
        document.querySelectorAll('.nav-tabs a.nav-link').forEach(function (tab) {
            tab.tabIndex = tab.classList.contains('disabled') ? -1 : 0;
        });
        panels.forEach(function (cfg) {
            var panel = document.getElementById(cfg[0]);
            if (!panel) return;
            var open = cfg[0] === 'sidebar-filters-container'
                ? panel.style.right === '0px' : panel.style.transform === 'translateX(0px)';
            var previous = panel._keyboardOpen;
            if (previous === open) return;
            panel._keyboardOpen = open;
            panel.inert = !open;
            panel.setAttribute('aria-hidden', String(!open));
            var toggle = document.getElementById(cfg[1]);
            if (toggle) {
                toggle.setAttribute('aria-expanded', String(open));
                toggle.setAttribute('aria-controls', cfg[0]);
            }
            if (open && previous === false && keyboard && !document.querySelector('.modal.show')) {
                panel._keyboardOpener = document.activeElement;
                var first = panel.querySelector('button:not([disabled]), input:not([type=hidden]):not([disabled]), select:not([disabled]), [tabindex="0"]');
                if (first) first.focus({preventScroll: true});
            } else if (!open && panel.contains(document.activeElement)) {
                var opener = panel._keyboardOpener;
                if (!opener || !opener.isConnected || opener.closest('[inert]')) opener = toggle;
                if (opener) opener.focus({preventScroll: true});
            }
        });
        document.querySelectorAll(reorderHandles).forEach(function (handle) {
            if (handle.tabIndex === 0) return;
            handle.tabIndex = 0;
            handle.setAttribute('role', 'button');
            handle.setAttribute('aria-label', 'Reorder with Alt + arrow keys');
            handle.title = 'Alt + arrow keys to reorder';
        });
        if (ST.describeSplitHandle) document.querySelectorAll('.split-handle').forEach(function (handle) {
            if (!handle.hasAttribute('aria-valuenow')) ST.describeSplitHandle(handle);
        });
        if (pendingFocus) {
            var candidates = document.querySelectorAll(pendingFocus.selector);
            var row = Array.from(candidates).find(function (el) {
                return el.getAttribute(pendingFocus.attribute) === pendingFocus.name;
            });
            if (row && row !== pendingFocus.original) {
                var target = pendingFocus.handle ? row.querySelector(pendingFocus.handle) : row;
                if (target) target.focus({preventScroll: true});
                pendingFocus = null;
            } else if (Date.now() > pendingFocus.deadline) pendingFocus = null;
        }
        if (keyboard && lastFocused && !lastFocused.isConnected && document.activeElement === document.body &&
                !document.querySelector('.modal.show')) {
            var replacement = lastFocused.id && document.getElementById(lastFocused.id);
            var name = lastFocused.getAttribute('data-node-menu');
            if (!replacement && name) replacement = Array.from(document.querySelectorAll('[data-node-menu]'))
                .find(function (el) { return el.getAttribute('data-node-menu') === name && el.getClientRects().length; });
            if (replacement) replacement.focus({preventScroll: true});
        }
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
        target.focus({preventScroll: true});
        announce('Moved to position ' + (siblings.indexOf(other) + 1));
        return true;
    }

    document.addEventListener('pointerdown', function () { keyboard = false; pendingFocus = null; }, true);
    // Keep hover-only tooltips available on deliberate Tab navigation without
    // reopening them when a mouse-opened modal restores focus to its button.
    document.addEventListener('keydown', function (e) {
        tooltipFocusIntent = e.key === 'Tab';
        setTimeout(function () { tooltipFocusIntent = false; }, 0);
    }, true);
    document.addEventListener('focusin', function (e) {
        lastFocused = e.target;
        if (tooltipFocusIntent && e.target.matches('button, a, [tabindex="0"]') &&
                !e.target.closest('.ctx-menu') && !e.target.matches('.keyboard-graph')) {
            e.target._keyboardTooltip = true;
            e.target.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
        }
    });
    document.addEventListener('focusout', function (e) {
        if (!e.target._keyboardTooltip) return;
        e.target._keyboardTooltip = false;
        e.target.dispatchEvent(new MouseEvent('mouseout', {bubbles: true, relatedTarget: e.relatedTarget}));
    });
    document.addEventListener('keydown', function (e) {
        keyboard = true;
        if (e.defaultPrevented || e.isComposing) return;
        var target = e.target;
        if (!target.matches) return;
        if (target.matches('.nav-tabs .nav-link')) {
            if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
                e.preventDefault();
                var tabs = Array.from(target.closest('.nav-tabs').querySelectorAll('.nav-link:not(.disabled)'));
                var i = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1
                    : (tabs.indexOf(target) + (e.key === 'ArrowLeft' ? -1 : 1) + tabs.length) % tabs.length;
                tabs[i].focus(); tabs[i].click(); return;
            }
            if (target.tagName === 'A' && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault(); target.click(); return;
            }
        }
        if (e.altKey && ['ArrowUp', 'ArrowLeft', 'ArrowDown', 'ArrowRight'].includes(e.key)) {
            if (reorder(target, ['ArrowUp', 'ArrowLeft'].includes(e.key) ? -1 : 1)) {
                e.preventDefault(); return;
            }
        }
        if ((e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) &&
                target.matches('[data-node-menu], .event-card')) {
            e.preventDefault();
            var rect = target.getBoundingClientRect();
            target.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true,
                clientX: rect.left + 16, clientY: rect.top + 16}));
            return;
        }
        if ((e.key === 'Enter' || e.key === ' ') && !e.altKey && !e.ctrlKey && !e.metaKey && target.matches(custom)) {
            e.preventDefault(); target.click(); return;
        }
        if (e.key === 'Escape' && !document.querySelector('.modal.show, .ctx-menu[style*="display: block"]')) {
            var cfg = panels.find(function (p) {
                var panel = document.getElementById(p[0]);
                return panel && panel.contains(target) && !panel.inert;
            });
            if (cfg) {
                e.preventDefault(); document.getElementById(cfg[2]).click();
            }
        }
    });

    ST.canvases.forEach(function (canvas) {
        var cursor = null;
        ST.onCytoReady('#' + canvas.cytoscapeId, function (cy) {
            var el = document.getElementById(canvas.cytoscapeId);
            el.classList.add('keyboard-graph');
            el.tabIndex = 0;
            el.setAttribute('role', 'group');
            el.setAttribute('aria-label', 'Graph. ' + graphHelp);
            el.title = graphHelp;
            // DOM listeners belong to the wrapper once; fetch the current cy
            // at use time so a Dash remount does not retain the old instance.
            if (el._keyboardBound) return;
            el._keyboardBound = true;
            el.addEventListener('focus', function () {
                if (keyboard) announce(graphHelp);
            });
            el.addEventListener('keydown', function (e) {
                if (e.target !== el || e.altKey || e.ctrlKey || e.metaKey) return;
                var cy = ST.getCy(el);
                if (!cy) return;
                var nodes = cy.nodes().filter(function (n) { return n.visible(); }).toArray()
                    .sort(function (a, b) { return a.id().localeCompare(b.id()); });
                var node = nodes.find(function (n) { return n.id() === cursor; });
                if (!node) node = nodes.find(function (n) { return n.selected(); }) || nodes[0];
                if (['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End'].includes(e.key)) {
                    e.preventDefault();
                    if (!nodes.length) { announce('Graph is empty'); return; }
                    var i = nodes.indexOf(node);
                    if (e.key === 'Home') i = 0;
                    else if (e.key === 'End') i = nodes.length - 1;
                    else if (cursor !== null) i = (i + (['ArrowUp', 'ArrowLeft'].includes(e.key) ? -1 : 1) + nodes.length) % nodes.length;
                    node = nodes[i]; cursor = node.id();
                    cy.nodes('.keyboard-current').removeClass('keyboard-current');
                    node.addClass('keyboard-current');
                    cy.center(node);
                    announce(node.id() + '. ' + node.data('type') + ', ' + node.data('status') + '. ' + (i + 1) + ' of ' + nodes.length);
                } else if ((e.key === 'Enter' || e.key === ' ') && node) {
                    e.preventDefault(); cursor = node.id();
                    if (!e.shiftKey) cy.$('node:selected').unselect();
                    node.select(); node.emit('tap');
                    announce('Selected ' + node.id());
                } else if ((e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) && node) {
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

    function start() {
        sync();
        new MutationObserver(function (records) {
            if (records.some(function (r) { return r.type === 'childList' || panels.some(function (p) { return p[0] === r.target.id; }); })) sync();
        }).observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['style']});
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
}());
