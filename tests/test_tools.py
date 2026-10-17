"""The developer tools start when run as scripts, the way CI and the docs run them."""
import importlib.util
import subprocess
import sys

import pytest
from support.paths import ROOT


needs_playwright = pytest.mark.skipif(
    importlib.util.find_spec('playwright') is None,
    reason="animation_bench imports Playwright, which only some CI jobs install")


@pytest.mark.parametrize('tool', [
    'perf_bench', 'perf_graph', pytest.param('animation_bench', marks=needs_playwright),
])
def test_a_tool_starts_as_a_script(tool):
    """`python tools/x.py` puts tools/ on sys.path, not the repo. A package
    import above a tool's own sys.path setup failed in CI and nowhere else,
    since pytest already has the repo on sys.path."""
    result = subprocess.run([sys.executable, f'tools/{tool}.py', '--help'],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
