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

pip install -r requirements.txt
```

`requirements.txt` mirrors `environment.yml`. If you bump a dependency, update both files.

## 3. Run the app

Launch in **sandbox mode** first — it uses a separate database (`%LOCALAPPDATA%\Skill Tree\Data\sandbox_skilltree.db` on Windows) so you can experiment without touching real data.

```bash
python app.py --sandbox --port 8051
```

The app opens automatically at <http://127.0.0.1:8051>. The SQLite database is created automatically on first launch (an empty graph), so there's no migration or seed step.

To run against the primary database instead, omit `--sandbox` (defaults to port 8050):

```bash
python app.py
```

Sandbox (8051) and production (8050) use distinct ports and databases, so both can run side by side.

## 4. Run the tests (optional)

```bash
pytest
```

Tests run against a temporary per-test database and never touch your sandbox or production data.

## Notes

- **Database files** live in `%LOCALAPPDATA%\Skill Tree\Data\` on Windows, `~/Library/Application Support/Skill Tree/Data/` on macOS, and `$XDG_DATA_HOME/Skill Tree/Data/` (or `~/.local/share/Skill Tree/Data/`) on Linux. They are created on demand: `skilltree.db` (production) and `sandbox_skilltree.db` (sandbox).
- **Logs** use the matching platform app-data `Logs` folder: `app.log` (production) and `sandbox_app.log` (sandbox), rotating at 5 MB. Backup and optional scoring-performance logs live there too.
- Settings → Integrations has up to five named Resource sections. General sections can open URLs or any local file type; optional roots make files beneath them portable as relative paths. Obsidian uses an `obsidian://` URI and is optional.
