"""The package's layers, and the rules for importing across them.

skilltree/ is split by layer. Each may import only the layers it builds on:

    domain       pure logic: models, scoring, time, rules
    runtime      paths, the version, the server
    store        SQLite and what reads or writes it      domain, runtime
    ui           Dash pieces that features share         domain, runtime, store
    features/x   one feature's layout and callbacks      the above, and x itself
    composition  app, services, shell, engine            anything

Features don't import each other. The composition modules tie them together,
and tabs coordinate through the database and shared stores.

Three more rules hold everywhere:

- No module imports another module's _private names, or reads them as
  module._name. A name another module needs is public.
- skilltree modules import each other at the top of the file. Only
  skilltree.app defers its imports, so a launch that hands over to a running
  instance exits before loading Dash.
- __init__.py files stay empty, so importing a package runs nothing.

KNOWN_VIOLATIONS lists the imports that break a rule today. The refactor that
fixes one deletes it from the list. A new violation fails, and so does a
listed one that no longer happens, so the list only shrinks.
"""
import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'skilltree'

COMPOSITION = {'skilltree', 'skilltree.app', 'skilltree.services', 'skilltree.shell'}

# What each layer may import from the package.
ALLOWED = {
    'domain': {'domain'},
    'runtime': {'runtime'},
    'store': {'domain', 'runtime', 'store'},
    'ui': {'domain', 'runtime', 'store', 'ui'},
}

# Libraries a layer must not reach for.
FORBIDDEN_LIBRARIES = {
    'domain': {'sqlite3', 'dash', 'dash_bootstrap_components', 'dash_cytoscape',
               'plotly', 'flask', 'werkzeug'},
    'runtime': {'dash', 'dash_bootstrap_components', 'dash_cytoscape', 'plotly'},
    'store': {'dash', 'dash_bootstrap_components', 'dash_cytoscape', 'plotly',
              'flask', 'werkzeug'},
}

# The one module that may import the package inside its functions.
DEFERRED_IMPORTS_OK = {'skilltree.app'}

KNOWN_VIOLATIONS = {
    'deferred: skilltree.engine.callbacks -> skilltree.domain.models',
    'deferred: skilltree.engine.callbacks -> skilltree.store.events',
    'deferred: skilltree.features.details.layout -> skilltree.domain.models',
    'deferred: skilltree.features.onboarding.steps -> skilltree.store.database',
    'deferred: skilltree.features.review.callbacks -> skilltree.features.editor.values',
    'deferred: skilltree.features.settings.callbacks -> skilltree.store.events',
    'deferred: skilltree.features.settings.callbacks -> skilltree.store.settings',
    'deferred: skilltree.runtime.server -> skilltree.runtime.version',
    'deferred: skilltree.shell -> skilltree.features.home.view',
    'deferred: skilltree.store.backup -> skilltree.store.settings',
    'deferred: skilltree.store.commands -> skilltree.domain.models',
    'deferred: skilltree.store.database -> skilltree.store.backup',
    'deferred: skilltree.store.database -> skilltree.store.resources',
    'deferred: skilltree.store.events -> skilltree.domain.rules',
    'deferred: skilltree.store.events -> skilltree.store.graph.manager',
    'deferred: skilltree.store.events -> skilltree.store.settings',
    'deferred: skilltree.store.graph.manager -> skilltree.domain.contexts',
    'deferred: skilltree.store.graph.manager -> skilltree.store.events',
    'deferred: skilltree.store.graph.manager -> skilltree.store.settings',
    'deferred: skilltree.store.graph.queries -> skilltree.domain.communities',
    'deferred: skilltree.store.graph.queries -> skilltree.features.analyze.data',
    'deferred: skilltree.store.graph.scoring -> skilltree.runtime.perf',
    'deferred: skilltree.store.graph.state -> skilltree.store.database',
    'deferred: skilltree.store.settings -> skilltree.store.graph.manager',
    'deferred: skilltree.store.transfer -> skilltree.store.events',
    'deferred: skilltree.store.transfer -> skilltree.store.graph.manager',
    'deferred: skilltree.store.transfer -> skilltree.store.settings',
    'deferred: skilltree.ui.canvas.view -> skilltree.ui.styles',
    'layer: skilltree.features.review.calibration -> skilltree.features.editor.values',
    'layer: skilltree.features.review.callbacks -> skilltree.features.editor.values',
    'layer: skilltree.features.review.layout -> skilltree.features.editor.values',
    'layer: skilltree.store.commands -> skilltree.ui.payloads',
    'layer: skilltree.store.graph.queries -> skilltree.features.analyze.data',
    'layer: skilltree.ui.canvas.view -> skilltree.engine.response',
    'private: skilltree.app -> skilltree.store.database._db_path_cache',
    'private: skilltree.domain.goals -> skilltree.domain.scoring._done_names',
    'private: skilltree.domain.goals -> skilltree.domain.scoring._goals_above',
    'private: skilltree.domain.goals -> skilltree.domain.scoring._milestone_names',
    'private: skilltree.domain.goals -> skilltree.domain.scoring._strongest_routes',
    'private: skilltree.engine.callbacks -> skilltree.engine.sidebars._compute_sidebar_styles',
    'private: skilltree.engine.callbacks -> skilltree.features.editor.values._calibration_modal_text',
    'private: skilltree.engine.callbacks -> skilltree.features.editor.values._calibration_unit_for',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._RECENT_DAYS',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._REFLECTION_MIN_N',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._TYPE_ORDER',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._build_adjacency',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._compute_bottlenecks',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._compute_estimation_accuracy',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._compute_goal_progress',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._compute_overview',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._compute_rating_distribution',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._compute_reflection_drift',
    'private: skilltree.features.analyze.callbacks -> skilltree.features.analyze.data._compute_throughput',
    'private: skilltree.features.details.callbacks -> skilltree.features.details.layout._build_suggestion_row',
    'private: skilltree.features.events.callbacks -> skilltree.features.events.layout._event_trigger_type',
    'private: skilltree.features.review.calibration -> skilltree.features.editor.values._calibration_modal_text',
    'private: skilltree.features.review.calibration -> skilltree.features.editor.values._calibration_prepop',
    'private: skilltree.features.review.calibration -> skilltree.features.editor.values._calibration_review_queue',
    'private: skilltree.features.review.calibration -> skilltree.features.editor.values._calibration_unit_for',
    'private: skilltree.features.review.callbacks -> skilltree.features.editor.values._calibration_modal_text',
    'private: skilltree.features.review.callbacks -> skilltree.features.editor.values._calibration_prepop',
    'private: skilltree.features.review.callbacks -> skilltree.features.editor.values._calibration_review_queue',
    'private: skilltree.shell -> skilltree.features.home.view._initial_next_view',
    'private: skilltree.store.graph.manager -> skilltree.domain.rules._canonicalize_edge',
    'private: skilltree.store.graph.manager -> skilltree.domain.rules._is_prereq_satisfied',
    'private: skilltree.store.graph.manager -> skilltree.store.graph.queries._build_nx_graph',
    'private: skilltree.store.transfer -> skilltree.domain.rules._canonicalize_edge',
    'private: skilltree.store.transfer -> skilltree.store.backup._read_only_uri',
    'private: skilltree.store.transfer -> skilltree.store.database._initialized',
    'private: skilltree.store.transfer -> skilltree.store.database._refusal_for',
}


def _dotted(path):
    parts = list(path.relative_to(ROOT).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


MODULES = {_dotted(path): path for path in sorted(PACKAGE.rglob('*.py'))}


def _layer(module):
    if module in COMPOSITION or module.split('.')[:2] == ['skilltree', 'engine']:
        return 'composition'
    parts = module.split('.')
    if parts[1] == 'features':
        return f'feature:{parts[2]}' if len(parts) > 2 else 'composition'
    return parts[1]


def _may_import(source_layer, target_layer):
    if source_layer == 'composition':
        return True
    if source_layer.startswith('feature:'):
        return target_layer in {'domain', 'runtime', 'store', 'ui', source_layer}
    return target_layer in ALLOWED[source_layer]


def _target(module, name):
    """`from module import name` names a submodule, or something in module."""
    submodule = f'{module}.{name}'
    return (submodule, None) if submodule in MODULES else (module, name)


def _violations_of(module, path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    layer = _layer(module)
    aliases = {}
    found = set()

    def imported(target, name, deferred):
        library = target.split('.')[0]
        if library != 'skilltree':
            if library in FORBIDDEN_LIBRARIES.get(layer, ()):
                found.add(f'external: {module} -> {target}')
            return
        if not _may_import(layer, _layer(target)):
            found.add(f'layer: {module} -> {target}')
        if name and name.startswith('_') and not name.startswith('__'):
            found.add(f'private: {module} -> {target}.{name}')
        if deferred and module not in DEFERRED_IMPORTS_OK:
            found.add(f'deferred: {module} -> {target}')

    def visit(node, deferred):
        for child in ast.iter_child_nodes(node):
            inside = deferred or isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            if isinstance(child, ast.Import):
                for alias in child.names:
                    if alias.name in MODULES:
                        aliases[alias.asname or alias.name] = alias.name
                    imported(alias.name, None, deferred)
            elif isinstance(child, ast.ImportFrom):
                assert not child.level, f'{module} uses a relative import'
                for alias in child.names:
                    target, name = _target(child.module, alias.name)
                    if name is None:
                        aliases[alias.asname or alias.name] = target
                    imported(target, name, deferred)
            elif isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                owner = aliases.get(child.value.id)
                if (owner and owner != module and child.attr.startswith('_')
                        and not child.attr.startswith('__')):
                    found.add(f'private: {module} -> {owner}.{child.attr}')
            visit(child, inside)

    visit(tree, False)
    if path.name == '__init__.py' and path.read_text(encoding='utf-8').strip():
        found.add(f'init: {module} is not empty')
    return found


def test_imports_follow_the_layers():
    found = set().union(*(_violations_of(m, p) for m, p in MODULES.items()))
    new = sorted(found - KNOWN_VIOLATIONS)
    fixed = sorted(KNOWN_VIOLATIONS - found)
    assert not new, ("Imports that break the layer rules (this file's docstring "
                     "has them):\n  " + "\n  ".join(new))
    assert not fixed, ("These no longer happen. Delete them from "
                       "KNOWN_VIOLATIONS:\n  " + "\n  ".join(fixed))


def _import_everything(check):
    names = ['app', *MODULES]
    script = (
        'import importlib, logging, sqlite3, sys\n'
        'def forbidden(*args, **kwargs):\n'
        '    raise AssertionError("Import attempted to open a database")\n'
        'sqlite3.connect = forbidden\n'
        'handlers = list(logging.getLogger().handlers)\n'
        f'for name in {names!r}:\n'
        '    importlib.import_module(name)\n'
        + check)
    result = subprocess.run([sys.executable, '-c', script], capture_output=True,
                            text=True, timeout=60, cwd=ROOT)
    assert result.returncode == 0, result.stderr


def test_importing_any_module_opens_no_database_and_configures_no_logging():
    _import_everything('assert logging.getLogger().handlers == handlers\n')


def test_networkx_loads_only_when_communities_are_detected():
    """NetworkX is hundreds of modules. The desktop window waits for the
    server to answer, so the server shouldn't load it first; app.main warms
    it in the background instead."""
    _import_everything("assert 'networkx' not in sys.modules\n")
