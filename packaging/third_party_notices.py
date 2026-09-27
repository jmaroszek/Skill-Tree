"""Write THIRD_PARTY_NOTICES.txt: what Skill Tree ships that others wrote (P7.1).

    python packaging/third_party_notices.py [OUT]

OUT defaults to THIRD_PARTY_NOTICES.txt at the repo root, where the server's
PyInstaller build picks it up and Settings > About opens it. It lists, each
with its license text:
- the Python packages the server runs on: requirements.txt and everything
  they pull in on this platform, read from the installed packages' metadata;
- the desktop shell's npm packages: electron/package.json's dependencies and
  theirs, read from electron/node_modules (skipped if it isn't installed);
- the fonts, icons and scripts vendored in assets/vendor.

Some Python dependencies are platform-specific, so each platform's build
writes its own file. Electron and Chromium ship their notices inside the app
(LICENSE.electron.txt and LICENSES.chromium.html), and the file says so.
"""
import argparse
import json
import re
import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
LICENSE_FILE = re.compile(r"^(licen[cs]e|copying|notice|authors)([._-].*)?$", re.IGNORECASE)
VENDORED = {
    "bootstrap-icons": "Bootstrap Icons, by The Bootstrap Authors",
    "bootswatch-darkly": "Bootswatch Darkly theme (with Bootstrap), by Thomas Park and The Bootstrap Authors",
    "lato": "Lato font, by Łukasz Dziedzic",
    "sortablejs": "SortableJS, by All contributors to SortableJS",
}
RULE = "=" * 78
MIT = """Copyright (c) {holder}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""


def _python_closure():
    """The installed distributions requirements.txt needs here, by name."""
    wanted = [Requirement(line.split("#")[0].strip())
              for line in (ROOT / "requirements.txt").read_text().splitlines()
              if line.split("#")[0].strip() and not line.startswith("-")]
    seen = {}
    while wanted:
        req = wanted.pop()
        if req.marker is not None and not req.marker.evaluate({"extra": ""}):
            continue
        key = req.name.lower().replace("_", "-")
        if key in seen:
            continue
        try:
            dist = metadata.distribution(req.name)
        except metadata.PackageNotFoundError:
            continue
        seen[key] = dist
        wanted.extend(Requirement(r) for r in (dist.requires or []))
    return [seen[k] for k in sorted(seen)]


def _python_license(dist):
    meta = dist.metadata
    name = meta.get("License-Expression") or ""
    if not name:
        short = (meta.get("License") or "").strip()
        if short and "\n" not in short and len(short) < 80:
            name = short
    if not name:
        classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or []
                       if c.startswith("License :: ")]
        name = ", ".join(classifiers)
    texts = []
    for file in dist.files or []:
        if LICENSE_FILE.match(Path(str(file)).name) and ".dist-info" in str(file):
            try:
                texts.append(Path(file.locate()).read_text(encoding="utf-8",
                                                           errors="replace").strip())
            except OSError:
                pass
    if not texts and meta.get("License") and "\n" in meta.get("License"):
        texts.append(meta.get("License").strip())
    return name or "see its project page", texts


def _npm_closure(root):
    """electron/package.json's runtime dependencies, and theirs."""
    modules = root / "node_modules"
    if not modules.is_dir():
        return None
    top = json.loads((root / "package.json").read_text())
    found = {}
    pending = [(name, root) for name in top.get("dependencies", {})]
    while pending:
        name, parent = pending.pop()
        # Node's lookup: the parent's own node_modules first, then upward.
        for base in [parent, *parent.parents]:
            candidate = base / "node_modules" / name
            if (candidate / "package.json").is_file():
                break
        else:
            continue
        if candidate in found:
            continue
        package = json.loads((candidate / "package.json").read_text())
        found[candidate] = package
        pending.extend((dep, candidate) for dep in package.get("dependencies", {}))
    return sorted(found.items(), key=lambda item: (item[1]["name"], item[1]["version"]))


def _file_texts(folder):
    return [f.read_text(encoding="utf-8", errors="replace").strip()
            for f in sorted(folder.iterdir())
            if f.is_file() and LICENSE_FILE.match(f.name)]


def _entry(title, license_name, texts):
    lines = [RULE, title, f"License: {license_name}", RULE]
    lines += [text + "\n" for text in texts] or ["(No license text is included in the "
                                                 "package; see its project page.)\n"]
    return "\n".join(lines)


def notices():
    parts = [
        "Skill Tree includes the work of others, listed here with their licenses.\n"
        "Electron and Chromium's own notices are in the desktop app, beside its\n"
        "executable: LICENSE.electron.txt and LICENSES.chromium.html. Python's\n"
        "license, for the interpreter inside the server, is under Python below.\n",
        "\n## The server: Python and its packages\n",
    ]
    parts.append(_entry(f"Python {sys.version.split()[0]}", "PSF-2.0",
                        ["Copyright (c) 2001 Python Software Foundation; All Rights Reserved.\n"
                         "The full license is at https://docs.python.org/3/license.html"]))
    for dist in _python_closure():
        license_name, texts = _python_license(dist)
        parts.append(_entry(f"{dist.metadata['Name']} {dist.version}", license_name, texts))
    npm = _npm_closure(ROOT / "electron")
    if npm is not None:
        parts.append("\n## The desktop shell's packages\n")
        for folder, package in npm:
            license_name = package.get("license") or "see its project page"
            texts = _file_texts(folder)
            if not texts and license_name == "MIT":
                # The package says MIT but ships no license file; MIT's terms
                # are fixed, and its author holds the copyright.
                author = package.get("author") or package["name"] + " authors"
                if isinstance(author, dict):
                    author = author.get("name", package["name"] + " authors")
                texts = [MIT.format(holder=author)]
            parts.append(_entry(f"{package['name']} {package['version']}",
                                license_name, texts))
    parts.append("\n## Fonts, icons and scripts in the page\n")
    for folder in sorted((ROOT / "assets" / "vendor").iterdir()):
        if folder.is_dir():
            title = VENDORED.get(folder.name, folder.name)
            texts = _file_texts(folder)
            parts.append(_entry(title, "OFL-1.1" if folder.name == "lato" else "MIT", texts))
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", nargs="?", type=Path, default=ROOT / "THIRD_PARTY_NOTICES.txt")
    args = parser.parse_args(argv)
    args.out.write_text(notices(), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
