'use strict';

// Electron desktop shell for Skill Tree.
//
// Responsibilities:
//   1. Start the Python server (`app.py --desktop`, pythonw, no console) with
//      a fresh access token, and wait for its READY line, which names the
//      port it picked (server_process.js).
//   2. Open a native window there. The first URL carries the token, which
//      the server swaps for a cookie; nothing else on the machine has it.
//   3. Own the lifecycle: quitting closes the server's stdin and the server
//      shuts itself down. If the shell crashes, stdin closes all the same.

const { app, BrowserWindow, Menu, dialog, ipcMain } = require('electron');
const path = require('path');
const { registerResourceDialog } = require('./resource_dialog');
const {
  appUrl, exitMessage, newToken, startServer, stopServer,
} = require('./server_process');

const SANDBOX = process.argv.includes('--sandbox');

// The Skill Tree conda environment's windowless interpreter.
const PYTHONW = 'C:\\Users\\jonah\\anaconda3\\envs\\skill-tree\\pythonw.exe';
// electron/ lives inside the repo, so the app root is one level up.
const REPO = path.resolve(__dirname, '..');
const ICON = path.join(REPO, 'assets', 'skill_tree.ico');

let server = null;   // { proc, port }; proc is null when showing another shell's server
let mainWindow = null;
let quitting = false;
registerResourceDialog(ipcMain, dialog, () => mainWindow, () => server && server.port);

app.setAppUserModelId('com.skilltree.app');
// Separate Electron profile per environment so a sandbox window and a
// production window never share state or fight over the single-instance lock.
app.setPath('userData', path.join(app.getPath('appData'),
  SANDBOX ? 'SkillTree-Sandbox' : 'SkillTree'));

async function launch() {
  const token = newToken();
  const args = ['app.py', '--desktop'];
  if (SANDBOX) args.push('--sandbox');
  let started;
  try {
    started = await startServer({
      command: PYTHONW, args, cwd: REPO,
      env: { ...process.env, SKILLTREE_TOKEN: token },
      log: chunk => process.stdout.write(`[py] ${chunk}`),
    });
  } catch (err) {
    let message;
    if (err.timedOut) message = "Skill Tree's server didn't start in time.";
    else if (err.exitCode !== undefined) message = exitMessage(err.exitCode, err.stderrTail);
    else message = `Skill Tree couldn't start its server: ${err.message}`;
    dialog.showErrorBox('Skill Tree', message);
    app.quit();
    return;
  }
  if (started.alreadyRunning) {
    // Another Skill Tree owns this data: show it rather than refuse.
    server = { proc: null, port: started.port };
    createWindow(appUrl(started.port, started.token));
    return;
  }
  server = started;
  started.proc.on('exit', code => {
    if (quitting) return;
    dialog.showErrorBox('Skill Tree', exitMessage(code));
    app.quit();
  });
  createWindow(appUrl(started.port, token));
}

function createWindow(url) {
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
  // Maximize before the page loads, so its first frame is drawn at full size.
  // Maximizing after the first paint (on ready-to-show) resized a page whose
  // main thread was busy with startup. It couldn't re-lay-out until the work
  // paused, so the startup cover sat in the top-left 1400x900 corner.
  // maximize() also shows the window, in backgroundColor, which matches the
  // cover, until the page paints.
  mainWindow.maximize();
  mainWindow.show();
  mainWindow.loadURL(url);
  mainWindow.on('closed', () => { mainWindow = null; });
  // F12 / Ctrl+Shift+I toggles DevTools (there's no app menu to provide it).
  mainWindow.webContents.on('before-input-event', (e, input) => {
    const ctrlShiftI = input.control && input.shift && input.key.toLowerCase() === 'i';
    if (input.key === 'F12' || ctrlShiftI) mainWindow.webContents.toggleDevTools();
  });
}

async function shutdown() {
  quitting = true;
  if (server && server.proc) await stopServer(server.proc);
  server = null;
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
    launch();
  });
}

// Quit waits for the server to finish what it is doing and exit.
app.on('before-quit', event => {
  if (quitting) return;
  event.preventDefault();
  shutdown().then(() => app.quit());
});
app.on('window-all-closed', () => app.quit());
