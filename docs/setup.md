# Setup

How to clone Skill Tree and get it running locally. The app is a Dash web app with a Python backend and SQLite storage. There is no build step and no external services to configure.

## Prerequisites

- **Python 3.10** — the pinned environment targets 3.10. Newer versions usually work, but 3.10 is what the dependency set is tested against.
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

The `environment.yml` pins exact versions and Python 3.10, so this reproduces the tested environment most reliably.

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

Launch in **sandbox mode** first — it uses a separate database (`data/sandbox_skilltree.db`) so you can experiment without touching real data.

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

- **Database files** live in `data/` and are created on demand: `skilltree.db` (production) and `sandbox_skilltree.db` (sandbox). Neither is committed to the repo, so a fresh clone starts with an empty graph.
- **Logs** are written to `data/app.log` (production) and `data/sandbox_app.log` (sandbox), rotating at 5 MB.
- The "Open in Obsidian" feature shells out to an `obsidian://` URI and is optional — the app runs fine without Obsidian installed.
