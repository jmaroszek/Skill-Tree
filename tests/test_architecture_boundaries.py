"""Keep shared operations usable without registering or importing UI callbacks."""
import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize('module', [
    'goal_ranking', 'graph_analytics', 'context_rules', 'node_commands',
    'editor_values', 'next_view', 'graph_manager',
])
def test_shared_modules_do_not_import_callback_modules(module):
    source = Path(__file__).resolve().parents[1] / f'{module}.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or '')
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    assert not [name for name in imports
                if name == 'callbacks' or name.endswith('_callbacks')]


def test_layout_does_not_import_callback_modules():
    test_shared_modules_do_not_import_callback_modules('layout')
