# Changelog

What changes in each release, newest first. Download releases from the
[releases page](https://github.com/jmaroszek/Skill-Tree/releases).

## Unreleased

- Put the toolbar icons in Filter, Reflection, Settings, Help order.
- Tidied the Settings window. Each resource card has a numbered heading. The Data
  and About tabs no longer print folder paths; their Open buttons remain. The
  diagnostics that "Report a problem" copies sit in their own box. Backups made
  with Back up now are labelled "manual".
- A failed update check now says so in one line instead of showing the raw error.
- The Windows installer now asks whether to add a desktop shortcut (checked by
  default) and launches the installed app directly from its Finish page.
- Skill Tree takes less space. On Windows it needs about 427 MB instead of
  482 MB, and the installer is about 12 MB smaller. On macOS and Linux it is
  about 30 MB smaller. Nothing about how it works has changed.

## 1.0.0 (not yet released)

The first public release: Skill Tree as an app anyone can install.

### Install and run
- Installers for Windows (64-bit), macOS (Apple silicon and Intel) and Linux
  (.deb and AppImage), each with its own Python inside: nothing else to install.
  See [installing](docs/user/install.md).
- Works offline. Its fonts, icons and scripts ship with the app.
- Checks for updates once per launch. It installs them itself on Windows and with
  the AppImage, and offers the download on macOS and with the .deb. You can turn
  the check off in Settings → About.
- A first-launch welcome, and a Getting Started checklist on Home that ticks
  itself off as you go.
- Settings → About: the version, the data and log folders, diagnostics you can
  copy, a link to report a problem, update controls, and third-party notices.
- Help on the toolbar.

### Your data
- Automatic backups: once a day when your graph has changed, and before every
  upgrade, restore and import. Settings → Data has Back up now and Restore.
- Export your graph to a file and import it on another computer, or keep a copy
  of the database file itself.
- A damaged data file no longer just stops the app. Skill Tree offers the newest
  backup that opens cleanly and keeps the damaged file.
- A data file saved by a newer version, or one another program has open, is
  refused with a clear reason and left untouched.
- Only one Skill Tree opens a given graph at a time. A second launch brings up the
  first one.
- The app's server answers only its own window, on your computer alone.

### Fixes
- A new node given an existing node's name no longer overwrites that node. Names
  are unique ignoring case, and renaming onto another node's name is refused
  with a reason.
- Names containing `|` no longer make actions affect a different node.
- Un-marking Done in the editor now asks first when it would re-block finished
  work after it, as the node menu does.
- The editor now shows a status changed from the node menu, so a later save can't
  write the old status back.
- A Blocked node can't be marked Done. Before, the next launch quietly undid
  that.
- Multi-node actions (Done on a selection, group delete, Settings save,
  context migration) happen completely or not at all.
- Large graphs lay out about three times faster, so adding or removing a node
  in a graph of several hundred no longer stalls the window.
- Date-triggered events fire on time while the app sits open.
