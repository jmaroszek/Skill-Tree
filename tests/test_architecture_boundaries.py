"""Keep shared operations usable without registering or importing UI callbacks."""
import ast
from pathlib import Path
import subprocess
import sys

import pytest


# Modules that hold graph/business logic. These must stay usable without the
# Dash UI stack, so callback_helpers (which imports dash, dbc and plotly) is
# off-limits to them as well as the callback registration modules themselves.
CORE_MODULES = [
    'skilltree.domain.goals', 'skilltree.features.analyze.data',
    'skilltree.domain.contexts', 'skilltree.store.commands',
    'skilltree.features.editor.values', 'skilltree.store.graph.manager',
    'skilltree.store.graph.repository', 'skilltree.store.graph.queries',
    'skilltree.store.graph.scoring', 'skilltree.domain.rules',
    'skilltree.store.graph.state', 'skilltree.shell', 'skilltree.ui.payloads',
]

# View-preparation modules. They legitimately build Dash components, so they may
# use callback_helpers — but they still must not import callback registration.
VIEW_MODULES = ['skilltree.features.home.view', 'skilltree.ui.canvas.view',
                'skilltree.engine.sidebars']


def _imports_of(module):
    source = Path(__file__).resolve().parents[1] / (module.replace('.', '/') + '.py')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or '')
            imports.extend(f'{node.module}.{alias.name}' for alias in node.names)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    return imports


@pytest.mark.parametrize('module', CORE_MODULES + VIEW_MODULES)
def test_shared_modules_do_not_import_callback_modules(module):
    offenders = [name for name in _imports_of(module)
                 if any(part == 'callbacks' or part.endswith('_callbacks')
                        for part in name.split('.'))]
    assert not offenders, f'{module} imports callback modules: {offenders}'


@pytest.mark.parametrize('module', CORE_MODULES)
def test_core_modules_do_not_depend_on_the_dash_ui_helper_layer(module):
    """Graph/business logic must not reach for the component-building helpers.

    callback_helpers pulls in dash, dash_bootstrap_components and plotly. A core
    module that imports it can no longer be used (or tested) without the UI stack,
    which is the coupling this split exists to remove.
    """
    assert not any('callback_helpers' in name.split('.')
                   for name in _imports_of(module))


def test_importing_application_modules_has_no_database_or_logging_side_effects():
    script = '''
import importlib
import logging
import sqlite3
def forbidden(*args, **kwargs):
    raise AssertionError("Import attempted to open a database")
sqlite3.connect = forbidden
handlers = list(logging.getLogger().handlers)
for name in (
    'app', 'skilltree.app', 'skilltree.services', 'skilltree.shell',
    'skilltree.ui.sidebars_layout', 'skilltree.engine.callbacks',
    'skilltree.features.details.callbacks', 'skilltree.features.analyze.callbacks',
    'skilltree.features.events.callbacks', 'skilltree.features.home.callbacks',
    'skilltree.features.settings.callbacks', 'skilltree.features.review.callbacks',
    'skilltree.features.goals.callbacks', 'skilltree.features.review.calibration',
    'skilltree.features.editor.resources',
):
    importlib.import_module(name)
assert logging.getLogger().handlers == handlers
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_networkx_loads_only_when_communities_are_detected():
    """NetworkX is hundreds of modules. The desktop window waits for the
    server to answer, so the server shouldn't load it first; app.main warms
    it in the background instead."""
    script = '''
import importlib
import sys
for name in (
    'app', 'skilltree.app', 'skilltree.services', 'skilltree.store.graph.manager',
    'skilltree.store.graph.queries', 'skilltree.engine.callbacks',
    'skilltree.features.details.callbacks', 'skilltree.features.analyze.callbacks',
    'skilltree.features.events.callbacks', 'skilltree.features.home.callbacks',
    'skilltree.features.settings.callbacks', 'skilltree.features.goals.callbacks',
):
    importlib.import_module(name)
assert 'networkx' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_canvas_view_preserves_filtering_and_focus_without_mutating_graph():
    from skilltree.ui.canvas.view import build_canvas_view
    from skilltree.engine.callbacks import generate_elements
    from skilltree.store.graph.manager import GraphManager
    from test_atomic_saves import graph
    manager = graph('A', 'B')
    manager.add_edge('A', 'B', 'Needs_Hard')
    version = GraphManager._graph_version
    view = build_canvas_view(
        manager, generate_elements, 'filter-context', None,
        'components', {}, 'All', 'B', None, None)
    assert {e['data']['id'] for e in view.elements if 'source' not in e['data']} == {'A', 'B'}
    assert view.clear_focus_style == {'display': 'inline-block'}
    assert any(rule['selector'] == 'node[id = "A"]' for rule in view.stylesheet)
    assert GraphManager._graph_version == version


def test_scoring_caches_are_scoped_to_database_identity(monkeypatch, tmp_path, temp_database):
    import sqlite3
    from contextlib import closing
    from skilltree.store import database
    from skilltree.store.graph.manager import GraphManager
    from test_atomic_saves import graph

    manager = graph('A', 'B')
    manager.add_edge('A', 'B', 'Needs_Soft')
    manager.get_priority_normalizer()
    first_key = manager.caches.normalizer_key
    other = str(tmp_path / 'other.db')
    # A connection's own `with` only commits; closing() also closes it.
    with closing(sqlite3.connect(temp_database)) as source, \
            closing(sqlite3.connect(other)) as target:
        source.backup(target)
        target.execute("UPDATE Nodes SET value=10 WHERE name='B'")
        target.commit()
    monkeypatch.setattr(database, 'get_db_path', lambda: other)
    assert manager.get_priority_normalizer() == GraphManager().get_priority_normalizer()
    assert manager.caches.normalizer_key != first_key
