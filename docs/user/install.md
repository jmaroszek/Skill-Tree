# Installing Skill Tree

Skill Tree runs on Windows, macOS and Linux. It works entirely on your computer:
no account, no sign-in, and your graph never leaves your machine
([privacy](privacy.md)).

Download the installer for your system from the
[latest release](https://github.com/jmaroszek/Skill-Tree/releases/latest). Each
release lists the files' SHA-256 checksums in `SHA256SUMS`, if you want to check
your download.

| System | File |
|---|---|
| Windows 10 or 11 (64-bit) | `Skill-Tree-Setup-<version>.exe` |
| macOS on Apple silicon (M1 and later) | `Skill-Tree-<version>-mac-arm64.dmg` |
| macOS on an Intel Mac | `Skill-Tree-<version>-mac-x64.dmg` |
| Linux: Ubuntu, Debian and relatives | `skill-tree_<version>_amd64.deb` |
| Linux: anything else | `Skill-Tree-<version>-linux-x86_64.AppImage` |

Not sure which Mac you have? Choose Apple menu → About This Mac. "Chip: Apple M…"
means Apple silicon; "Processor: Intel" means Intel.

## Windows

1. Run `Skill-Tree-Setup-<version>.exe`.
2. Choose where to install it, or keep the default. It installs for you alone and
   doesn't need an administrator. The desktop shortcut option is checked by
   default; clear it if you don't want an icon on your desktop.
3. Start Skill Tree from the Start menu or the desktop shortcut.

If Windows shows "Windows protected your PC", choose **More info**, then
**Run anyway**. The installer is signed, but Windows can still warn about a
publisher it hasn't seen much of yet.

## macOS

1. Open the `.dmg` and drag **Skill Tree** into **Applications**.
2. Open Skill Tree from Applications. macOS says it can't check the app for
   malicious software and won't open it. Choose **Done**.
3. Open **System Settings → Privacy & Security**. Near the bottom it says
   "Skill Tree was blocked to protect your Mac." Choose **Open Anyway**, then
   confirm with your password.

You only do this once. macOS asks because Skill Tree isn't yet signed with an
Apple Developer ID, which costs money every year; the app is the same either way.
On macOS 14 and earlier you can instead Control-click the app, choose **Open**,
and then **Open** again.

## Linux

**The .deb** (Ubuntu, Debian, Linux Mint, Pop!_OS and others):

```bash
sudo apt install ./skill-tree_<version>_amd64.deb
```

Skill Tree then appears among your applications. Remove it with
`sudo apt remove skill-tree`.

**The AppImage** (any distribution) is a single file that runs without
installing:

```bash
chmod +x Skill-Tree-<version>-linux-x86_64.AppImage
./Skill-Tree-<version>-linux-x86_64.AppImage
```

If it doesn't start:
- It needs FUSE 2: `sudo apt install libfuse2t64` on Ubuntu 24.04 and newer,
  `sudo apt install libfuse2` on Ubuntu 22.04.
- On Ubuntu 24.04 and newer, the system may stop the sandbox the app's window runs
  in, and the AppImage exits at once. Use the .deb instead, which comes with the
  permission it needs, or start the AppImage with `--no-sandbox`.

## Updates

Skill Tree checks for a new version once each time it starts, 15 seconds after
the window opens. On Windows and with the AppImage it downloads the new version in
the background and installs it the next time you quit. On macOS and with the .deb
it tells you a new version is out and offers the download page; install it over
the old one. Your graph stays where it is.

Settings → About has a switch to turn the check off, and a **Check now** button.
The check asks GitHub for the latest release and sends nothing about you or your
graph.

## Where your data lives

Your graph is a single file, `skilltree.db`, in the Data folder. Skill Tree backs
it up there too, in `Backups`, and keeps its logs beside it.

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\Skill Tree` |
| macOS | `~/Library/Application Support/Skill Tree` |
| Linux | `~/.local/share/Skill Tree` (or `$XDG_DATA_HOME/Skill Tree`) |

Settings → About opens the data and log folders for you.

**Backups.** Skill Tree copies the graph into `Data/Backups` once a day when it
starts, if anything changed. It keeps the last 30 of those, and makes one more
before every upgrade, restore or import. Settings → Data has **Back up now**,
**Restore…** from any of them, and exports you can keep anywhere.

**Moving to another computer.** In Settings → Data, choose **Export graph (.json)**.
Install Skill Tree on the other computer, and on its welcome screen choose
**Import a graph…**. The import keeps your resource links but clears their root
folders. Choose those folders again in Settings → Resources. Choose an extra
backup folder on this computer in Settings → Data if you want one.

## Uninstalling

Uninstalling removes the app but never your graph, so reinstalling picks up where
you left off.

- **Windows:** Settings → Apps → Installed apps → Skill Tree → Uninstall.
- **macOS:** drag Skill Tree from Applications to the Trash.
- **Linux:** `sudo apt remove skill-tree`, or delete the AppImage.

To remove your data as well, delete the data folder above. The app also keeps its
window settings and your update preference in a folder of its own: delete
`%APPDATA%\SkillTree` on Windows, `~/Library/Application Support/SkillTree` on
macOS, or `~/.config/SkillTree` on Linux.
