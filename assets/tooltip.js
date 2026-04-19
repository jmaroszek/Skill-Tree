/**
 * Floating node tooltip for Skill Tree.
 *
 * Uses Cytoscape.js native node events (mouseover/mouseout) so the tooltip
 * stays visible while the cursor rests on a node and only starts fading
 * when the cursor moves off a node.
 *
 * Fix for same-node re-hover: if the tooltip already has content when the
 * user hovers the same node again, we show it immediately rather than
 * waiting for the Dash callback (which won't re-fire for identical data).
 */
(function () {

    var hideTimer = null;
    var showTimer = null;
    var HIDE_DELAY_MS = 300;
    var SHOW_DELAY_MS = 700;

    function readTooltipConfig() {
        var el = document.getElementById('tooltip-config');
        if (!el) return;
        var show = parseInt(el.getAttribute('data-show'), 10);
        var nodeHide = parseInt(el.getAttribute('data-node-hide'), 10);
        if (!isNaN(show)) SHOW_DELAY_MS = show;
        if (!isNaN(nodeHide)) HIDE_DELAY_MS = nodeHide;
    }

    var onNode = false;
    var lastHoveredNodeId = null;
    var delayElapsed = false;
    var lastMouseX = 0;
    var lastMouseY = 0;

    function initTooltip() {
        var tooltip = document.getElementById('hover-tooltip');
        if (!tooltip) {
            setTimeout(initTooltip, 200);
            return;
        }
        readTooltipConfig();

        // --- 1. Follow the cursor ---
        function positionTooltip(mx, my) {
            var offset = 16;
            var tw = tooltip.offsetWidth;
            var th = tooltip.offsetHeight;
            var x = mx + offset;
            var y = my + offset;
            tooltip.style.left = (x + tw > window.innerWidth  ? mx - tw - offset : x) + 'px';
            tooltip.style.top  = (y + th > window.innerHeight ? my - th - offset : y) + 'px';
        }

        document.addEventListener('mousemove', function (e) {
            lastMouseX = e.clientX;
            lastMouseY = e.clientY;
            if (tooltip.style.display === 'none') return;
            positionTooltip(e.clientX, e.clientY);
        });

        // --- 2. MutationObserver: show tooltip when Dash populates content ---
        var observer = new MutationObserver(function () {
            if (onNode && tooltip.innerText.trim().length > 0 && delayElapsed) {
                clearTimeout(hideTimer);
                positionTooltip(lastMouseX, lastMouseY);
                tooltip.style.display = 'block';
            }
        });
        observer.observe(tooltip, { childList: true, subtree: true, characterData: true });

        // --- 3. Attach to Cytoscape.js instance for precise node events ---
        // Container-level listener is attached once (survives cy replacement).
        // cy-level listeners are attached via onCytoReady so they re-bind if
        // dash-cytoscape ever swaps the underlying cy instance.
        var _mouseLeaveBound = {};

        function bindCyHandlers(cy) {
            cy.on('mouseover', 'node', function (evt) {
                var nodeId = evt.target.id();
                onNode = true;
                delayElapsed = false;
                clearTimeout(hideTimer);
                clearTimeout(showTimer);

                if (nodeId !== lastHoveredNodeId) {
                    tooltip.style.display = 'none';
                }

                showTimer = setTimeout(function () {
                    showTimer = null;
                    delayElapsed = true;
                    if (!onNode) return;
                    if (tooltip.innerText.trim().length > 0) {
                        positionTooltip(lastMouseX, lastMouseY);
                        tooltip.style.display = 'block';
                    }
                }, SHOW_DELAY_MS);

                lastHoveredNodeId = nodeId;
            });

            cy.on('mouseout', 'node', function () {
                onNode = false;
                delayElapsed = false;
                clearTimeout(showTimer);
                showTimer = null;
                clearTimeout(hideTimer);
                hideTimer = setTimeout(function () {
                    tooltip.style.display = 'none';
                }, HIDE_DELAY_MS);
            });
        }

        function attachCytoEvents(selector) {
            // Container-level mouseleave handler — attach once per selector.
            // The wrapper DOM persists across cy recreation, so this doesn't
            // need to run inside onCytoReady.
            if (!_mouseLeaveBound[selector]) {
                var wrapper = document.querySelector(selector);
                if (!wrapper) {
                    setTimeout(function () { attachCytoEvents(selector); }, 300);
                    return;
                }
                wrapper.addEventListener('mouseleave', function () {
                    onNode = false;
                    clearTimeout(showTimer);
                    showTimer = null;
                    clearTimeout(hideTimer);
                    tooltip.style.display = 'none';
                });
                _mouseLeaveBound[selector] = true;
            }

            if (window.SkillTree && window.SkillTree.onCytoReady) {
                window.SkillTree.onCytoReady(selector, bindCyHandlers);
            } else {
                // Helper not loaded yet — retry. Load order isn't guaranteed.
                setTimeout(function () { attachCytoEvents(selector); }, 100);
            }
        }

        attachCytoEvents('#cytoscape-graph');
        attachCytoEvents('#goal-mini-graph');
        attachCytoEvents('#details-mini-graph');
        attachCytoEvents('#events-detail-graph');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTooltip);
    } else {
        initTooltip();
    }
})();
