# Setup — the desktop shell, for developers

People who just want to use Skill Tree install it from a release (the Windows
installer, the macOS dmg, or the Linux AppImage or deb). This file is for
running the desktop shell from a checkout. The shell (`electron/`) starts the
Python/Dash server and shows it in a native window. The Python app's own setup
is in [`docs/setup.md`](docs/setup.md).

## Prerequisites

- The `skill-tree` conda environment (`conda env create -f environment.yml`), which
  includes **Node.js**. Any Python 3.13 with `requirements.txt` installed, plus
  Node.js 22, also works.

## Install the shell's packages

```
cd electron
npm ci
```

On Windows, `.\setup.ps1` does the same, and falls back to unpacking Electron
itself if its download left `node_modules/electron/dist` without `electron.exe`.
Electron's own install used to hit that until 42.4.0 fixed its unzip step, so the
fallback is rarely needed now.

## Run it

```
cd electron
npm start               # your real data
npm run start:sandbox   # the sandbox database
```

- **Finding Python.** The shell (`electron/shell.js`) looks for the interpreter
  in this order:
  1. `SKILLTREE_PYTHON`, if set.
  2. A conda env named `skill-tree` under `%USERPROFILE%` (anaconda3, miniconda3,
     miniforge3 or mambaforge).
  3. `pythonw` (Windows) or `python3` on `PATH`.
- **Port.** The server takes a free port and says which in its `SKILLTREE_READY`
  line, so nothing else on the machine can collide with it.
- **Quitting.** Closing the window stops the server.
- **Side by side.** Production and sandbox use separate Electron profiles, so
  they can run together.
- **Desktop shortcuts.** To launch from an icon, point a shortcut at a script
  that runs `npm start` (or `npm run start:sandbox`) in `electron/`.

A packaged build runs its bundled server instead (`packaging/skilltree-server.spec`)
and ignores `--sandbox`. To build the installers, see
[`docs/setup.md`](docs/setup.md#5-build-the-desktop-installers-optional).
