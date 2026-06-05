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

### Known quirk: Electron's unzip step

In this environment, Electron's npm post-install **fails to extract its binary**.
`node_modules/electron/dist/` ends up with only a `locales/` folder — no
`electron.exe` — even though the download itself succeeds and passes its
checksum. The cause is Electron's bundled `extract-zip` step, not the download
and not antivirus: `Expand-Archive` extracts the very same cached zip perfectly.

`setup.ps1` works around it. If `electron.exe` is missing after `npm install`, it
extracts the cached (or freshly downloaded) zip with `Expand-Archive` and writes
`node_modules/electron/path.txt`. So run `setup.ps1` — a bare `npm install` is
not enough here on its own.

## Launching

- Desktop icon → `Code\Terminal\Batch\skill_tree.bat` → Electron (production, port 8050).
- `Code\Terminal\Batch\skill_tree_sandbox.bat` → Electron against the sandbox DB (port 8051).

Both spawn the env's `pythonw` server under the hood; closing the window stops it.
Production and sandbox use separate Electron profiles, so they can run side by side.
