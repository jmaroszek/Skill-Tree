'use strict';

// The shell's decisions, kept apart from Electron so they can be tested:
// which server to start, how the window's title bar looks on each platform,
// which URLs may load in the window, and the macOS menu.

const path = require('path');

// Conda installs checked, in order, for a developer's `skill-tree` env.
const CONDA_ROOTS = ['anaconda3', 'miniconda3', 'miniforge3', 'mambaforge'];

// How to start the server. A packaged app runs the PyInstaller build that
// electron-builder put in resources/server. A developer's checkout runs
// app.py with SKILLTREE_PYTHON, else a conda env named skill-tree, else
// whatever is on PATH.
function serverCommand({ isPackaged, platform, resourcesPath, repo, env, exists, sandbox }) {
  const p = platform === 'win32' ? path.win32 : path.posix;
  if (isPackaged) {
    const dir = p.join(resourcesPath, 'server');
    const binary = platform === 'win32' ? 'skilltree-server.exe' : 'skilltree-server';
    // --sandbox is a developer's flag; a packaged app has one set of data.
    return { command: p.join(dir, binary), args: ['--desktop'], cwd: dir };
  }
  const args = ['app.py', '--desktop'];
  if (sandbox) args.push('--sandbox');
  let command = env.SKILLTREE_PYTHON;
  if (!command && platform === 'win32' && env.USERPROFILE) {
    command = CONDA_ROOTS
      .map(root => p.join(env.USERPROFILE, root, 'envs', 'skill-tree', 'pythonw.exe'))
      .find(candidate => exists(candidate));
  }
  if (!command) command = platform === 'win32' ? 'pythonw' : 'python3';
  return { command, args, cwd: repo };
}

// The OS draws the window buttons above the page, so a modal's backdrop can't
// dim them. The page reports when a modal is open (assets/window_chrome.js)
// and the shell repaints the overlay as the backdrop would: black at
// Bootstrap's backdrop opacity over the toolbar's colors.
const OVERLAY = { color: '#1a1d21', symbolColor: '#dee2e6', height: 40 };
const BACKDROP_OPACITY = 0.5;

function dimHex(hex) {
  const channels = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  return '#' + channels
    .map(c => Math.round(c * (1 - BACKDROP_OPACITY)).toString(16).padStart(2, '0'))
    .join('');
}

function titleBarOverlay(dimmed) {
  if (!dimmed) return { ...OVERLAY };
  return { ...OVERLAY, color: dimHex(OVERLAY.color), symbolColor: dimHex(OVERLAY.symbolColor) };
}

// The title bar. On Windows and macOS the app's toolbar is the title bar, with
// the OS's own window buttons drawn over it: on the right on Windows, as
// traffic lights on the left on macOS. titleBarOverlay exposes their area to
// CSS (env(titlebar-area-*)), which assets/theme.css pads around. Linux
// desktops draw their buttons too differently to overlay, so it keeps the
// native frame.
function windowChrome(platform) {
  if (platform === 'win32') {
    return { titleBarStyle: 'hidden', titleBarOverlay: titleBarOverlay(false) };
  }
  if (platform === 'darwin') {
    return { titleBarStyle: 'hiddenInset', titleBarOverlay: true };
  }
  return {};
}

function parse(url) {
  try {
    return new URL(url);
  } catch (err) {
    return null;
  }
}

// The window only ever shows the app itself.
function isAppUrl(url, port) {
  const parsed = parse(url);
  return !!(parsed && port && parsed.protocol === 'http:'
    && parsed.hostname === '127.0.0.1' && parsed.port === String(port));
}

// Links the page may hand to the system: web pages and email. Anything else
// (file:, custom schemes) goes through the server's resource opener, which
// asks first (resource_links.NeedsConfirmation).
function isExternalUrl(url) {
  const parsed = parse(url);
  return !!parsed && ['http:', 'https:', 'mailto:'].includes(parsed.protocol);
}

// macOS takes Cmd+C, Cmd+V and friends from the menu's roles; with no menu
// they don't work, even in text fields.
function macMenuTemplate(appName) {
  return [
    {
      label: appName,
      submenu: [
        { role: 'about' }, { type: 'separator' },
        { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' },
        { type: 'separator' }, { role: 'quit' },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' }, { role: 'redo' }, { type: 'separator' },
        { role: 'cut' }, { role: 'copy' }, { role: 'paste' },
        { role: 'pasteAndMatchStyle' }, { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' }, { role: 'toggleDevTools' }, { type: 'separator' },
        { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
        { type: 'separator' }, { role: 'togglefullscreen' },
      ],
    },
    { role: 'windowMenu' },
  ];
}

module.exports = { isAppUrl, isExternalUrl, macMenuTemplate, serverCommand, titleBarOverlay, windowChrome };
