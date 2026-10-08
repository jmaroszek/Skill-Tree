/**
 * Suggestions under the filters sidebar's Search field.
 *
 * As you type, the node names that hold every word you typed open in a panel
 * under the field, like the node editor's Search list. Unlike that list, the
 * field keeps free text: Enter filters by what you typed, and a suggestion only
 * fills the field with its name and applies it.
 *
 * The panel is built here and lives on <body>, as the context picker's does,
 * so the sidebar's overflow cannot clip it. The names arrive from a callback
 * (setNames). Nothing here reads or writes Dash state except the field's value,
 * which it sets the way the other bridges do, through the native setter.
 */
(function () {
    'use strict';
    var ST = window.SkillTree = window.SkillTree || {};
    var FIELD_ID = 'filter-text';
    var LIMIT = 8;

    var names = [];
    var panel = null;
    var items = [];
    var active = -1;

    function field() { return document.getElementById(FIELD_ID); }

    function terms(text) {
        return String(text || '').toLowerCase().split(/\s+/).filter(Boolean);
    }

    // Names holding every typed word. Ones that start with the first word come
    // first, since that is usually what is being typed.
    function matches(text) {
        var words = terms(text);
        if (!words.length) return [];
        var hits = names.filter(function (name) {
            var lower = name.toLowerCase();
            return words.every(function (word) { return lower.indexOf(word) !== -1; });
        });
        var head = words[0];
        hits.sort(function (a, b) {
            var rank = Number(b.toLowerCase().indexOf(head) === 0)
                - Number(a.toLowerCase().indexOf(head) === 0);
            return rank || a.length - b.length || a.localeCompare(b);
        });
        return hits.slice(0, LIMIT);
    }

    function setActive(index) {
        active = index;
        items.forEach(function (row, i) {
            row.classList.toggle('is-active', i === active);
            row.setAttribute('aria-selected', String(i === active));
        });
        var input = field();
        if (input) {
            if (active >= 0) input.setAttribute('aria-activedescendant', items[active].id);
            else input.removeAttribute('aria-activedescendant');
        }
        if (active >= 0 && items[active].scrollIntoView) {
            items[active].scrollIntoView({block: 'nearest'});
        }
    }

    function close() {
        if (panel) { panel.remove(); panel = null; }
        items = [];
        active = -1;
        var input = field();
        if (input) {
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
        }
    }

    function place() {
        var box = document.getElementById('filter-search');
        if (!panel || !box) return;
        var rect = box.getBoundingClientRect();
        panel.style.left = rect.left + 'px';
        panel.style.top = (rect.bottom + 4) + 'px';
        panel.style.width = rect.width + 'px';
    }

    function open() {
        var input = field();
        if (!input) return;
        var hits = matches(input.value);
        // Exactly what is typed, and nothing else to offer: no panel.
        if (!hits.length || (hits.length === 1 && hits[0] === input.value.trim())) {
            close();
            return;
        }
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'filter-suggest-panel';
            panel.className = 'filter-suggest';
            panel.setAttribute('role', 'listbox');
            // Choosing happens on mousedown, before the field loses focus.
            panel.addEventListener('mousedown', function (e) {
                e.preventDefault();
                var row = e.target.closest('.filter-suggest-item');
                if (row) choose(row.dataset.name);
            });
            document.body.appendChild(panel);
        }
        panel.textContent = '';
        items = hits.map(function (name, i) {
            var row = document.createElement('div');
            row.id = 'filter-suggest-' + i;
            row.className = 'filter-suggest-item';
            row.setAttribute('role', 'option');
            row.dataset.name = name;
            row.textContent = name;
            panel.appendChild(row);
            return row;
        });
        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-owns', panel.id);
        input.setAttribute('aria-expanded', 'true');
        active = -1;
        place();
    }

    // Write the field the way React notices, then apply it as Enter would.
    function choose(name) {
        var input = field();
        if (!input) return;
        var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(input, name);
        input.dispatchEvent(new Event('input', {bubbles: true}));
        close();
        input.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
    }

    document.addEventListener('input', function (e) {
        if (e.target.id === FIELD_ID) open();
    });
    document.addEventListener('focusin', function (e) {
        if (e.target.id === FIELD_ID && e.target.value) open();
    });
    document.addEventListener('focusout', function (e) {
        if (e.target.id === FIELD_ID) close();
    });
    document.addEventListener('keydown', function (e) {
        if (e.target.id !== FIELD_ID || !panel) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            var step = e.key === 'ArrowDown' ? 1 : -1;
            // From the typed text, the first arrow lands on the first (or last)
            // suggestion; a second one past either end returns to the text.
            var next = active + step;
            setActive(next < 0 && active === -1 ? items.length - 1
                : next >= items.length || next < 0 ? -1 : next);
        } else if (e.key === 'Enter' && active >= 0) {
            // A highlighted suggestion wins; otherwise Enter applies the text.
            e.preventDefault();
            e.stopPropagation();
            choose(items[active].dataset.name);
        } else if (e.key === 'Escape') {
            // The sidebar's own Escape stands down while aria-expanded is set,
            // so this only closes the panel.
            close();
        }
    }, true);
    window.addEventListener('resize', place);
    document.addEventListener('scroll', place, true);

    ST.filterSuggest = {
        setNames: function (list) { names = Array.isArray(list) ? list : []; },
        matches: matches
    };
})();
