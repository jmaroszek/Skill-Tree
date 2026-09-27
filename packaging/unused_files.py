"""The files in the server's packages that the frozen server never uses.

Dash and Dash Cytoscape ship development builds of their scripts, which Dash
serves only in debug mode, and plotly ships the script for its Jupyter widget.
Together they are about a quarter of the server. packaging/skilltree-server.spec
leaves out every file unused() names, and tests/test_frozen_build.py checks
that none of them is a file the app serves.

Source maps stay, though only a browser's developer tools ask for them: each
missing one would put an error in the log whenever those tools are open.
"""
from pathlib import PurePosixPath

PACKAGES = {"dash", "dash_cytoscape", "plotly"}
# plotly's Jupyter widget (FigureWidget), which needs anywidget.
WIDGET = PurePosixPath("plotly/package_data/widgetbundle.js")


def unused(dest):
    """True for a file the frozen server never reads or serves.

    ``dest`` is the file's path in the bundle, such as ``dash/dcc/async-graph.js``.
    """
    path = PurePosixPath(str(dest).replace("\\", "/"))
    if not path.parts or path.parts[0] not in PACKAGES:
        return False
    name = path.name
    return (name.endswith(".dev.js")
            # React's development builds; Dash serves the .min.js ones.
            or (path.parent == PurePosixPath("dash/deps") and not name.endswith(".min.js"))
            or path == WIDGET)
