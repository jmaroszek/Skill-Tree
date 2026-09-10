/**
 * Release deferred Details work after the newest graph layout settles.
 *
 * Cytoscape can briefly overlap two layout instances while replacing a
 * subtree. A monotonically increasing generation ignores the older stop, and
 * a short quiet window coalesces any back-to-back layoutstop events. Every
 * settled layout releases Time Simulation; root transitions also release the
 * subtasks table. The root travels with both signals so stale work is rejected.
 */
(function () {
    if (!window.SkillTree || !window.SkillTree.onCytoReady) return;

    function setNativeValue(input, value) {
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    window.SkillTree.onCytoReady('#details-mini-graph', function (cy) {
        var generation = 0;
        var records = new WeakMap();
        var quietTimer = null;
        var lastStartedRoot = null;
        var pendingRoot = null;

        cy.on('layoutstart', function (event) {
            generation += 1;
            if (quietTimer !== null) {
                clearTimeout(quietTimer);
                quietTimer = null;
            }
            var root = window.SkillTree._detailsLayoutRoot || null;
            // A root transition starts a new table-render cycle. Keep the
            // pending root through duplicate layout starts for that selection,
            // then clear it once the newest one settles. Passing through null
            // lets clearing and re-selecting the same node work again.
            if (root !== lastStartedRoot) {
                lastStartedRoot = root;
                pendingRoot = root;
            }
            if (event.layout && typeof event.layout === 'object') {
                records.set(event.layout, {
                    generation: generation,
                    root: root
                });
            }
        });

        cy.on('layoutstop', function (event) {
            var record = event.layout && records.get(event.layout);
            if (!record) {
                record = {
                    generation: generation,
                    root: window.SkillTree._detailsLayoutRoot || null
                };
            }
            // Only the most recently started layout may release deferred work.
            if (record.generation !== generation) return;

            if (quietTimer !== null) clearTimeout(quietTimer);
            quietTimer = setTimeout(function () {
                quietTimer = null;
                var root = record.root;
                if (!root || root !== window.SkillTree._detailsLayoutRoot) return;

                var simulationInput = document.getElementById(
                    'details-simulation-settled-trigger-input'
                );
                if (simulationInput) {
                    setNativeValue(simulationInput, JSON.stringify({
                        root: root,
                        settledAt: Date.now()
                    }));
                }

                // Filters can re-layout the same root without rebuilding its
                // table. Only a root transition releases table rendering.
                if (root !== pendingRoot) return;
                var tableInput = document.getElementById(
                    'details-layout-settled-trigger-input'
                );
                if (!tableInput) return;

                pendingRoot = null;
                setNativeValue(tableInput, JSON.stringify({
                    root: root,
                    settledAt: Date.now()
                }));
            }, 150);
        });
    });
})();
