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
    var HIDE_DELAY_MS = 300;
    var onNode = false;
    var lastHoveredNodeId = null;

    function initTooltip() {
        var tooltip = document.getElementById('hover-tooltip');
        if (!tooltip) {
            setTimeout(initTooltip, 200);
            return;
        }

        // --- 1. Follow the cursor ---
        document.addEventListener('mousemove', function (e) {
            if (tooltip.style.display === 'none') return;
            var offset = 16;
            var tw = tooltip.offsetWidth;
            var th = tooltip.offsetHeight;
            var x = e.clientX + offset;
            var y = e.clientY + offset;
            tooltip.style.left = (x + tw > window.innerWidth  ? e.clientX - tw - offset : x) + 'px';
            tooltip.style.top  = (y + th > window.innerHeight ? e.clientY - th - offset : y) + 'px';
        });

        // --- 2. MutationObserver: show tooltip when Dash populates content ---
        var observer = new MutationObserver(function () {
            if (onNode && tooltip.innerText.trim().length > 0) {
                clearTimeout(hideTimer);
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

                // Mouse enters a node — show tooltip, cancel any hide timer
                cy.on('mouseover', 'node', function (evt) {
                    var nodeId = evt.target.id();
                    onNode = true;
                    clearTimeout(hideTimer);

                    // If re-hovering the same node, Dash callback won't fire
                    // since mouseoverNodeData hasn't changed. Show existing content.
                    if (nodeId === lastHoveredNodeId && tooltip.innerText.trim().length > 0) {
                        tooltip.style.display = 'block';
                    }
                    lastHoveredNodeId = nodeId;
                    // Content will be populated by Dash callback; MutationObserver shows it
                });

                // Mouse leaves a node — start the hide countdown
                cy.on('mouseout', 'node', function () {
                    onNode = false;
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
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTooltip);
    } else {
        initTooltip();
    }
})();
