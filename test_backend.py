from models import Node
from graph_manager import GraphManager

manager = GraphManager()

e_needs = ["Variables"]
e_helps = []
e_res = []
name = "Python Basics"

node = manager.get_node(name)

try:
    with manager.get_connection() as conn:
         cursor = conn.cursor()
         cursor.execute("DELETE FROM Edges WHERE target=? AND type='Needs'", (name,))
         conn.commit()
    for src in e_needs:
         manager.add_edge(src, name, "Needs")
         
    with manager.get_connection() as conn:
         cursor = conn.cursor()
         cursor.execute("DELETE FROM Edges WHERE (target=? OR source=?) AND type='Helps'", (name, name))
         conn.commit()
    for linked in e_helps:
         manager.add_edge(name, linked, "Helps")
         
    with manager.get_connection() as conn:
         cursor = conn.cursor()
         cursor.execute("DELETE FROM Edges WHERE target=? AND type='Resource'", (name,))
         conn.commit()
    for r_src in e_res:
         manager.add_edge(r_src, name, "Resource")

    # TEST SUGGESTIONS
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, {})
    scored = manager.calculate_priority_scores(filtered_nodes)
    valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
    
    print("BACKEND TEST PASSED")
except Exception as e:
    import traceback
    traceback.print_exc()

