# Changelog

What changes in each release, newest first. Download releases from the
[releases page](https://github.com/jmaroszek/Skill-Tree/releases).

## Unreleased

- The local server keeps its launch key in the tab instead of a cookie shared
  with other services on the same computer. Reopen the app's link after a restart.
- Imported exports can no longer redirect later backups to another folder;
  the backup folder already chosen on this computer stays in place.
- Import keeps resource links but clears their device-specific root folders;
  choose each folder on this computer after import. Browse still starts at a
  locally saved root, while network roots cannot start the dialog silently.
- The dividers that resize the Details and Events panels work as soon as the tab
  appears, and the Details divider stays under the pointer as you drag it.
- Selecting a node on the Nodes tab is faster on large graphs. It no longer
  works out the contents of a panel the tab stopped showing long ago.
- Web pages served from your own computer, such as another app's local server,
  can no longer send changes to Skill Tree.
- A save that completes a node always fires the events waiting on it.
- A node that is already Done when its event fires stays out of Now, and Add to
  Event no longer lists finished nodes.
- An event fires once. Pressing Trigger on an event that had already fired, in a
  window that hadn't caught up, now says so instead of pushing its delayed nodes'
  wake dates later.
- Importing a graph checks it first. A file the app couldn't have built itself,
  such as one whose prerequisites loop or whose edges name missing nodes, is
  refused with the problem named, and nothing changes.
- A link to a program, script, installer or shortcut (an `.exe`, `.bat` or `.lnk`
  file, for example) now asks before it opens. Opening one runs it, and links can
  arrive in someone else's export.
- A new app icon: a tree whose canopy is a cluster of connected nodes, replacing
  the pixel-art tree.
- Put the toolbar icons in Filter, Reflection, Settings, Help order.
- Tidied the Settings window. Each resource card has a numbered heading. The Data
  and About tabs no longer print folder paths; their Open buttons remain. The
  diagnostics that "Report a problem" copies sit in their own box. Backups made
  with Back up now are labelled "manual".
- A failed update check now says so in one line instead of showing the raw error.
- The Windows installer now asks whether to add a desktop shortcut (checked by
  default) and launches the installed app directly from its Finish page.
- Skill Tree takes less space. On Windows it needs about 380 MB instead of
  482 MB, and the installer is 116 MB instead of 136 MB. macOS and Linux get the
  same trims.
- Chromium's own built-in text is now English only, like the rest of the app. On
  a Windows set to another language, date fields, decimal points and spellcheck
  now follow US English.

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
