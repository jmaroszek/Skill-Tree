/** Shared boundary for Dash-controlled inputs and Cytoscape internals.
 * Loaded before feature assets by Dash's filename ordering.
 */
(function () {
    var SkillTree = window.SkillTree = window.SkillTree || {};
    var layouts = new WeakMap();

    SkillTree.getCy = function (element) {
        return element && element._cyreg && element._cyreg.cy || null;
    };

    SkillTree.setInputValue = function (input, value) {
        if (!input) return;
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    };

    // Preserve wrapper composition: the last registered hook runs first and
    // calls the preceding hook through next(options). Each instance owns its
    // own chain; duplicate registrations do not wrap it again.
    SkillTree.wrapLayout = function (cy, key, hook) {
        var state = layouts.get(cy);
        if (!state) {
            state = { base: cy.layout, hooks: [], keys: new Set() };
            layouts.set(cy, state);
            cy.layout = function (options) {
                function invoke(index, current) {
                    if (index < 0) return state.base.call(cy, current);
                    return state.hooks[index](function (updated) {
                        return invoke(index - 1, updated);
                    }, current);
                }
                return invoke(state.hooks.length - 1, options);
            };
        }
        if (state.keys.has(key)) return;
        state.keys.add(key);
        state.hooks.push(hook);
    };
})();
