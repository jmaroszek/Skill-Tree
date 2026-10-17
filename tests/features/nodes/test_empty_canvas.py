"""What the Nodes canvas says when it shows nothing."""
from skilltree.features.nodes.layout import empty_canvas_detail


# ============================================================================
# empty_canvas_detail
# ============================================================================

class TestEmptyCanvasDetail:
    @staticmethod
    def _hidden(hidden, done, dormant):
        return {"hidden": hidden, "done": done, "dormant": dormant}

    def test_names_done_nodes(self):
        assert empty_canvas_detail(self._hidden(1, 1, 0)) ==             "1 matching node is Done and hidden."
        assert empty_canvas_detail(self._hidden(3, 3, 0)) ==             "3 matching nodes are Done and hidden."

    def test_names_dormant_nodes(self):
        assert empty_canvas_detail(self._hidden(2, 0, 2)) ==             "2 matching nodes are Dormant and hidden."

    def test_splits_both_kinds(self):
        assert empty_canvas_detail(self._hidden(4, 3, 2)) ==             "4 matching nodes are hidden: 3 Done, 2 Dormant."

    def test_nothing_hidden_says_to_widen(self):
        assert empty_canvas_detail(self._hidden(0, 0, 0)) ==             "Widen the filters, or clear them."
