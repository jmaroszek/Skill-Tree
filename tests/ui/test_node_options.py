"""The node pickers' options."""
from skilltree.ui.canvas.view import node_options
from support.graphs import make_node


# ============================================================================
# node_options
# ============================================================================

class TestNodeOptions:
    def test_basic_options(self):
        nodes = [make_node("A"), make_node("B")]
        result = node_options(nodes)
        assert result == [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]

    def test_exclude_node(self):
        nodes = [make_node("A"), make_node("B"), make_node("C")]
        result = node_options(nodes, exclude="B")
        names = [r['value'] for r in result]
        assert "B" not in names
        assert len(result) == 2

    def test_empty_list(self):
        assert node_options([]) == []
