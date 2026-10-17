"""Where the repository's files are, for tests that read them.

Test modules sit at different depths under tests/, so they find files from
here rather than from their own location.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
FIXTURES = ROOT / "tests" / "fixtures"


def asset_file(name):
    """The file called ``name`` under assets/, in whichever folder it sits."""
    found = sorted(ASSETS.rglob(name))
    assert len(found) == 1, f"expected one asset called {name}, found {found}"
    return found[0]


def app_asset_files(suffix):
    """The app's own files under assets/ that end in ``suffix``: every folder
    but vendor/, which Dash leaves out too."""
    return sorted(path for path in ASSETS.rglob(f"*{suffix}")
                  if "vendor" not in path.relative_to(ASSETS).parts)
