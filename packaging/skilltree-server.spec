# PyInstaller spec for the Skill Tree server: one folder, one console binary.
#
#   pip install -r requirements-build.txt
#   pyinstaller packaging/skilltree-server.spec --noconfirm
#
# Output: dist/skilltree-server/skilltree-server[.exe], with its libraries in
# dist/skilltree-server/_internal. electron-builder copies the folder into the
# desktop app's resources, and electron/main.js starts it with --desktop.
#
# A console binary, not a windowed one, even on Windows: the shell starts it
# hidden (windowsHide) and talks to it over stdin/stdout, which a windowed
# build doesn't reliably have.
import runpy
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent
unused = runpy.run_path(str(ROOT / "packaging" / "unused_files.py"))["unused"]

# The app's own CSS, JS and vendored theme (app_paths.resource_path finds
# them in the bundle). dash, dash_bootstrap_components and plotly bring their
# JS bundles through pyinstaller-hooks-contrib; dash_cytoscape has no hook.
datas = [(str(ROOT / "assets"), "assets")]
# Written per platform by third_party_notices.py; Settings > About opens it.
if (ROOT / "THIRD_PARTY_NOTICES.txt").is_file():
    datas.append((str(ROOT / "THIRD_PARTY_NOTICES.txt"), "."))
datas += collect_data_files("dash_cytoscape")

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    # Loaded by name in app.main to warm it up; also imported normally.
    hiddenimports=["networkx"],
    excludes=[
        # Not used, and large. tkinter is the browser-only file picker,
        # which callback_helpers turns off in a frozen build.
        "tkinter", "scipy", "matplotlib", "pandas", "IPython", "jupyter",
        "notebook", "pytest", "hypothesis", "playwright",
    ],
    noarchive=False,
)
# Development builds and plotly's Jupyter widget: about a quarter of the
# server, and never served (unused_files.py).
left_out = [entry for entry in a.datas if unused(entry[0])]
a.datas = [entry for entry in a.datas if not unused(entry[0])]
print(f"Left out {len(left_out)} files the server never uses "
      f"({sum(Path(src).stat().st_size for _, src, _ in left_out) / 1e6:.0f} MB).")
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="skilltree-server",
    console=True,
    icon=str(ROOT / "assets" / "skill_tree.ico"),
    # UPX-packed binaries draw antivirus false positives.
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="skilltree-server", upx=False)
