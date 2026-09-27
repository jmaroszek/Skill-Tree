# Troubleshooting

If something here doesn't help, use **Report a problem on GitHub** in Settings →
About. It fills in the details we need; the logs (Settings → About → **Open logs
folder**) help too.

## When Skill Tree won't start

It says why in a message. Your graph is never changed when it refuses to start.

**"Your Skill Tree data file is damaged."** Skill Tree offers to put back the
newest backup that opens cleanly, and says when it was taken. Changes made after
that are lost; the damaged file is kept beside your data, renamed, in case you
want it. If there is no good backup, nothing is changed: report the problem, and
keep the file.

**"Your Skill Tree data file is in use by another program."** A backup, sync or
antivirus program, or a database viewer, has the file open. Close it, or wait for
it to finish, and start Skill Tree again. If a sync service (OneDrive, Dropbox,
iCloud) is syncing the data folder, pause it while Skill Tree runs.

**"Your Skill Tree data was saved by a newer version of Skill Tree."** You opened
your graph with a newer Skill Tree before. Install that version or a later one
from the [releases page](https://github.com/jmaroszek/Skill-Tree/releases).

**"Skill Tree can't write to its data folder."** The disk is full, or the folder
has become read-only. Free some space, or check the folder's permissions
([where it is](install.md#where-your-data-lives)).

**"Skill Tree's server didn't start in time."** Usually an antivirus program
scanning the app the first time it runs. Start Skill Tree again. If it keeps
happening, let your antivirus trust the Skill Tree folder, and report it.

**"Skill Tree is already running, but it isn't answering."** An earlier copy is
stuck. Quit it (Task Manager on Windows, Activity Monitor on macOS), or restart the
computer.

On macOS, if the app won't open at all the first time, see
[installing on macOS](install.md#macos). On Linux, see
[the AppImage notes](install.md#linux).

## While you use it

**The window went blank, or says it stopped unexpectedly.** Choose **Reload**.
Your graph is saved as you work, so nothing is lost.

**I changed or deleted something by mistake.** Settings → Data → **Restore…** puts
back an earlier state. Skill Tree backs up once a day when it starts, and before
every upgrade, restore and import; **Back up now** makes one on the spot. A restore
makes a backup of the current state first, so it can be undone the same way.

**A node won't let me mark it Done.** It needs something first: a node is Done
only once every hard prerequisite leading to it is. Finish those, or remove the
requirement.

**Un-marking a node asks me first.** Nodes after it that are already Done would
become Blocked again, since they need it. The question lists them.

**Large graphs.** Past about 600 nodes on the canvas, the layout switches to a
faster mode, so adding or removing nodes doesn't stall the window. Hiding Done
nodes, or filtering by context, keeps the canvas quick at any size.

## Starting over

Quit Skill Tree and move or delete its data folder. The next start is a first
start, with the welcome, and an empty graph.
