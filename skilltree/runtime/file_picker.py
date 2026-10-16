"""The file and folder picker for the standalone browser. The desktop shell
uses its own native dialog."""
import json


def spawn_local_file_picker(initial_dir, title, filetypes_list, directory=False):
    """Standalone-browser fallback picker. Electron uses its native dialog.

    ``directory`` picks a folder instead of a file; ``filetypes_list`` is then
    ignored.
    """
    import logging
    import re
    import subprocess
    import sys

    _logger = logging.getLogger(__name__)
    if getattr(sys, "frozen", False):
        # sys.executable is the Skill Tree server itself here: "-c <script>"
        # would start another server. The desktop shell's native picker
        # (assets/resource_picker.js) serves the frozen build.
        _logger.warning("No file picker in this build; paste the path instead.")
        return ""
    # Import clears device-local roots. For older data, never pass a UNC or
    # extended path to Tk before the user has chosen it in the dialog.
    if not isinstance(initial_dir, str) or initial_dir.startswith(("\\\\", "//")):
        initial_dir = ""
    elif sys.platform == "win32":
        initial_dir = initial_dir if re.match(r"^[A-Za-z]:[\\/]", initial_dir) else ""
    else:
        initial_dir = initial_dir if initial_dir.startswith("/") else ""
    script = '''import json
import os
import sys
import tkinter as tk
from tkinter import filedialog

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
try:
    options = {'title': sys.argv[2]}
    if sys.argv[1]:
        options['initialdir'] = sys.argv[1]
    if sys.argv[4] == "1":
        abs_path = filedialog.askdirectory(**options)
    else:
        abs_path = filedialog.askopenfilename(
            **options, filetypes=json.loads(sys.argv[3]))
    if abs_path:
        print(os.path.normpath(abs_path), end="")
finally:
    root.destroy()
'''
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, initial_dir, title,
             json.dumps(filetypes_list or []), "1" if directory else "0"],
            capture_output=True, text=True,
            check=False,
        )
        if result.returncode:
            _logger.error("File picker failed: %s", result.stderr.strip())
            return ""
        return result.stdout.strip()
    except Exception as e:
        _logger.error(f"Error launching file picker: {e}")
        return ""
