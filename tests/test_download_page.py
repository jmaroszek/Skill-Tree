"""The website's download page offers every installer the release builds (P7.4).

website/index.html finds each installer in the latest release by its file
name, and electron/electron-builder.yml decides those names. If one changed
without the other, the page would quietly stop offering that download. This
builds the names from electron-builder.yml's own patterns and runs the page's
matching under Node.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "website" / "index.html"


def _templates():
    """artifactName for each top-level section of electron-builder.yml."""
    found, section = {}, None
    for line in (ROOT / "electron" / "electron-builder.yml").read_text().splitlines():
        if re.match(r"^\w+:", line):
            section = line.split(":")[0]
        match = re.match(r"^\s+artifactName:\s*(\S+)", line)
        if match:
            found[section] = match.group(1)
    return found


def _name(template, version="1.2.3", **values):
    name = template.replace("${version}", version)
    for key, value in values.items():
        name = name.replace("${%s}" % key, value)
    assert "${" not in name, name
    return name


def _release_names():
    t = _templates()
    return {
        "windows": _name(t["win"], ext="exe"),
        "mac-arm64": _name(t["mac"], arch="arm64", ext="dmg"),
        "mac-x64": _name(t["mac"], arch="x64", ext="dmg"),
        # electron-builder calls x64 "amd64" in a deb and "x86_64" in an AppImage.
        "linux-deb": _name(t["deb"], arch="amd64", ext="deb"),
        "linux-appimage": _name(t["linux"], arch="x86_64", ext="AppImage"),
    }


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to run the download page's script")
    script = re.search(r"<script>(.*?)</script>", PAGE.read_text(), re.S).group(1)
    result = subprocess.run([node, "-e", "global.window = {};\n" + script + "\n" + body],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_every_installer_the_release_builds_is_offered():
    names = _release_names()
    extras = [names["mac-arm64"].replace(".dmg", ".zip"), "latest.yml", "SHA256SUMS",
              names["windows"] + ".blockmap"]
    assets = [{"name": n, "size": 1, "browser_download_url": "https://x/" + n}
              for n in [*names.values(), *extras]]

    picked = _run("console.log(JSON.stringify(window.SkillTreeDownloads.pickAssets("
                  + json.dumps({"assets": assets})
                  + ").map(p => [p.kind.key, p.asset.name])));")

    assert dict(picked) == names


@pytest.mark.parametrize("platform, agent, arm, expected", [
    ("Win32", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", None, "windows"),
    ("MacIntel", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", True, "mac-arm64"),
    ("MacIntel", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", False, "mac-x64"),
    # Safari won't say which chip, so the visitor chooses.
    ("MacIntel", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", None, None),
    ("Linux x86_64", "Mozilla/5.0 (X11; Ubuntu; Linux x86_64)", None, "linux-deb"),
    ("Linux x86_64", "Mozilla/5.0 (X11; Fedora; Linux x86_64)", None, "linux-appimage"),
    ("iPhone", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)", True, None),
    ("Linux armv8l", "Mozilla/5.0 (Linux; Android 14; Pixel 8)", None, None),
])
def test_the_suggested_download_fits_the_visitor(platform, agent, arm, expected):
    args = ", ".join(json.dumps(v) for v in (platform, agent, arm))
    guess = _run(f"console.log(JSON.stringify(window.SkillTreeDownloads.guessKind({args})));")
    assert guess == expected
