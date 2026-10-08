/** Focus boundaries shared by sliding panels, floating panels and fullscreen.
 * Loaded before feature scripts. Dash still owns opening, closing and draft
 * checks; this observes their result rather than maintaining another UI state.
 */
(function () {
    'use strict';
    var ST = window.SkillTree;
    var layers = [];
    var serial = 0;
    var keyboard = false;
    var tabbing = false;
    var action = null;
    var modalFocus = new Map();
    var pendingReturn = null;
    var selector = 'button, a[href], input:not([type="hidden"]), select, textarea, [tabindex]';

    function visible(el) {
        return Boolean(el && el.isConnected && !el.closest('[inert]') &&
            el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
    }

    function reveal(el) {
        if (!visible(el)) return;
        // Scroll only actual vertical scroll regions. scrollIntoView can move
        // overflow:hidden ancestors sideways to expose a translated sidebar.
        for (var p = el.parentElement; p; p = p.parentElement) {
            var css = getComputedStyle(p);
            if (!/auto|scroll/.test(css.overflowY) || p.scrollHeight <= p.clientHeight) continue;
            var box = p.getBoundingClientRect(), rect = el.getBoundingClientRect();
            var bottom = box.bottom - 8;
            var bar = p.querySelector('#node-editor-actions');
            if (bar && !bar.contains(el)) bottom = Math.min(bottom, bar.getBoundingClientRect().top - 8);
            if (rect.bottom > bottom) p.scrollTop += rect.bottom - bottom;
            rect = el.getBoundingClientRect();
            if (rect.top < box.top + 8) p.scrollTop -= box.top + 8 - rect.top;
        }
    }

    function focus(el) {
        if (!visible(el)) return false;
        el.focus({preventScroll: true});
        reveal(el);
        return document.activeElement === el;
    }

    function controls(root) {
        return Array.from(root.querySelectorAll(selector)).filter(function (el) {
            return visible(el) && !el.disabled && el.tabIndex >= 0;
        });
    }

    function returnFocus(el) {
        // A draft prompt can outlive the sidebar it closes. Restoring behind
        // that prompt is rejected by its focus enforcement, then lost when
        // Bootstrap tries to return to the now-inert editor field.
        var modal = Array.from(document.querySelectorAll('.modal')).filter(visible).at(-1);
        if (modal && !modal.contains(el)) pendingReturn = el;
        else focus(el);
    }

    // A base-select <select> draws its menu in the page, so Escape reaches the
    // page while the menu is open. Focus is then on one of its options.
    function openSelect(target) {
        var select = target.closest && target.closest('select');
        if (!select) return false;
        if (target !== select) return true;
        try { return select.matches(':open'); } catch (err) { return false; }
    }

    function register(cfg) {
        layers.push(Object.assign({open: false, root: null, order: 0, engaged: false}, cfg));
    }

    function activeLayers() {
        var modal = document.activeElement.closest('.modal.show') ||
            Array.from(document.querySelectorAll('.modal.show')).at(-1);
        return layers.filter(function (layer) {
            return layer.open && visible(layer.root) && (!modal || modal.contains(layer.root) ||
                (layer.opener && modal.contains(layer.opener)) ||
                (layer.modalId && modal.contains(document.getElementById(layer.modalId))));
        }).sort(function (a, b) {
            if (a.root.contains(b.root)) return -1;
            if (b.root.contains(a.root)) return 1;
            return a.order - b.order;
        });
    }

    function current() {
        if (document.querySelector('dialog[open]')) return null;
        var active = document.activeElement;
        return activeLayers().reverse().find(function (layer) {
            return layer.engaged || layer.root.contains(active) ||
                (layer.opener === active && layer.triggerId === active.id);
        });
    }

    function entry(layer) {
        var remembered = layer.lastId && document.getElementById(layer.lastId);
        var preferred = layer.initial && layer.root.querySelector(layer.initial);
        return (visible(remembered) && layer.root.contains(remembered) && !remembered.disabled && remembered) ||
            (visible(preferred) && !preferred.disabled && preferred) || controls(layer.root)[0] || layer.root;
    }

    function sync() {
        // Close everything first: switching between left sidebars must not
        // restore old focus after the new sidebar has received it.
        layers.forEach(function (layer) {
            var root = document.getElementById(layer.id);
            if (!root) {
                if (layer.open && layer.engaged && document.activeElement === document.body) {
                    returnFocus(layer.opener);
                }
                layer.root = null; layer.open = false; layer.engaged = false;
                return;
            }
            if (root !== layer.root) layer.open = false;
            layer.root = root;
            var open = layer.isOpen(root);
            if (layer.hideWhenClosed) {
                root.inert = !open;
                root.setAttribute('aria-hidden', String(!open));
            }
            var toggle = document.getElementById(layer.triggerId);
            if (toggle) {
                toggle.setAttribute('aria-expanded', String(open));
                toggle.setAttribute('aria-controls', layer.id);
            }
            if (layer.open && !open) {
                var restore = root.contains(document.activeElement) || layer.closing ||
                    (document.activeElement === document.body && layer.engaged);
                layer.open = false;
                layer.engaged = false;
                layer.closing = false;
                if (restore) returnFocus(visible(layer.opener) ? layer.opener : toggle);
            }
        });
        syncModalFocus();
        layers.forEach(function (layer) {
            var root = layer.root;
            if (!root || layer.open || !layer.isOpen(root)) return;
            layer.open = true;
            layer.order = ++serial;
            root.tabIndex = -1;
            var explicit = action && Date.now() - action.time < 2000 &&
                !action.target.closest('.nav-tabs');
            layer.opener = document.activeElement;
            layer.engaged = Boolean(explicit && action.keyboard);
            if (layer.engaged && activeLayers().includes(layer)) focus(entry(layer));
        });
        if (pendingReturn && !document.querySelector('dialog[open]') &&
                !Array.from(document.querySelectorAll('.modal')).some(visible)) {
            var target = pendingReturn;
            pendingReturn = null;
            if (document.activeElement === document.body || !visible(document.activeElement)) focus(target);
        }
    }

    function syncModalFocus() {
        // Bootstrap enforces focus in its own DOM subtree. A registered child
        // reference is portalled outside that subtree, so suspend enforcement
        // only while that child is open. Our boundary owns Tab/Escape meanwhile.
        var ids = new Set(layers.map(function (layer) { return layer.modalId; }).filter(Boolean));
        ids.forEach(function (id) {
            if (!document.getElementById(id)) return;
            var child = layers.find(function (layer) {
                return layer.modalId === id && layer.root && layer.isOpen(layer.root);
            });
            var suspended = Boolean(child);
            if (modalFocus.get(id) === suspended) return;
            modalFocus.set(id, suspended);
            window.dash_clientside.set_props(id, {enforceFocus: !suspended});
            if (child) requestAnimationFrame(function () {
                if (child.open && child.engaged && visible(child.root)) focus(entry(child));
            });
        });
    }

    function tab(event) {
        if (event.defaultPrevented || document.querySelector('dialog[open]')) return;
        var layer = current();
        // Bootstrap enforces modal focus after it escapes, leaving browser
        // chrome/body and the dialog wrapper as extra stops. Own the actual
        // sequential boundary, including the topmost of stacked modals.
        var modal = !layer && Array.from(document.querySelectorAll('.modal.show')).at(-1);
        if (modal) layer = {root: modal};
        if (!layer) return;
        var items = controls(layer.root);
        // Portalled dropdowns keep their native keyboard behavior. Once they
        // close, the containing panel resumes its normal focus boundary.
        var active = document.activeElement;
        if (active.closest('.context-picker-panel, .context-picker-submenu, .ctx-menu')) return;
        var trigger = Array.from(layer.root.querySelectorAll(
            '[aria-haspopup="listbox"][aria-expanded="true"][aria-controls], ' +
            '[role="combobox"][aria-expanded="true"][aria-controls]'))
            .find(function (control) {
                var portal = document.getElementById(control.getAttribute('aria-controls'));
                return portal && (portal.contains(active) || control === active);
            });
        if (trigger) {
            var portal = document.getElementById(trigger.getAttribute('aria-controls'));
            // Dash mounts some dropdown lists inside the sidebar and others
            // outside it. Neither their search nor their virtualized option
            // radios belong to the containing form's sequential focus order.
            items = items.filter(function (el) { return el === trigger || !portal.contains(el); });
            trigger.click(); active = trigger;
        } else if (!layer.root.contains(active)) {
            if (layer.opener === active && layer.triggerId === active.id) {
                // A pointer-opened panel need not steal focus. The next Tab
                // explicitly enters it instead of walking the toolbar first.
                event.preventDefault(); event.stopPropagation();
                layer.engaged = true;
                tabbing = true;
                try { focus(event.shiftKey ? items.at(-1) || layer.root : entry(layer)); }
                finally { tabbing = false; }
                return;
            }
            if (!modal) return;
        }
        event.preventDefault();
        event.stopPropagation();
        if (!items.length) { focus(layer.root); return; }
        var i = items.indexOf(active);
        var next = i < 0 ? (event.shiftKey ? items.length - 1 : 0)
            : (i + (event.shiftKey ? -1 : 1) + items.length) % items.length;
        tabbing = true;
        try { focus(items[next]); }
        finally { tabbing = false; }
        if (trigger) requestAnimationFrame(function () {
            // The dropdown's close animation may restore its own trigger after
            // our synchronous focus move. Finish that same Tab after it closes.
            if (document.activeElement === trigger && trigger.getAttribute('aria-expanded') !== 'true') {
                tabbing = true;
                try { focus(items[next]); }
                finally { tabbing = false; }
            }
        });
    }

    register({id: 'sidebar-editor-container', triggerId: 'btn-add', closeId: 'btn-close-editor',
        initial: '#search-node', hideWhenClosed: true,
        isOpen: function (el) { return el.style.transform === 'translateX(0px)'; }});
    register({id: 'details-goal-sidebar', triggerId: 'btn-goals-toggle', closeId: 'btn-details-goals-close',
        initial: '#details-goal-search', hideWhenClosed: true,
        isOpen: function (el) { return el.style.transform === 'translateX(0px)'; }});
    register({id: 'events-sidebar-container', triggerId: 'btn-events-sidebar-toggle', closeId: 'btn-events-sidebar-close',
        initial: '#events-search-input', hideWhenClosed: true,
        isOpen: function (el) { return el.style.transform === 'translateX(0px)'; }});
    register({id: 'sidebar-filters-container', triggerId: 'btn-filters-toggle', closeId: 'btn-close-filters',
        initial: '#filter-text', hideWhenClosed: true,
        isOpen: function (el) { return el.style.transform === 'translateX(0px)'; }});
    register({id: 'details-filters-sidebar', closeId: 'btn-details-filters-close', hideWhenClosed: true,
        isOpen: function (el) { return el.style.transform === 'translateX(0px)'; }});
    // Analyze's gear popovers render at the end of the page, out of Tab reach
    // from their gear. Opening one from the keyboard moves focus into it.
    [['popover-analyze-goals', 'btn-analyze-goals-limit'],
     ['popover-analyze-bottlenecks', 'btn-analyze-bottlenecks-limit'],
     ['popover-analyze-throughput', 'btn-analyze-throughput-gear']].forEach(function (pair) {
        register({id: pair[0], triggerId: pair[1], initial: 'input, select',
            isOpen: function (el) { return el.classList.contains('show'); },
            dismiss: function () { document.getElementById(pair[1]).click(); }});
    });
    ST.canvases.forEach(function (canvas) {
        register({id: canvas.settingsPanelId, triggerId: canvas.settingsToggleId,
            closeId: canvas.settingsCloseId, initial: 'input', hideWhenClosed: true,
            isOpen: function (el) { return el.style.display === 'block'; }});
        register({id: canvas.containerId, triggerId: canvas.fullscreenButtonId,
            initial: '#' + canvas.cytoscapeId,
            isOpen: function (el) { return el.classList.contains('canvas-fullscreen'); },
            dismiss: function () { document.getElementById(canvas.fullscreenButtonId).click(); }});
    });

    // `html.keyboard-mode` tells CSS how focus arrived. A text field matches
    // :focus-visible after a click too, so a field that wants its ring for the
    // keyboard only reads this. Typing in a field is not navigating, so only
    // Tab and the movement keys outside one switch it on; a pointer press
    // switches it off.
    var NAVIGATION_KEYS = ['Tab', 'Enter', ' ', 'ArrowUp', 'ArrowDown', 'ArrowLeft',
        'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'];
    function navigating(e) {
        if (NAVIGATION_KEYS.indexOf(e.key) === -1) return false;
        return e.key === 'Tab' || !e.target.matches ||
            !e.target.matches('textarea, [contenteditable], input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=button])');
    }

    document.addEventListener('pointerdown', function (e) {
        keyboard = false;
        document.documentElement.classList.remove('keyboard-mode');
        layers.forEach(function (layer) {
            if (layer.root && !layer.root.contains(e.target)) layer.engaged = false;
        });
    }, true);
    document.addEventListener('click', function (e) {
        action = {target: e.target, time: Date.now(), keyboard: keyboard && e.detail === 0};
        layers.forEach(function (layer) {
            if (layer.closeId && e.target.closest('#' + layer.closeId)) layer.closing = true;
        });
    }, true);
    document.addEventListener('focusin', function (e) {
        layers.forEach(function (layer) {
            if (!layer.open || !layer.root.contains(e.target)) return;
            if (e.target.matches('input, select, textarea, [aria-haspopup="listbox"], .keyboard-graph')) {
                layer.lastId = e.target.id;
            }
            if (keyboard) layer.engaged = true;
        });
        if (keyboard) { reveal(e.target); requestAnimationFrame(function () { reveal(e.target); }); }
    });
    document.addEventListener('keydown', function (e) {
        keyboard = true;
        if (navigating(e)) document.documentElement.classList.add('keyboard-mode');
        if (e.key !== 'Escape' || e.defaultPrevented || e.isComposing) return;
        if (e.target.closest('.ctx-menu, .context-picker-panel, .context-picker-submenu') ||
                document.querySelector('.context-picker-panel') ||
                document.querySelector('[aria-haspopup="listbox"][aria-expanded="true"], [role="combobox"][aria-expanded="true"]') ||
                e.target.closest('.Select.is-open') || openSelect(e.target)) return;
        // Graph selection is the innermost layer, before fullscreen itself.
        if (e.target.matches('.keyboard-graph')) {
            var cy = ST.getCy(e.target);
            if (cy && (cy.$('node:selected').length || cy.$('.keyboard-current').length)) return;
        }
        var layer = current();
        if (!layer) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        layer.closing = true;
        if (layer.dismiss) layer.dismiss();
        else {
            var close = document.getElementById(layer.closeId);
            if (close) close.click();
        }
    }, true);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Tab') tab(e);
    }, true);

    function start() {
        sync();
        new MutationObserver(sync).observe(document.body, {childList: true, subtree: true,
            attributes: true, attributeFilter: ['style', 'class']});
    }
    ST.keyboardFocus = {register: register, sync: sync, focus: focus, reveal: reveal,
        visible: visible, controls: controls, tab: tab, isKeyboard: function () { return keyboard; },
        isTabbing: function () { return tabbing; }};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
}());
