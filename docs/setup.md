# Setup

How to clone Skill Tree and get it running locally. The app is a Dash web app with a Python backend and SQLite storage. There is no build step and no external services to configure.

## Prerequisites

- **Python 3.13** — the pinned environment targets 3.13. This is the version the dependency set is tested against and the app runs on.
- **git**
- Either **conda/miniconda** (recommended — matches the tested environment exactly) or plain **pip + venv**.

## 1. Clone the repo

```bash
git clone https://github.com/jmaroszek/Skill-Tree.git
cd Skill-Tree
```

## 2. Install dependencies

Pick **one** of the two options.

### Option A — conda (recommended)

The `environment.yml` pins exact versions and Python 3.13, so this reproduces the tested environment most reliably.

```bash
conda env create -f environment.yml
conda activate skill-tree
```

### Option B — pip + venv

```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs the runtime set in `requirements.txt` plus the test tools. Both mirror `environment.yml`. If you bump a dependency, update all three files.

## 3. Run the app

Launch in **sandbox mode** first — it uses a separate database (`%LOCALAPPDATA%\Skill Tree\Data\sandbox_skilltree.db` on Windows) so you can experiment without touching real data.

```bash
python app.py --sandbox --dev
```

A browser tab opens on the app. The SQLite database is created automatically on first launch (an empty graph), so there's no migration or seed step. `--dev` adds Flask's debugger and hot reload: edits to Python, CSS and JS apply without a restart. Leave it off to run the app the way users get it.

To run against the primary database instead, omit `--sandbox`:

```bash
python app.py
```

- **Ports.** Sandbox uses 8051 and production 8050, so both can run side by side. `--port N` picks another, and if the port is taken by something else the app moves to a free one. The desktop shell always takes a free port.
- **The access link.** The server only answers the window or tab it opened: the first URL carries a token, which that tab keeps in origin-scoped session storage for later requests. After a restart, use the new tab it opens. With `--no-browser` it prints the link instead. The link is also in `<Data>/sandbox_skilltree.instance.json` (or `skilltree.instance.json`) while it runs.
- **Imported resource roots.** Import keeps the links in each resource section but clears its root folder. Choose the folder on this computer in Settings → Resources before opening relative file links.
- **One server per database.** A second launch opens the running one instead of starting another.
- **A throwaway data folder.** Set `SKILLTREE_HOME` to an absolute folder, and Data and Logs go there instead of the per-user folder.

## 4. Run the tests (optional)

```bash
pytest
python -m ruff check .
```

Tests run against a temporary per-test database and never write to your sandbox or production data. Two scoring tests read a consistent copy of those databases when they exist, and skip when they don't. A few asset tests drive the JavaScript under Node.js and skip when `node` isn't on your `PATH`. CI (`.github/workflows/ci.yml`) runs the whole suite, with Node, on Windows, macOS and Linux.

The linter checks for unused imports and variables, undefined names, and shadowed imports. `ruff.toml` names its rules, and CI runs it too.

The browser journeys in `tests/e2e` start a real server and drive it in Chromium, the way a new user would. They skip unless Playwright is installed:

```bash
pip install -r requirements-e2e.txt
python -m playwright install chromium
pytest tests/e2e
```

Each journey gets its own server on a free port and a throwaway data folder.

## 5. Build the desktop installers (optional)

The desktop app is the Electron shell plus a PyInstaller build of the server.
Each platform builds its own:

```bash
pip install -r requirements-build.txt
(cd electron && npm ci)
python packaging/third_party_notices.py                              # -> THIRD_PARTY_NOTICES.txt
python -m PyInstaller packaging/skilltree-server.spec --noconfirm   # -> dist/skilltree-server/
python packaging/smoke_test.py dist/skilltree-server/skilltree-server
cd electron && npm run dist                                          # -> electron/dist/
```

- `third_party_notices.py` lists what the build ships that others wrote, with their
  licenses: the server's Python packages, the shell's npm packages and the vendored
  fonts, icons and scripts. Each platform writes its own, since some Python packages
  are platform-specific. The server's build bundles it and Settings → About opens it.

- The spec leaves out files the server's packages ship but never serve: Dash's and
  Dash Cytoscape's development builds, and plotly's Jupyter widget
  (`packaging/unused_files.py`). A test checks the list against every file the app
  serves.
- `npm run dist` makes the installer for the machine it runs on: an NSIS installer on
  Windows, a dmg and zip on macOS, and an AppImage and deb on Linux
  (`electron/electron-builder.yml`). It keeps only Chromium's US English language
  pack, and on Windows leaves out Chromium's WebGPU shader compiler, which Skill
  Tree doesn't use (`electron/build/unused-files.js`).
- CI builds and smoke-tests the server on every push.
- Signed Windows tag builds use the GitHub `release-signing` environment. It
  requires a reviewer, permits only `v*` tags, and the `protect-release-tags`
  ruleset limits release-tag creation, deletion and retargeting. Put
  `WINDOWS_SIGN_COMMAND` and optional `WINDOWS_SIGN_SETUP` secrets **only in that
  environment**. Remove any repository or organization copies that branch
  workflows could read. Branch trial builds use the separate `trial-build`
  environment, which has no signing secrets. Recreate these protections if the
  release workflow moves to another repository.
- `packaging/app_journey.py` drives a built app the way a new user would: the window,
  the welcome, a node saved, quitting, and a second start. It uses a throwaway data
  folder, so it never touches yours. The release workflow runs it on every platform:

  ```bash
  pip install -r requirements-e2e.txt
  python packaging/app_journey.py "electron/dist/win-unpacked/Skill Tree.exe"     # Windows
  python packaging/app_journey.py "electron/dist/mac-arm64/Skill Tree.app/Contents/MacOS/Skill Tree"
  python packaging/app_journey.py electron/dist/linux-unpacked/skill-tree --headless  # needs xvfb-run
  ```

## Notes

- **Database files** live in `%LOCALAPPDATA%\Skill Tree\Data\` on Windows, `~/Library/Application Support/Skill Tree/Data/` on macOS, and `$XDG_DATA_HOME/Skill Tree/Data/` (or `~/.local/share/Skill Tree/Data/`) on Linux. They are created on demand: `skilltree.db` (production) and `sandbox_skilltree.db` (sandbox).
- **Logs** use the matching platform app-data `Logs` folder: `app.log` (production) and `sandbox_app.log` (sandbox), rotating at 5 MB. Backup and optional scoring-performance logs live there too.
- Settings → Resources has up to five named Resource sections. Each opens URLs and any local file type; an optional root folder makes files beneath it portable as relative paths. A section with Open in Obsidian sends its notes to Obsidian through an `obsidian://` URI instead of the default app.
