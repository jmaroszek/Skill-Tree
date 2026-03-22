import dash
from callbacks import core_engine
import traceback
from unittest.mock import patch

try:
    # mock context
    class MockCtx:
        triggered = [{'prop_id': 'btn-save.n_clicks'}]
        
    with patch('dash.callback_context', new=MockCtx()):
        # Pass dummy defaults matching the new core_engine signature
        res = core_engine(
            1, 0, "All", "All", [], None, None,
            "All", "components", 1, 1, None, 10, 5,
            0, 0, 0, 0, 0, False, 0,
            "Python Basics", "Topic", "", "Mind", "None", ["Open"], 5, 5, 5,
            1.0, 1.0, 1.0, 
            [], [], [], [], [], [],
            "", "", [], {}, {}
        )
                       
    print("SUCCESS")
except Exception as e:
    traceback.print_exc()

import sys; sys.exit(0)
