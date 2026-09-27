"""The Python app and the Electron shell ship one version."""
import json
import re
from pathlib import Path

from version import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_version_is_plain_semver():
    # electron-builder and the update feed need semver; a bare X.Y.Z is also
    # a valid PEP 440 version, so one string serves both toolchains.
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_electron_package_carries_the_app_version():
    package = json.loads((ROOT / "electron" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "electron" / "package-lock.json").read_text(encoding="utf-8"))

    assert package["version"] == __version__
    assert lock["version"] == __version__
    assert lock["packages"][""]["version"] == __version__
