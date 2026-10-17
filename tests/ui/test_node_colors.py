"""How canvas elements color a node."""
from skilltree.domain.models import EDGE_NEEDS_HARD
from skilltree.ui.canvas.elements import generate_elements
from skilltree.store.settings import DEFAULT_NODE_COLORS
from skilltree.store.graph.manager import GraphManager
from support.graphs import make_node


manager = GraphManager()


# ============================================================================
# generate_elements — Resource node color logic
# ============================================================================

class TestResourceNodeColor:
    """Tests that nodes get the right color in generate_elements.

    Expected colors are resolved from DEFAULT_NODE_COLORS rather than
    hardcoded so a future palette tweak doesn't break these checks; the
    intent of each test is encoded in which key it pulls (Resource vs.
    Done vs. Blocked, etc.).
    """

    def test_resource_open_gets_resource_color(self, services):
        manager.add_node(make_node("Res1", type="Resource", status="Open"))
        elements = generate_elements(services.graph, services.events)
        node_el = next(e for e in elements if e['data'].get('id') == 'Res1')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Resource']

    def test_resource_done_gets_done_color(self, services):
        manager.add_node(make_node("Res2", type="Resource", status="Done"))
        elements = generate_elements(services.graph, services.events)
        node_el = next(e for e in elements if e['data'].get('id') == 'Res2')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Done']

    def test_resource_blocked_gets_blocked_color(self, services):
        """Blocked resource nodes should follow the Blocked color, like other blocked types."""
        manager.add_node(make_node("Blocker", type="Learn", status="Open"))
        manager.add_node(make_node("Res3", type="Resource", status="Open"))
        manager.add_edge("Blocker", "Res3", EDGE_NEEDS_HARD)
        # Res3 should now be Blocked
        assert manager.get_node("Res3").status == "Blocked"
        elements = generate_elements(services.graph, services.events)
        node_el = next(e for e in elements if e['data'].get('id') == 'Res3')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Blocked']

    def test_goal_node_gets_goal_color(self, services):
        manager.add_node(make_node("G1", type="Goal"))
        elements = generate_elements(services.graph, services.events)
        node_el = next(e for e in elements if e['data'].get('id') == 'G1')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Goal']

    def test_normal_node_gets_status_color(self, services):
        manager.add_node(make_node("Learn1", type="Learn", status="Open"))
        elements = generate_elements(services.graph, services.events)
        node_el = next(e for e in elements if e['data'].get('id') == 'Learn1')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Open']
