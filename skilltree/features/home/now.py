"""The Now list's actions: the context menu's Now toggle, the cap's toast, and
reordering the Now cards."""
import json

from dash import Input, Output, no_update

from skilltree.domain.models import STATUS_DONE
from skilltree.store import database
from skilltree.store.settings import ConfigManager
from skilltree.ui import payloads as bridge_payloads


def register_now_callbacks(app, services):
    manager = services.graph

    # --- Context-Menu Now Toggle ---
    # Right-click → "Now" on the canvas / mini-graphs / goal sidebar
    # writes a JSON list of names + timestamp to toggle-now-trigger-input.
    # Set the selection to one deterministic state, then bump node-now-trigger-
    # input to cause the canvas to re-render. If any target is not Now, every
    # target is set Now; only an all-Now selection is cleared. This mirrors the
    # Done bulk action and avoids a mixed selection silently swapping states.
    @app.callback(
        Output("node-now-trigger-input", "value", allow_duplicate=True),
        Output("now-cap-refused-trigger", "value", allow_duplicate=True),
        Input("toggle-now-trigger-input", "value"),
        prevent_initial_call=True,
    )
    @database.serialized  # the cap check and the writes, as one step
    def handle_now_trigger(trigger_data):
        import time
        if not trigger_data:
            return no_update, no_update
        names = bridge_payloads.names(trigger_data)
        if not names:
            return no_update, no_update
        nodes = [n for n in (manager.get_node(name) for name in names) if n]
        if not nodes:
            return no_update, no_update
        nodes = [node for node in nodes if node.now > 0 or (
            not node.dormant and node.status != STATUS_DONE)]
        wants_now = any(node.now <= 0 for node in nodes)

        # Track count locally so a bulk set-Now stops at the cap. Pull
        # the live count once, then update it as we flip — get_now_nodes
        # would re-query the DB each iteration and miss our pending writes.
        now_nodes = manager.get_now_nodes()
        current_count = len(now_nodes)
        max_now = max([n.now for n in now_nodes]) if now_nodes else 0
        refused_any = False
        error = None
        # One ranking for the whole selection: each start scored the graph.
        with manager.ranking_batch():
            for node in nodes:
                before = node.now
                if not wants_now and node.now > 0:
                    # Clearing an all-Now selection is always allowed.
                    node.now = 0
                    current_count -= 1
                elif wants_now and node.now <= 0:
                    if current_count >= ConfigManager.get_now_node_cap():
                        refused_any = True
                        continue  # Cap reached — skip this set-Now.
                    max_now += 1
                    node.now = max_now
                    current_count += 1
                else:
                    continue
                try:
                    manager.update_node(node)
                except ValueError as e:
                    # The others still change; the toast names the refusal.
                    error = error or str(e)
                    current_count += -1 if node.now > 0 else 1
                    node.now = before
        ts = int(time.time() * 1000)
        if error is not None:
            refused_out = f"error|{ts}|{error}"
        else:
            refused_out = f"refused|{ts}" if refused_any else no_update
        return f"ctx|{ts}", refused_out

    # --- Now cap toast ---
    # Pops a transient warning when setting Now is refused for hitting the
    # cap. Both the editor dispatcher and the context-menu handler bump
    # now-cap-refused-trigger on refusal; this callback flips is_open and
    # dbc.Toast's `duration` auto-dismisses after 5s.
    @app.callback(
        Output("now-cap-toast", "is_open"),
        Output("now-cap-toast", "children"),
        Output("now-cap-toast", "header"),
        Input("now-cap-refused-trigger", "value"),
        prevent_initial_call=True,
    )
    def show_now_cap_toast(trigger):
        if not trigger:
            return False, no_update, no_update
        # "error|<ts>|<message>" carries a save's refusal; anything else is
        # the cap.
        if trigger.startswith("error|"):
            return True, trigger.split("|", 2)[2], "Couldn't change Now"
        cap = ConfigManager.get_now_node_cap()
        return True, f"{cap} Now nodes is the cap. Clear one to make room.", "Now Cap Reached"

    # --- Drag and drop reordering of Now cards ---
    @app.callback(
        Output("node-now-trigger-input", "value", allow_duplicate=True),
        Input("now-drag-order-input", "value"),
        prevent_initial_call=True,
    )

    def handle_now_reorder(order_json):
        if not order_json:
            return no_update
        try:
            names = json.loads(order_json)
        except (json.JSONDecodeError, TypeError):
            return no_update
        if isinstance(names, list) and names:
            manager.reorder_now_nodes(names)
            import time
            return f"reorder|{int(time.time() * 1000)}"
        return no_update
