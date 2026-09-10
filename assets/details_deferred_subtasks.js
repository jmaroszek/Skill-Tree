/**
 * Release deferred Details work after the newest graph layout settles.
 *
 * Cytoscape can briefly overlap two layout instances while replacing a
 * subtree. A monotonically increasing generation ignores the older stop, and
 * a short quiet window coalesces any back-to-back layoutstop events. Every
 * settled layout releases Time Simulation; root transitions also release the
 * subtasks table. The root travels with both signals so stale work is rejected.
 *
 * `layoutstop` is a promise over every per-node animation the layout started,
 * so anything that stops one of those without completing it swallows the event
 * — and the panels wait on a signal that can no longer arrive. Rather than
 * trust that nothing ever will, a deadline armed at layoutstart releases the
 * same work regardless. The visible cost of a missed stop is then a slightly
 * late table, not one that never loads.
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

    // Long enough that a healthy layout always settles first: the animation
    // itself runs 1s, plus the 150ms quiet window and room for a slow frame.
    var RELEASE_DEADLINE_MS = 4000;

    window.SkillTree.onCytoReady('#details-mini-graph', function (cy) {
        var generation = 0;
        var records = new WeakMap();
        var quietTimer = null;
        var deadlineTimer = null;
        var lastStartedRoot = null;
        var pendingRoot = null;

        function writeTrigger(id, root) {
            var input = document.getElementById(id);
            if (!input) return false;
            setNativeValue(input, JSON.stringify({root: root, settledAt: Date.now()}));
            return true;
        }

        // Shared by the normal settle and the deadline, so a late release is
        // the same release, never a second variant of it.
        function release(root) {
            if (!root || root !== window.SkillTree._detailsLayoutRoot) return;
            if (deadlineTimer !== null) {
                clearTimeout(deadlineTimer);
                deadlineTimer = null;
            }
            writeTrigger('details-simulation-settled-trigger-input', root);
            // Filters can re-layout the same root without rebuilding its
            // table. Only a root transition releases table rendering.
            if (root !== pendingRoot) return;
            if (writeTrigger('details-layout-settled-trigger-input', root)) {
                pendingRoot = null;
            }
        }

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
            // Capture the root this deadline is for. Reading the live one
            // when it fires would release a selection whose own layout has not
            // started yet, which is exactly the wait this gate exists to keep.
            if (deadlineTimer !== null) clearTimeout(deadlineTimer);
            deadlineTimer = setTimeout(function () {
                deadlineTimer = null;
                release(root);
            }, RELEASE_DEADLINE_MS);
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
                release(record.root);
            }, 150);
        });
    });
})();
