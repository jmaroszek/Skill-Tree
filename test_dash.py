import dash
from app import update_graph, generate_elements
import traceback
from unittest.mock import patch

try:
    # mock context
    class MockCtx:
        triggered = [{'prop_id': 'btn-save.n_clicks'}]
        
    with patch('dash.callback_context', new=MockCtx()):
        res = update_graph(1, 0, "All", [], None, 
                           "Python Basics", "Topic", "", "Mind", "Open", "5", "5", "1.0", "2", 
                           ["Variables"], [], [], [])
                       
    print("SUCCESS")
except Exception as e:
    traceback.print_exc()

import sys; sys.exit(0)
