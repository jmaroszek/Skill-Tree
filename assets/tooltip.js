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
        function attachCytoEvents(selector) {
            var cyWrapper = document.querySelector(selector);
            if (!cyWrapper) {
                setTimeout(function() { attachCytoEvents(selector); }, 300);
                return;
            }

            // Immediately hide when mouse leaves the graph container entirely
            cyWrapper.addEventListener('mouseleave', function () {
                onNode = false;
                clearTimeout(showTimer);
                showTimer = null;
                clearTimeout(hideTimer);
                tooltip.style.display = 'none';
            });

            // Access the Cytoscape.js instance (Dash Cytoscape stores it on the DOM element)
            function getCyInstance() {
                if (cyWrapper && cyWrapper._cyreg && cyWrapper._cyreg.cy) {
                    return cyWrapper._cyreg.cy;
                }
                return null;
            }

            function bindCyEvents() {
                var cy = getCyInstance();
                if (!cy) {
                    setTimeout(bindCyEvents, 500);
                    return;
                }

                // Mouse enters a node — schedule tooltip after SHOW_DELAY_MS
                cy.on('mouseover', 'node', function (evt) {
                    var nodeId = evt.target.id();
                    onNode = true;
                    delayElapsed = false;
                    clearTimeout(hideTimer);
                    clearTimeout(showTimer);

                    // Hide tooltip immediately when moving to a different node
                    if (nodeId !== lastHoveredNodeId) {
                        tooltip.style.display = 'none';
                    }

                    showTimer = setTimeout(function () {
                        showTimer = null;
                        delayElapsed = true;
                        if (!onNode) return;
                        // If re-hovering the same node, Dash callback won't fire
                        // since mouseoverNodeData hasn't changed. Show existing content.
                        if (tooltip.innerText.trim().length > 0) {
                            positionTooltip(lastMouseX, lastMouseY);
                            tooltip.style.display = 'block';
                        }
                        // Otherwise MutationObserver will show it once Dash populates content
                    }, SHOW_DELAY_MS);

                    lastHoveredNodeId = nodeId;
                });

                // Mouse leaves a node — cancel show timer and start hide countdown
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

            bindCyEvents();
        }

        attachCytoEvents('#cytoscape-graph');
        attachCytoEvents('#goal-mini-graph');
        attachCytoEvents('#details-mini-graph');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTooltip);
    } else {
        initTooltip();
    }
})();
