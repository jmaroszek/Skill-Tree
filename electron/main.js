'use strict';

// Electron desktop shell for Skill Tree.
//
// Responsibilities:
//   1. Spawn the existing Dash/Flask app as a local server (pythonw, no console).
//   2. Wait for it to answer on /_server_boot_id, then open a native window at it.
//   3. Own the lifecycle: closing the window kills the Python server.
//
// The Python app is unchanged except for a --no-browser flag (so it serves
// without opening a browser tab, since we load it ourselves).

const { app, BrowserWindow, Menu } = require('electron');
const { spawn } = require('child_process');
const treeKill = require('tree-kill');
const http = require('http');
const path = require('path');

const SANDBOX = process.argv.includes('--sandbox');
const PORT = SANDBOX ? 8051 : 8050;

// The Skill Tree conda environment's windowless interpreter.
const PYTHONW = 'C:\\Users\\jonah\\anaconda3\\envs\\skill-tree\\pythonw.exe';
// electron/ lives inside the repo, so the app root is one level up.
const REPO = path.resolve(__dirname, '..');
const ICON = path.join(REPO, 'assets', 'skill_tree.ico');

let pyProc = null;
let mainWindow = null;

app.setAppUserModelId('com.skilltree.app');
// Separate Electron profile per environment so a sandbox window and a
// production window never share state or fight over the single-instance lock.
app.setPath('userData', path.join(app.getPath('appData'),
  SANDBOX ? 'SkillTree-Sandbox' : 'SkillTree'));

function startServer() {
  const args = ['app.py', '--port', String(PORT), '--no-browser'];
  if (SANDBOX) args.push('--sandbox');
  pyProc = spawn(PYTHONW, args, { cwd: REPO, windowsHide: true });
  pyProc.stdout.on('data', d => process.stdout.write(`[py] ${d}`));
  pyProc.stderr.on('data', d => process.stderr.write(`[py] ${d}`));
  pyProc.on('exit', code => console.log(`[shell] python server exited: ${code}`));
}

// Poll the existing boot-id endpoint until the server answers, so the window
// never loads a dead URL. Gives up after ~18s and opens anyway.
function waitForServer(onReady, tries = 0) {
  const req = http.get(`http://127.0.0.1:${PORT}/_server_boot_id`, res => {
    res.resume();
    if (res.statusCode === 200) onReady(); else schedule();
  });
  req.on('error', schedule);
  function schedule() {
    if (tries >= 120) { onReady(); return; }
    setTimeout(() => waitForServer(onReady, tries + 1), 150);
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#1a1d21',   // matches the app; avoids a white flash
    icon: ICON,
    show: false,
    // Integrated title bar: hide the OS caption but keep the native window
    // buttons as an overlay in the top-right; the app's toolbar fills the rest.
    titleBarStyle: 'hidden',
    titleBarOverlay: { color: '#1a1d21', symbolColor: '#dee2e6', height: 40 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadURL(`http://127.0.0.1:${PORT}`);
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.on('closed', () => { mainWindow = null; });
  // F12 / Ctrl+Shift+I toggles DevTools (there's no app menu to provide it).
  mainWindow.webContents.on('before-input-event', (e, input) => {
    const ctrlShiftI = input.control && input.shift && input.key.toLowerCase() === 'i';
    if (input.key === 'F12' || ctrlShiftI) mainWindow.webContents.toggleDevTools();
  });
}

function shutdown() {
  if (pyProc && pyProc.pid) {
    treeKill(pyProc.pid);
    pyProc = null;
  }
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);   // drop the default File/Edit/View/Window menu
    startServer();
    waitForServer(createWindow);
  });
}

app.on('before-quit', shutdown);
app.on('window-all-closed', () => { shutdown(); app.quit(); });
