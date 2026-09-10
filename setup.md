# Setup — Skill Tree desktop app

Skill Tree runs as a native desktop app through an Electron shell (`electron/`)
that spawns the Python/Dash server and hosts it in a window. This file covers
getting that shell working. The Python app's own dependencies live in
`environment.yml` / `requirements.txt`.

## Prerequisites

- The `skill-tree` conda environment (`conda env create -f environment.yml`).
  It now includes **Node.js**, which the Electron shell needs.

## Install the desktop shell

From an activated `skill-tree` env:

```
cd "Skill Tree\electron"
.\setup.ps1
```

`setup.ps1` runs `npm install` and makes sure the Electron binary is in place.

### Fixed: Electron's unzip step

Electron's npm post-install used to **fail to extract its binary** here.
`node_modules/electron/dist/` ended up with only a `locales/` folder — no
`electron.exe` — even though the download itself succeeded and passed its
checksum. The cause was the `extract-zip` package Electron bundled for that
step, not the download and not antivirus.

Electron 42.4.0 replaced `extract-zip` with its own maintained
`@electron-internal/extract-zip` fork, and the extraction now works. A bare
`npm install` is enough. The same swap closed CVE-2026-56876, a symlink path
traversal in `extract-zip` that had no fix of its own.

`setup.ps1` keeps its `Expand-Archive` fallback as a safety net. It is a no-op
whenever the binary is already in place, so running the script is still the
recommended way to install.

## Launching

- Desktop icon → `Code\Terminal\Batch\skill_tree.bat` → Electron (production, port 8050).
- `Code\Terminal\Batch\skill_tree_sandbox.bat` → Electron against the sandbox DB (port 8051).

Both spawn the env's `pythonw` server under the hood; closing the window stops it.
Production and sandbox use separate Electron profiles, so they can run side by side.
