(function () {
    'use strict';

    var win = typeof window !== 'undefined' ? window : globalThis;
    var NO_SUBCONTEXT = '__no_subcontext__';
    var SEPARATOR = '\u001f';
    var instances = new WeakMap();
    var activeInstance = null;
    var hoverMedia = win.matchMedia
        ? win.matchMedia('(hover: hover) and (pointer: fine)')
        : {matches: false};

    function normalizeTaxonomy(value) {
        if (!Array.isArray(value)) return [];
        return value
            .filter(function (item) { return item && typeof item.context === 'string'; })
            .map(function (item) {
                return {
                    context: item.context,
                    subcontexts: Array.isArray(item.subcontexts)
                        ? item.subcontexts.filter(function (sub) { return typeof sub === 'string'; })
                        : [],
                };
            });
    }

    function decodeSubcontextValue(value) {
        if (typeof value !== 'string') return null;
        var separatorIndex = value.indexOf(SEPARATOR);
        var separatorLength = 1;
        if (separatorIndex < 0) {
            separatorIndex = value.indexOf('::');
            separatorLength = 2;
        }
        if (separatorIndex < 0) return null;
        return {
            context: value.slice(0, separatorIndex),
            subcontext: value.slice(separatorIndex + separatorLength) || NO_SUBCONTEXT,
        };
    }

    function encodeSubcontextValue(context, subcontext) {
        return context + SEPARATOR + (subcontext === NO_SUBCONTEXT ? '' : subcontext);
    }

    function multiSelection(state) {
        var contexts = new Set(Array.isArray(state.context) ? state.context : []);
        var partial = new Map();
        (Array.isArray(state.subcontext) ? state.subcontext : []).forEach(function (value) {
            var decoded = decodeSubcontextValue(value);
            if (!decoded || !contexts.has(decoded.context)) return;
            if (!partial.has(decoded.context)) partial.set(decoded.context, new Set());
            partial.get(decoded.context).add(decoded.subcontext);
        });
        return {contexts: contexts, partial: partial};
    }

    function multiSummary(state, taxonomy, emptyLabel) {
        var selection = multiSelection(state);
        var summaries = [];
        var descriptions = [];
        taxonomy.forEach(function (item) {
            var context = item.context;
            if (!selection.contexts.has(context)) return;
            var selected = selection.partial.get(context);
            if (!selected || !selected.size) {
                summaries.push(context);
                descriptions.push(context + ': all subcontexts');
                return;
            }
            summaries.push(context + ' (' + selected.size + ')');
            descriptions.push(context + ': ' + Array.from(selected).map(function (subcontext) {
                return subcontext === NO_SUBCONTEXT ? 'No subcontext' : subcontext;
            }).join(', '));
        });
        var label = emptyLabel;
        if (summaries.length <= 2 && summaries.length) {
            label = summaries.join(' · ');
        } else if (summaries.length > 2) {
            label = summaries.slice(0, 2).join(' · ') + ' +' + (summaries.length - 2);
        }
        return {label: label, descriptions: descriptions, count: summaries.length};
    }

    function canonicalMultiState(taxonomy, contexts, partial) {
        var contextValue = [];
        var subcontextValue = [];
        taxonomy.forEach(function (item) {
            var context = item.context;
            if (!contexts.has(context)) return;
            contextValue.push(context);
            var selected = partial.get(context);
            if (!selected || !selected.size) return;
            item.subcontexts.concat([NO_SUBCONTEXT]).forEach(function (subcontext) {
                if (selected.has(subcontext)) {
                    subcontextValue.push(encodeSubcontextValue(context, subcontext));
                }
            });
        });
        return {context: contextValue, subcontext: subcontextValue};
    }

    win.SkillTreeContextPicker = {
        NO_SUBCONTEXT: NO_SUBCONTEXT,
        decodeSubcontextValue: decodeSubcontextValue,
        encodeSubcontextValue: encodeSubcontextValue,
        multiSelection: multiSelection,
        multiSummary: multiSummary,
        canonicalMultiState: canonicalMultiState,
    };

    if (typeof document === 'undefined') return;

    function setNativeValue(input, value) {
        window.SkillTree.setInputValue(input, value);
    }

    function dispatchSelection(instance, selection) {
        instance.state.context = selection.context;
        instance.state.subcontext = selection.subcontext;
        var payload = {
            context: selection.context,
            subcontext: selection.subcontext,
            nonce: Date.now() + Math.random(),
        };
        setNativeValue(instance.action, JSON.stringify(payload));
    }

    function parseState(instance) {
        try {
            var parsed = JSON.parse(instance.stateElement.textContent || '{}');
            parsed.mode = parsed.mode || instance.mode;
            parsed.taxonomy = normalizeTaxonomy(parsed.taxonomy);
            if (instance.mode === 'multi') {
                parsed.context = Array.isArray(parsed.context) ? parsed.context : [];
                parsed.subcontext = Array.isArray(parsed.subcontext) ? parsed.subcontext : [];
            } else {
                parsed.context = parsed.context || '';
                parsed.subcontext = parsed.subcontext || '';
            }
            return parsed;
        } catch (_error) {
            return {
                mode: instance.mode,
                taxonomy: [],
                context: instance.mode === 'multi' ? [] : '',
                subcontext: instance.mode === 'multi' ? [] : '',
            };
        }
    }

    function announce(instance, message) {
        if (instance.announcement) instance.announcement.textContent = message;
    }

    function updateTrigger(instance) {
        var value = instance.trigger.querySelector('.context-picker-value');
        if (!value) return;
        var isEmpty = instance.mode === 'single'
            ? !instance.state.context
            : !instance.state.context.length;
        value.classList.toggle('is-placeholder', isEmpty);
        if (instance.mode === 'single') {
            value.textContent = instance.state.context
                ? instance.state.context + (instance.state.subcontext
                    ? ' › ' + instance.state.subcontext : '')
                : instance.emptyLabel;
            instance.trigger.setAttribute(
                'aria-label',
                instance.state.context
                    ? 'Context: ' + value.textContent
                    : instance.emptyLabel
            );
            return;
        }
        var summary = multiSummary(instance.state, instance.state.taxonomy, instance.emptyLabel);
        value.textContent = summary.label;
        instance.trigger.setAttribute(
            'aria-label',
            summary.count ? 'Context filters: ' + summary.descriptions.join('; ') : instance.emptyLabel
        );
        if (summary.descriptions.length) instance.trigger.title = summary.descriptions.join('; ');
        else instance.trigger.removeAttribute('title');
        if (instance.clearButton) instance.clearButton.hidden = summary.count === 0;
    }

    function portal() {
        return document.getElementById('context-picker-portal') || document.body;
    }

    function positionPanel(instance) {
        if (!instance.panel || !instance.panel.isConnected) return;
        var triggerRect = instance.trigger.getBoundingClientRect();
        var viewportWidth = document.documentElement.clientWidth || win.innerWidth;
        var viewportHeight = document.documentElement.clientHeight || win.innerHeight;
        var width = Math.max(triggerRect.width, 260);
        width = Math.min(width, viewportWidth - 16);
        var left = Math.min(Math.max(8, triggerRect.left), viewportWidth - width - 8);
        instance.panel.style.width = width + 'px';
        instance.panel.style.left = left + 'px';
        instance.panel.style.top = (triggerRect.bottom + 2) + 'px';
        instance.panel.style.maxHeight = Math.min(430, Math.max(150, viewportHeight - 16)) + 'px';

        var panelHeight = instance.panel.getBoundingClientRect().height;
        var belowBottom = triggerRect.bottom + 2 + panelHeight;
        if (belowBottom > viewportHeight - 8 && triggerRect.top - panelHeight - 2 >= 8) {
            instance.panel.style.top = (triggerRect.top - panelHeight - 2) + 'px';
        } else if (belowBottom > viewportHeight - 8) {
            instance.panel.style.top = Math.max(8, viewportHeight - panelHeight - 8) + 'px';
        }
        positionSubmenu(instance);
    }

    function positionSubmenu(instance) {
        if (!instance.submenu || !instance.submenuAnchor
                || !instance.submenu.isConnected || !instance.submenuAnchor.isConnected) return;
        var anchorRect = instance.submenuAnchor.getBoundingClientRect();
        var panelRect = instance.panel.getBoundingClientRect();
        var submenuRect = instance.submenu.getBoundingClientRect();
        var viewportWidth = document.documentElement.clientWidth || win.innerWidth;
        var viewportHeight = document.documentElement.clientHeight || win.innerHeight;
        var left = panelRect.right + 5;
        if (left + submenuRect.width > viewportWidth - 8) {
            left = Math.max(8, panelRect.left - submenuRect.width - 5);
        }
        var top = Math.min(
            Math.max(8, anchorRect.top),
            Math.max(8, viewportHeight - submenuRect.height - 8)
        );
        instance.submenu.style.left = left + 'px';
        instance.submenu.style.top = top + 'px';
    }

    function moveButtonFocus(container, currentButton, direction) {
        var buttons = Array.from(container.querySelectorAll('button:not([disabled])'));
        var index = buttons.indexOf(currentButton);
        if (index < 0 || !buttons.length) return;
        buttons[(index + direction + buttons.length) % buttons.length].focus();
    }

    function closeSubmenu(instance) {
        if (instance.submenu) instance.submenu.remove();
        instance.submenu = null;
        instance.submenuAnchor = null;
        if (instance.contextList) {
            instance.contextList.querySelectorAll('[data-context]').forEach(function (row) {
                row.classList.remove('is-active');
                row.setAttribute('aria-expanded', 'false');
            });
        }
    }

    function closePicker(instance, restoreFocus) {
        if (!instance) return;
        win.clearTimeout(instance.hoverTimer);
        closeSubmenu(instance);
        if (instance.panel) instance.panel.remove();
        instance.panel = null;
        instance.contextList = null;
        instance.search = null;
        instance.trigger.setAttribute('aria-expanded', 'false');
        instance.trigger.removeAttribute('aria-controls');
        if (activeInstance === instance) activeInstance = null;
        if (restoreFocus) instance.trigger.focus();
    }

    function selectSingle(instance, context, subcontext) {
        var selection = {context: context, subcontext: subcontext || ''};
        dispatchSelection(instance, selection);
        updateTrigger(instance);
        announce(
            instance,
            subcontext
                ? 'Context set to ' + context + ', ' + subcontext + '.'
                : 'Context set to ' + context + ', no subcontext.'
        );
        closePicker(instance, true);
    }

    function openSingleSubmenu(instance, context, anchor, focusFirst) {
        closeSubmenu(instance);
        instance.activeContext = context;
        instance.submenuAnchor = anchor;
        var item = instance.state.taxonomy.find(function (entry) {
            return entry.context === context;
        });
        if (!item) return;

        var submenu = document.createElement('div');
        submenu.className = 'context-picker-submenu';
        submenu.setAttribute('role', 'listbox');
        submenu.setAttribute('aria-label', context + ' subcontexts');

        var heading = document.createElement('div');
        heading.className = 'context-picker-submenu-heading';
        heading.textContent = context;
        submenu.appendChild(heading);

        var options = document.createElement('div');
        submenu.appendChild(options);

        function subcontextKeydown(event) {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                moveButtonFocus(options, event.currentTarget, event.key === 'ArrowDown' ? 1 : -1);
                return;
            }
            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                closeSubmenu(instance);
                anchor.focus();
            }
        }

        item.subcontexts.forEach(function (subcontext) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'context-picker-menu-row';
            var selected = instance.state.context === context
                && instance.state.subcontext === subcontext;
            button.classList.toggle('is-selected', selected);
            button.setAttribute('role', 'option');
            button.setAttribute('aria-selected', String(selected));
            button.textContent = subcontext;
            button.addEventListener('click', function () {
                selectSingle(instance, context, subcontext);
            });
            button.addEventListener('keydown', subcontextKeydown);
            options.appendChild(button);
        });

        var divider = document.createElement('hr');
        divider.className = 'context-picker-no-subcontext-divider';
        options.appendChild(divider);

        var noneButton = document.createElement('button');
        noneButton.type = 'button';
        noneButton.className = 'context-picker-menu-row';
        var noneSelected = instance.state.context === context && !instance.state.subcontext;
        noneButton.classList.toggle('is-selected', noneSelected);
        noneButton.setAttribute('role', 'option');
        noneButton.setAttribute('aria-selected', String(noneSelected));
        noneButton.textContent = 'No subcontext';
        noneButton.addEventListener('click', function () {
            selectSingle(instance, context, '');
        });
        noneButton.addEventListener('keydown', subcontextKeydown);
        options.appendChild(noneButton);

        portal().appendChild(submenu);
        instance.submenu = submenu;
        anchor.classList.add('is-active');
        anchor.setAttribute('aria-expanded', 'true');
        positionSubmenu(instance);
        if (focusFirst) {
            var selectedButton = options.querySelector('.is-selected');
            (selectedButton || options.querySelector('button')).focus();
        }
    }

    function renderSingle(instance) {
        closeSubmenu(instance);
        var query = instance.search.value.trim().toLocaleLowerCase();
        var list = instance.contextList;
        list.replaceChildren();

        if (query) {
            var matches = [];
            instance.state.taxonomy.forEach(function (item) {
                item.subcontexts.forEach(function (subcontext) {
                    var path = item.context + ' › ' + subcontext;
                    if (path.toLocaleLowerCase().includes(query)) {
                        matches.push({context: item.context, subcontext: subcontext, path: path});
                    }
                });
                var noSubcontextPath = item.context + ' › No subcontext';
                if (noSubcontextPath.toLocaleLowerCase().includes(query)) {
                    matches.push({context: item.context, subcontext: '', path: noSubcontextPath});
                }
            });
            matches.forEach(function (match) {
                var button = document.createElement('button');
                button.type = 'button';
                button.className = 'context-picker-menu-row';
                button.textContent = match.path;
                button.addEventListener('click', function () {
                    selectSingle(instance, match.context, match.subcontext);
                });
                button.addEventListener('keydown', function (event) {
                    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                        event.preventDefault();
                        moveButtonFocus(list, button, event.key === 'ArrowDown' ? 1 : -1);
                    }
                });
                list.appendChild(button);
            });
            if (!matches.length) {
                var empty = document.createElement('div');
                empty.className = 'context-picker-empty';
                empty.textContent = 'No matching context path';
                list.appendChild(empty);
            }
            positionPanel(instance);
            return;
        }

        instance.state.taxonomy.forEach(function (item) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'context-picker-menu-row';
            button.dataset.context = item.context;
            button.setAttribute('role', 'option');
            button.setAttribute('aria-expanded', 'false');

            var label = document.createElement('span');
            label.className = 'context-picker-menu-path';
            label.textContent = item.context;
            var chevron = document.createElement('span');
            chevron.className = 'context-picker-right-chevron';
            chevron.setAttribute('aria-hidden', 'true');
            button.append(label, chevron);

            button.addEventListener('click', function (event) {
                openSingleSubmenu(instance, item.context, button, event.detail === 0);
            });
            button.addEventListener('pointerenter', function (event) {
                if (!hoverMedia.matches || event.pointerType !== 'mouse') return;
                win.clearTimeout(instance.hoverTimer);
                instance.hoverTimer = win.setTimeout(function () {
                    if (activeInstance === instance && !instance.search.value.trim()) {
                        openSingleSubmenu(instance, item.context, button, false);
                    }
                }, 500);
            });
            button.addEventListener('pointerleave', function () {
                win.clearTimeout(instance.hoverTimer);
            });
            button.addEventListener('keydown', function (event) {
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault();
                    moveButtonFocus(list, button, event.key === 'ArrowDown' ? 1 : -1);
                    return;
                }
                if (event.key === 'ArrowRight') {
                    event.preventDefault();
                    openSingleSubmenu(instance, item.context, button, true);
                }
            });
            list.appendChild(button);
        });
        positionPanel(instance);
    }

    function filterFocusKey(control) {
        if (!control) return null;
        return {
            context: control.dataset.filterContext || '',
            role: control.dataset.filterRole || '',
            subcontext: control.dataset.filterSubcontext || '',
        };
    }

    function findFilterControl(instance, key) {
        if (!key || !instance.contextList) return null;
        return Array.from(instance.contextList.querySelectorAll('[data-filter-role]')).find(
            function (control) {
                return (control.dataset.filterContext || '') === key.context
                    && (control.dataset.filterRole || '') === key.role
                    && (control.dataset.filterSubcontext || '') === key.subcontext;
            }
        ) || null;
    }

    function restoreFilterFocus(instance, key) {
        var control = findFilterControl(instance, key);
        if (control) control.focus();
    }

    function moveFilterFocus(instance, currentControl, direction) {
        var controls = Array.from(instance.contextList.querySelectorAll(
            'input[type="checkbox"][data-filter-role]'
        ));
        var anchor = currentControl;
        if (currentControl.dataset.filterRole === 'context-disclosure') {
            anchor = controls.find(function (control) {
                return control.dataset.filterContext === currentControl.dataset.filterContext
                    && control.dataset.filterRole === 'context-checkbox';
            });
        }
        var index = controls.indexOf(anchor);
        if (index < 0 || !controls.length) return;
        controls[(index + direction + controls.length) % controls.length].focus();
    }

    function applyMultiSelection(instance, contexts, partial, message) {
        var selection = canonicalMultiState(instance.state.taxonomy, contexts, partial);
        dispatchSelection(instance, selection);
        updateTrigger(instance);
        renderMulti(instance);
        announce(instance, message);
    }

    function toggleWholeContext(instance, context, checked, focusKey) {
        var selection = multiSelection(instance.state);
        if (checked) selection.contexts.add(context);
        else selection.contexts.delete(context);
        selection.partial.delete(context);
        applyMultiSelection(
            instance,
            selection.contexts,
            selection.partial,
            checked ? 'Selected all ' + context + ' subcontexts.' : 'Cleared ' + context + '.'
        );
        restoreFilterFocus(instance, focusKey);
    }

    function toggleChild(instance, item, subcontext, checked, focusKey) {
        var selection = multiSelection(instance.state);
        var allChildren = item.subcontexts.concat([NO_SUBCONTEXT]);
        var selected;
        if (selection.contexts.has(item.context) && !selection.partial.has(item.context)) {
            selected = new Set(allChildren);
        } else {
            selected = new Set(selection.partial.get(item.context) || []);
        }
        if (checked) selected.add(subcontext);
        else selected.delete(subcontext);

        if (!selected.size) {
            selection.contexts.delete(item.context);
            selection.partial.delete(item.context);
        } else {
            selection.contexts.add(item.context);
            if (selected.size === allChildren.length) selection.partial.delete(item.context);
            else selection.partial.set(item.context, selected);
        }
        applyMultiSelection(
            instance,
            selection.contexts,
            selection.partial,
            (checked ? 'Selected ' : 'Cleared ')
                + item.context + ', '
                + (subcontext === NO_SUBCONTEXT ? 'No subcontext' : subcontext) + '.'
        );
        restoreFilterFocus(instance, focusKey);
    }

    function renderMulti(instance) {
        var query = instance.search.value.trim().toLocaleLowerCase();
        var selection = multiSelection(instance.state);
        var list = instance.contextList;
        list.replaceChildren();
        var visibleContexts = 0;

        instance.state.taxonomy.forEach(function (item) {
            var contextMatches = item.context.toLocaleLowerCase().includes(query);
            var matchingSubcontexts = item.subcontexts.filter(function (subcontext) {
                return (item.context + ' ' + subcontext).toLocaleLowerCase().includes(query);
            });
            var noSubcontextMatches = (item.context + ' no subcontext')
                .toLocaleLowerCase().includes(query);
            if (query && !contextMatches && !matchingSubcontexts.length && !noSubcontextMatches) {
                return;
            }

            visibleContexts += 1;
            var context = item.context;
            var expanded = instance.expanded.has(context) || Boolean(query);
            var selected = selection.partial.get(context);
            var allSelected = selection.contexts.has(context) && (!selected || !selected.size);

            var wrapper = document.createElement('div');
            wrapper.className = 'context-picker-tree-context';
            wrapper.setAttribute('role', 'treeitem');
            wrapper.setAttribute('aria-expanded', String(expanded));

            var parent = document.createElement('div');
            parent.className = 'context-picker-tree-parent';

            var parentCheckbox = document.createElement('input');
            parentCheckbox.type = 'checkbox';
            parentCheckbox.className = 'context-picker-tree-parent-checkbox';
            parentCheckbox.dataset.filterContext = context;
            parentCheckbox.dataset.filterRole = 'context-checkbox';
            parentCheckbox.setAttribute('aria-label', 'Select all ' + context + ' subcontexts');
            parentCheckbox.checked = allSelected;
            parentCheckbox.indeterminate = selection.contexts.has(context) && !allSelected;
            parentCheckbox.addEventListener('click', function (event) {
                event.stopPropagation();
            });
            parentCheckbox.addEventListener('change', function () {
                toggleWholeContext(
                    instance,
                    context,
                    parentCheckbox.checked,
                    filterFocusKey(parentCheckbox)
                );
            });

            var disclosure = document.createElement('button');
            disclosure.type = 'button';
            disclosure.className = 'context-picker-tree-disclosure';
            disclosure.dataset.filterContext = context;
            disclosure.dataset.filterRole = 'context-disclosure';
            disclosure.setAttribute('aria-label', 'Show ' + context + ' subcontexts');
            disclosure.setAttribute('aria-expanded', String(expanded));
            var label = document.createElement('span');
            label.className = 'context-picker-menu-path';
            label.textContent = context;
            var chevron = document.createElement('span');
            chevron.className = 'context-picker-right-chevron';
            chevron.setAttribute('aria-hidden', 'true');
            disclosure.append(label, chevron);

            parent.addEventListener('click', function (event) {
                var target = event.target.closest('[data-filter-role]');
                var focusKey = filterFocusKey(target);
                if (instance.expanded.has(context)) instance.expanded.delete(context);
                else instance.expanded.add(context);
                renderMulti(instance);
                restoreFilterFocus(instance, focusKey);
            });
            parent.append(parentCheckbox, disclosure);
            wrapper.appendChild(parent);

            if (expanded) {
                var children = document.createElement('div');
                children.className = 'context-picker-tree-children';
                children.setAttribute('role', 'group');
                var shown = query && !contextMatches ? matchingSubcontexts : item.subcontexts;
                shown.forEach(function (subcontext) {
                    var child = document.createElement('label');
                    child.className = 'context-picker-tree-child';
                    var checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.dataset.filterContext = context;
                    checkbox.dataset.filterRole = 'subcontext-checkbox';
                    checkbox.dataset.filterSubcontext = subcontext;
                    checkbox.checked = allSelected || Boolean(selected && selected.has(subcontext));
                    checkbox.addEventListener('change', function () {
                        toggleChild(
                            instance,
                            item,
                            subcontext,
                            checkbox.checked,
                            filterFocusKey(checkbox)
                        );
                    });
                    var childLabel = document.createElement('span');
                    childLabel.textContent = subcontext;
                    child.append(checkbox, childLabel);
                    children.appendChild(child);
                });

                if (!query || contextMatches || noSubcontextMatches) {
                    var divider = document.createElement('hr');
                    divider.className = 'context-picker-no-subcontext-divider';
                    children.appendChild(divider);

                    var noSubcontext = document.createElement('label');
                    noSubcontext.className = 'context-picker-tree-child';
                    var noneCheckbox = document.createElement('input');
                    noneCheckbox.type = 'checkbox';
                    noneCheckbox.dataset.filterContext = context;
                    noneCheckbox.dataset.filterRole = 'subcontext-checkbox';
                    noneCheckbox.dataset.filterSubcontext = NO_SUBCONTEXT;
                    noneCheckbox.checked = allSelected
                        || Boolean(selected && selected.has(NO_SUBCONTEXT));
                    noneCheckbox.addEventListener('change', function () {
                        toggleChild(
                            instance,
                            item,
                            NO_SUBCONTEXT,
                            noneCheckbox.checked,
                            filterFocusKey(noneCheckbox)
                        );
                    });
                    var noneLabel = document.createElement('span');
                    noneLabel.textContent = 'No subcontext';
                    noSubcontext.append(noneCheckbox, noneLabel);
                    children.appendChild(noSubcontext);
                }
                wrapper.appendChild(children);
            }
            list.appendChild(wrapper);
        });

        if (!visibleContexts) {
            var empty = document.createElement('div');
            empty.className = 'context-picker-empty';
            empty.textContent = 'No matching context path';
            list.appendChild(empty);
        }
        positionPanel(instance);
    }

    function handleFilterKeydown(instance, event) {
        var current = event.target.closest('[data-filter-role]');
        if (!current || !instance.contextList.contains(current)) return;

        if (event.key === 'Enter' && current.matches('input[type="checkbox"]')) {
            event.preventDefault();
            current.click();
            return;
        }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            moveFilterFocus(instance, current, event.key === 'ArrowDown' ? 1 : -1);
            return;
        }

        var context = current.dataset.filterContext;
        var role = current.dataset.filterRole;
        var queryActive = Boolean(instance.search.value.trim());
        var expanded = instance.expanded.has(context) || queryActive;
        if (event.key === 'ArrowRight') {
            event.preventDefault();
            if (role === 'subcontext-checkbox') return;
            if (!expanded) {
                var focusKey = filterFocusKey(current);
                instance.expanded.add(context);
                renderMulti(instance);
                restoreFilterFocus(instance, focusKey);
                return;
            }
            var firstChild = Array.from(instance.contextList.querySelectorAll(
                '[data-filter-role="subcontext-checkbox"]'
            )).find(function (control) {
                return control.dataset.filterContext === context;
            });
            if (firstChild) firstChild.focus();
            return;
        }
        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            if (role === 'subcontext-checkbox') {
                restoreFilterFocus(instance, {
                    context: context,
                    role: 'context-checkbox',
                    subcontext: '',
                });
                return;
            }
            if (expanded && !queryActive) {
                var key = filterFocusKey(current);
                instance.expanded.delete(context);
                renderMulti(instance);
                restoreFilterFocus(instance, key);
            }
        }
    }

    function createPanel(instance) {
        var panel = document.createElement('div');
        panel.id = instance.root.id + '-menu';
        panel.className = 'context-picker-panel context-picker-panel-' + instance.mode;

        var search = document.createElement('input');
        search.type = 'search';
        search.className = 'form-control context-picker-search';
        search.placeholder = 'Search contexts and subcontexts…';
        search.setAttribute('aria-label', 'Search contexts and subcontexts');
        panel.appendChild(search);

        var list = document.createElement('div');
        list.className = 'context-picker-list';
        list.setAttribute('role', instance.mode === 'multi' ? 'tree' : 'listbox');
        list.setAttribute(
            'aria-label',
            instance.mode === 'multi' ? 'Context filters' : 'Contexts'
        );
        panel.appendChild(list);

        instance.panel = panel;
        instance.search = search;
        instance.contextList = list;
        portal().appendChild(panel);
        instance.trigger.setAttribute('aria-expanded', 'true');
        instance.trigger.setAttribute('aria-controls', panel.id);

        search.addEventListener('input', function () {
            if (instance.mode === 'multi') renderMulti(instance);
            else renderSingle(instance);
        });
        search.addEventListener('keydown', function (event) {
            if (event.key !== 'ArrowDown') return;
            event.preventDefault();
            var first = instance.mode === 'multi'
                ? list.querySelector('input[type="checkbox"][data-filter-role]')
                : list.querySelector('button');
            if (first) first.focus();
        });
        if (instance.mode === 'multi') {
            list.addEventListener('keydown', function (event) {
                handleFilterKeydown(instance, event);
            });
        }
        panel.addEventListener('scroll', function () {
            positionSubmenu(instance);
        });
    }

    function openPicker(instance) {
        if (activeInstance && activeInstance !== instance) closePicker(activeInstance, false);
        if (activeInstance === instance) {
            closePicker(instance, false);
            return;
        }
        activeInstance = instance;
        createPanel(instance);
        if (instance.mode === 'multi') {
            // Every open starts fully collapsed.
            instance.expanded.clear();
            renderMulti(instance);
        } else {
            renderSingle(instance);
        }
        positionPanel(instance);
        instance.search.focus();
    }

    function syncInstance(instance) {
        instance.state = parseState(instance);
        updateTrigger(instance);
        if (activeInstance === instance) {
            if (instance.mode === 'multi') renderMulti(instance);
            else renderSingle(instance);
        }
    }

    function wirePicker(root) {
        if (instances.has(root)) return;
        var instance = {
            root: root,
            mode: root.dataset.contextPickerMode,
            emptyLabel: root.dataset.emptyLabel || 'Select context',
            trigger: root.querySelector('.context-picker-trigger'),
            clearButton: root.querySelector('.context-picker-clear'),
            action: root.querySelector('.context-picker-action input'),
            stateElement: root.querySelector('.context-picker-state'),
            announcement: root.querySelector('[aria-live]'),
            state: null,
            expanded: new Set(),
            panel: null,
            search: null,
            contextList: null,
            submenu: null,
            submenuAnchor: null,
            activeContext: '',
            hoverTimer: null,
        };
        if (!instance.trigger || !instance.action || !instance.stateElement) return;
        instances.set(root, instance);
        syncInstance(instance);

        instance.trigger.addEventListener('click', function () {
            openPicker(instance);
        });
        if (instance.clearButton) {
            instance.clearButton.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                dispatchSelection(instance, {context: [], subcontext: []});
                updateTrigger(instance);
                if (activeInstance === instance) renderMulti(instance);
                announce(instance, 'All context filters cleared.');
            });
        }

        var observer = new MutationObserver(function () {
            syncInstance(instance);
        });
        observer.observe(instance.stateElement, {
            childList: true,
            subtree: true,
            characterData: true,
        });
    }

    function wireAll() {
        document.querySelectorAll('.context-picker-root').forEach(wirePicker);
    }

    document.addEventListener('pointerdown', function (event) {
        if (!activeInstance) return;
        var target = event.target;
        if (activeInstance.root.contains(target)
                || (activeInstance.panel && activeInstance.panel.contains(target))
                || (activeInstance.submenu && activeInstance.submenu.contains(target))) return;
        closePicker(activeInstance, false);
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && activeInstance) {
            event.preventDefault();
            closePicker(activeInstance, true);
        }
    });

    win.addEventListener('resize', function () {
        if (activeInstance) positionPanel(activeInstance);
    });
    document.addEventListener('scroll', function () {
        if (activeInstance) positionPanel(activeInstance);
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireAll, {once: true});
    } else {
        wireAll();
    }
    new MutationObserver(function (mutations) {
        var pickerAdded = mutations.some(function (mutation) {
            return Array.prototype.some.call(mutation.addedNodes, function (node) {
                return node.nodeType === 1 && (
                    node.matches('.context-picker-root')
                    || node.querySelector('.context-picker-root')
                );
            });
        });
        if (pickerAdded) wireAll();
    }).observe(document.documentElement, {
        childList: true,
        subtree: true,
    });
})();
