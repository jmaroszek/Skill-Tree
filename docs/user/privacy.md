# Privacy

Skill Tree keeps everything on your computer. There is no account, no sign-in, no
cloud copy, no analytics and no crash reporting. Nobody, including the people who
make Skill Tree, can see your graph unless you send it to them.

## What stays on your computer

Your graph, its backups, your settings and the logs are files in your data folder
([where](install.md#where-your-data-lives)). The app is a small web server that
only your own computer can reach: it listens on 127.0.0.1, and it answers only the
window it opened, which holds a secret that changes every launch. Its fonts, icons
and scripts ship inside the app, so drawing the page needs no internet at all.

## When Skill Tree uses the internet

Only in these cases, and never with anything from your graph:

- **Checking for updates** (the desktop app). Once each time it starts, Skill Tree
  asks GitHub, where its releases are published, whether there is a newer
  version. On Windows and with the Linux AppImage, a new version is then
  downloaded from GitHub. Like any web request, this tells GitHub your IP address
  and that some copy of Skill Tree asked. Turn it off in Settings → About; the
  **Check now** button there asks once, when you press it.
- **Report a problem** (Settings → About) opens GitHub's issue form in your
  browser, with diagnostics filled in: the versions of Skill Tree and your system,
  where its files are (your home folder shows as `~`), and how many nodes, edges
  and events your graph has, never their names. Nothing is sent until you read the
  form and submit it yourself.
- **Help** opens this project's documentation on GitHub, in your browser.
- **Links you added to your nodes** open in your browser, or your other apps, when
  you click them. A link asks first when opening it would run a program, hand
  itself to an unfamiliar app, or reach another computer.

## Removing your data

Uninstalling leaves your graph in place, so a reinstall picks up where you left
off. To remove it, delete the data folder
([how](install.md#uninstalling)).
