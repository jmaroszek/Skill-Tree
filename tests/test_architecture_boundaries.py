"""Keep shared operations usable without registering or importing UI callbacks."""
import ast
from pathlib import Path
import subprocess
import sys

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
    'app', 'app_services', 'layout', 'sidebars_layout', 'callbacks',
    'details_callbacks', 'analyze_callbacks', 'event_callbacks',
    'next_callbacks', 'settings_callbacks', 'review_hub_callbacks',
    'sidebars_callbacks',
):
    importlib.import_module(name)
assert logging.getLogger().handlers == handlers
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
