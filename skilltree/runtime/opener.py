"""Opening a node's links: files, folders and web pages, on Windows, macOS and
Linux.

A file inside an Obsidian vault opens in Obsidian. A link that could run a
program, or that hands itself to another app or computer, asks first: the
caller gets NeedsConfirmation and repeats the call with confirmed=True."""
import ntpath
import os
import re
import subprocess
import sys
import urllib.parse
import webbrowser


WEB_URL = re.compile(r"^https?://", re.IGNORECASE)


# Any "scheme:" prefix of two or more characters. One letter is a Windows
# drive, and a digit after the colon is a port (example.com:8080).
_ANY_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]+):(?!\d)", re.IGNORECASE)


# Links that open without asking. Any other scheme runs whatever app registered
# it, and some such handlers have been exploitable (ms-msdt on Windows).
SAFE_SCHEMES = {"http", "https", "mailto", "obsidian"}


_DOMAIN = re.compile(r"^(?:www\.)?[^/\\\s]+\.[a-z]{2,}(?:[/:?#]|$)", re.IGNORECASE)


_FILE_SUFFIXES = {"txt", "md", "pdf", "png", "jpg", "jpeg", "gif", "webp",
                  "svg", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv",
                  "json", "yaml", "yml", "html", "htm", "py", "js", "zip"}


# Files the system opens by running them: programs, scripts, installers, and
# shortcuts that can point at either. Windows themes and search connectors
# are here too: opening one can fetch from another computer with the user's
# sign-in. A link to one asks first, like a link that hands itself to another
# app. Opening a document or a folder doesn't ask.
RUNNABLE_SUFFIXES = frozenset({
    # Windows
    "exe", "com", "scr", "pif", "cpl", "msc", "msi", "msp", "mst", "msix",
    "msixbundle", "appx", "appxbundle", "appinstaller", "appref-ms",
    "application", "gadget", "bat", "cmd", "ps1", "psm1", "psd1", "ps1xml",
    "psc1", "vb", "vbs", "vbe", "js", "jse", "ws", "wsf", "wsc", "wsh", "hta",
    "reg", "inf", "scf", "lnk", "url", "chm", "settingcontent-ms", "library-ms",
    "searchconnector-ms", "theme", "themepack", "deskthemepack", "diagcab", "xll",
    # macOS
    "app", "command", "tool", "terminal", "workflow", "action", "pkg", "mpkg",
    # Linux
    "desktop", "sh", "bash", "zsh", "csh", "ksh", "run", "appimage", "deb", "rpm",
    # Any system with the interpreter installed
    "py", "pyw", "pyz", "jar", "jnlp", "pl", "rb",
})


# What Obsidian itself opens: notes, canvases, bases, PDFs, and the image,
# audio and video formats it embeds. A file of one of these types inside a
# vault opens in Obsidian; anything else goes to the default app.
OBSIDIAN_SUFFIXES = {"md", "canvas", "base", "pdf",
                     "png", "jpg", "jpeg", "gif", "bmp", "svg", "webp", "avif",
                     "mp3", "wav", "m4a", "ogg", "flac", "3gp", "webm",
                     "mp4", "ogv", "mov", "mkv"}


def in_obsidian_vault(path):
    """True when a folder above `path` is a vault, which holds `.obsidian`."""
    folder = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isdir(os.path.join(folder, ".obsidian")):
            return True
        parent = os.path.dirname(folder)
        if parent == folder:
            return False
        folder = parent


def obsidian_file(path):
    """True when Obsidian can open `path`: an existing file of a type it
    opens, inside a vault."""
    name = os.path.basename(path)
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return (suffix in OBSIDIAN_SUFFIXES and os.path.isfile(path)
            and in_obsidian_vault(path))


class NeedsConfirmation(Exception):
    """This link starts another app or reaches another computer. The message
    is the question to put to the user; open_resource(confirmed=True) goes
    ahead once they agree."""


def absolute_path(value):
    return os.path.isabs(value) or ntpath.isabs(value)


def link_scheme(value):
    """The link's scheme, lowercased, or None for a path (C: is a drive)."""
    match = _ANY_SCHEME.match((value or "").strip())
    return match.group(1).lower() if match else None


def network_host(path):
    """The computer a network path names (\\\\host\\share, //host/share), or None."""
    text = str(path).replace("/", "\\")
    if text[:8].upper() == "\\\\?\\UNC\\":
        text = "\\\\" + text[8:]
    elif text.startswith(("\\\\?\\", "\\\\.\\")):   # local device paths
        return None
    if not text.startswith("\\\\"):
        return None
    return text[2:].split("\\", 1)[0] or None


def _ask_before_network(path, confirmed):
    """Windows signs in to the computer a network path names, handing it the
    user's password hash, as soon as anything looks at the path. So ask first."""
    host = network_host(path)
    if host and not confirmed:
        raise NeedsConfirmation(
            f"This link is a file on another computer, {host}. Opening it "
            "connects to that computer with your sign-in. Open it?")


def runnable_suffix(path):
    """The suffix that makes opening ``path`` run a program, or None.

    Windows drops trailing dots and spaces from a file name when it opens it,
    so ``setup.exe.`` runs ``setup.exe``; the check sees the same name.
    """
    name = ntpath.basename(os.fspath(path).replace("/", "\\")).rstrip(". ")
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return suffix if suffix in RUNNABLE_SUFFIXES else None


def _ask_before_running(path, confirmed):
    """Opening a program, script or shortcut runs it, so ask first."""
    suffix = runnable_suffix(path)
    if suffix and not confirmed:
        raise NeedsConfirmation(
            f"This link is a .{suffix} file. Opening it can run a program on "
            "your computer. Only open it if you trust where it came from. "
            "Open it?")


def resolve_target(value, section, confirmed=False):
    """Return ('web'|'path'|'uri', target); never mistake a drive for a URI.

    Raises NeedsConfirmation, unless ``confirmed``, for a scheme outside
    SAFE_SCHEMES or a path on another computer, before touching the
    filesystem, and for a local file that opening would run as a program.
    """
    value = (value or "").strip()
    if not value:
        raise ValueError("No file path or URL set.")
    if WEB_URL.match(value):
        return "web", value
    scheme = link_scheme(value)
    if scheme:
        if scheme not in SAFE_SCHEMES and not confirmed:
            raise NeedsConfirmation(
                f"This is a {scheme}: link, which opens in whatever app handles "
                f"{scheme}: links. Only open it if you trust where it came from. "
                "Open it?")
        return "uri", value
    _ask_before_network(value, confirmed)
    root = (section.get("root_path") or "").strip()
    if root and not absolute_path(value):
        _ask_before_network(root, confirmed)
    if absolute_path(value) or os.path.exists(value):
        path = value
    elif root:
        path = os.path.join(root, value.replace("/", os.sep))
    else:
        path = None
    if path is not None:
        # A vault holds `.obsidian`, so a vault file opens in Obsidian when
        # it is a type Obsidian opens. Without Obsidian there is no vault.
        if obsidian_file(path):
            full = os.path.normpath(os.path.abspath(path))
            return "uri", "obsidian://open?path=" + urllib.parse.quote(full, safe="")
        _ask_before_running(path, confirmed)
        return "path", path
    suffix = value.rsplit('.', 1)[-1].lower() if '.' in value else ''
    if _DOMAIN.match(value) and suffix not in _FILE_SUFFIXES:
        return "web", "https://" + value
    raise ValueError("Use an absolute file path or set a root folder for relative paths.")


def _launch_env():
    """The environment for starting the user's own apps, or None to inherit.

    A frozen (PyInstaller) build on Linux points LD_LIBRARY_PATH into its
    bundle, and a system program started with it, such as xdg-open or the
    browser it opens, can load the bundle's libraries and fail. PyInstaller
    keeps the original value in LD_LIBRARY_PATH_ORIG.
    """
    if not getattr(sys, "frozen", False):
        return None
    env = dict(os.environ)
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is None:
        env.pop("LD_LIBRARY_PATH", None)
    else:
        env["LD_LIBRARY_PATH"] = original
    return env


def _frozen_linux():
    return getattr(sys, "frozen", False) and sys.platform.startswith("linux")


def open_path(target):
    """Ask the OS to open a file, folder, or registered custom URI."""
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target], shell=False, env=_launch_env())
    else:
        subprocess.Popen(["xdg-open", target], shell=False, env=_launch_env())


def open_resource(value, section, confirmed=False):
    """Open a saved link. NeedsConfirmation first when it needs a yes."""
    kind, target = resolve_target(value, section, confirmed)
    if kind == "web" and _frozen_linux():
        # webbrowser can't be given the clean environment open_path uses.
        open_path(target)
    elif kind == "web":
        if not webbrowser.open_new_tab(target):
            raise OSError("No browser accepted the URL.")
    else:
        if kind == "path":
            if not absolute_path(target):
                target = os.path.abspath(target)
            if not os.path.exists(target):
                raise FileNotFoundError(target)
        open_path(target)
