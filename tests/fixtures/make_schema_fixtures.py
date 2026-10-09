"""Build tests/fixtures/schema_vN.db: a small graph saved by each old version.

    python tests/fixtures/make_schema_fixtures.py

For each schema version, this exports the repository as it was at that
version (git archive), and uses *that version's own code* to create a
database and fill it: nodes of each type, Needs and Helps edges, aliases,
a Done node, a Now node, an event with a sleeping node, priority goals, and
the resource links older versions kept in Nodes columns. What each version
lacks is skipped. test_migration_fixtures.py then opens every file with the
current code.

Run it again only to add a version; the files are committed.
"""
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

# The commit each schema version was introduced in (git log -G"^SCHEMA_VERSION = "
# -- database.py). v4 is the baseline, just before v5.
VERSIONS = {
    4: "22cf9d3^",
    5: "22cf9d3",
    6: "f6e0f0f",
    7: "6313c66",
    8: "c41e543",
    9: "5157ca3",
    10: "50d10be",
    11: "0f523c1",
    12: "99dac97",
}

FILL = r'''
import sys
sys.path.insert(0, ".")
import database
database.get_db_path = lambda: sys.argv[1]
database.init_db()
from graph_manager import GraphManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from config import ConfigManager

def node(name, node_type="Learn", **extra):
    fields = dict(name=name, type=node_type, description=f"About {name}.", value=7,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=6, difficulty=4,
                  status="Open", context="Mind")
    known = Node.__dataclass_fields__
    fields.update({k: v for k, v in extra.items() if k in known})
    return Node(**fields)

import sqlite3
_sections = {row[0] for row in sqlite3.connect(sys.argv[1]).execute("SELECT id FROM ResourceSections")}
SECTION = "website" if "website" in _sections else "links"  # a new database starts with "links"

m = GraphManager()
m.add_node(node("Sleep", "Goal", context="Body"))
# Before v11, links lived in Nodes columns; from v11, in named sections, a
# new database starting with Obsidian, Google Drive and Website.
m.add_node(node("Sleep hygiene", context="Body", subcontext="Rhythms",
                obsidian_path="Notes/Sleep hygiene.md", website="https://example.com/sleep",
                resource_links={SECTION: ["https://example.com/sleep"]}))
m.add_node(node("Blackout curtains", "Action", context="Body",
                google_drive_path="Shopping/curtains.pdf"))
m.add_node(node("Why We Sleep", "Resource", context="Body"))
m.add_node(node("Eight hours", "Milestone", context="Body"))
m.add_node(node("Stoicism", context="Mind"))
m.add_node(node("A|B test", "Action", context="Life"))
m.add_edge("Sleep hygiene", "Sleep", EDGE_NEEDS_HARD)
m.add_edge("Blackout curtains", "Sleep", EDGE_NEEDS_SOFT)
m.add_edge("Why We Sleep", "Sleep hygiene", EDGE_NEEDS_HARD)
m.add_edge("Stoicism", "Sleep hygiene", EDGE_HELPS)
done = m.get_node("Why We Sleep")
done.status = "Done"
m.update_node(done)
now = m.get_node("Blackout curtains")
now.now = 1
m.update_node(now)
try:
    m.set_aliases("Sleep hygiene", ["Sleep habits"])
except Exception:
    pass
try:
    ConfigManager.set_priority_goals(["Sleep"])
except Exception:
    pass
try:
    from event_manager import EventManager
    from models import Event
    events = EventManager()
    if "trigger_nodes" in Event.__dataclass_fields__:
        events.add_event(Event(name="Winter", trigger_nodes=["Stoicism"]))
    else:  # before v5, one trigger node
        events.add_event(Event(name="Winter", trigger_node="Stoicism"))
    events.add_node_to_event("Winter", "A|B test")
except Exception as exc:
    print("no events:", exc)
print("filled", sys.argv[1])
'''


def build(version, commit):
    target = OUT / f"schema_v{version}.db"
    if target.exists():
        target.unlink()
    with tempfile.TemporaryDirectory() as tree:
        archive = subprocess.run(["git", "archive", "--format=tar", commit],
                                 cwd=ROOT, check=True, capture_output=True).stdout
        tar_path = Path(tree) / "tree.tar"
        tar_path.write_bytes(archive)
        with tarfile.open(tar_path) as tar:
            tar.extractall(tree, filter="data")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run([sys.executable, "-c", FILL, str(target)], cwd=tree, env=env,
                       check=True)
    import sqlite3
    conn = sqlite3.connect(target)
    stamped = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.execute("VACUUM")
    conn.close()
    assert stamped == version, f"{commit} stamped v{stamped}, expected v{version}"


if __name__ == "__main__":
    for version, commit in VERSIONS.items():
        build(version, commit)
