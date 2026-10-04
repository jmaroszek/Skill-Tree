'use strict';

// Electron desktop shell for Skill Tree.
//
// Responsibilities:
//   1. Start the server with a fresh access token, and wait for its READY
//      line, which names the port it picked (server_process.js). A packaged
//      app runs the bundled PyInstaller build; a checkout runs app.py
//      (shell.js says which).
//   2. Open a native window there. The first URL carries the token, which
//      the server swaps for a cookie; nothing else on the machine has it.
//   3. Own the lifecycle: quitting closes the server's stdin and the server
//      shuts itself down. If the shell crashes, stdin closes all the same.

const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const { registerResourceDialog } = require('./resource_dialog');
const {
  appUrl, exitMessage, newToken, restorePrompt, startServer, stopServer,
} = require('./server_process');
const {
  isAppUrl, isExternalUrl, macMenuTemplate, serverCommand, titleBarOverlay, windowChrome,
} = require('./shell');
const {
  checkNow, latestRelease, readPreferences, updateMode, writePreferences,
} = require('./updates');

// The sandbox database is a developer's; a packaged app ignores the flag.
const SANDBOX = !app.isPackaged && process.argv.includes('--sandbox');

// electron/ lives inside the repo, so the app root is one level up.
const REPO = path.resolve(__dirname, '..');
const ICON = path.join(REPO, 'assets', 'skill_tree.ico');

let server = null;   // { proc, port }; proc is null when showing another shell's server
let mainWindow = null;
let quitting = false;
registerResourceDialog(ipcMain, dialog, () => mainWindow, () => server && server.port);
registerUpdateSettings();
registerModalDimming();

app.setAppUserModelId('com.skilltree.app');
// Separate Electron profile per environment so a sandbox window and a
// production window never share state or fight over the single-instance lock.
app.setPath('userData', path.join(app.getPath('appData'),
  SANDBOX ? 'SkillTree-Sandbox' : 'SkillTree'));

async function launch(extraArgs = []) {
  const token = newToken();
  const { command, args, cwd } = serverCommand({
    isPackaged: app.isPackaged, platform: process.platform,
    resourcesPath: process.resourcesPath, repo: REPO, env: process.env,
    exists: fs.existsSync, sandbox: SANDBOX,
  });
  let started;
  try {
    started = await startServer({
      command, args: [...args, ...extraArgs], cwd,
      env: { ...process.env, SKILLTREE_TOKEN: token },
      log: chunk => process.stdout.write(`[py] ${chunk}`),
    });
  } catch (err) {
    // A damaged database, and a backup that opens cleanly: offer it. The
    // server puts it in place, keeping the damaged file, and starts as usual.
    if (err.restoreOffer && !extraArgs.length) {
      const { response } = await dialog.showMessageBox(restorePrompt(err.restoreOffer));
      if (response === 0) {
        launch(['--restore-backup', err.restoreOffer.backup]);
        return;
      }
      app.quit();
      return;
    }
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
  // Well after startup, so the window never waits on the network.
  setTimeout(checkForUpdates, 15000);
}

// One check per launch (updates.js says which kind, or none).
function checkForUpdates() {
  const mode = updateMode({
    isPackaged: app.isPackaged, platform: process.platform, env: process.env,
    preferences: readPreferences(app.getPath('userData')),
  });
  if (mode === 'install') {
    // Downloads in the background; installs when the app next quits.
    const { autoUpdater } = require('electron-updater');
    autoUpdater.checkForUpdatesAndNotify().catch(err => {
      console.warn(`[shell] update check failed: ${err.message}`);
    });
  } else if (mode === 'notify') {
    latestRelease({ current: app.getVersion(), fetchJson: fetchReleaseJson }).then(release => {
      if (!release || !mainWindow) return;
      const choice = dialog.showMessageBoxSync(mainWindow, {
        type: 'info',
        message: `Skill Tree ${release.version} is available.`,
        detail: `You have ${app.getVersion()}. Download it from the release page and install `
          + 'it over this one. Your graph stays where it is.',
        buttons: ['Download', 'Later'],
        defaultId: 0,
        cancelId: 1,
      });
      if (choice === 0) shell.openExternal(release.url);
    });
  }
}

// Settings > About's update controls reach the shell through these
// (preload.js, about_callbacks.py). Only the app's own page may call them.
function registerUpdateSettings() {
  const userData = () => app.getPath('userData');
  const guard = event => {
    const url = event.senderFrame && event.senderFrame.url;
    if (!isAppUrl(url, server && server.port)) throw new Error('Not the Skill Tree page.');
  };
  ipcMain.handle('skilltree:updates-get', event => {
    guard(event);
    return readPreferences(userData()).checkForUpdates !== false;
  });
  ipcMain.handle('skilltree:updates-set', (event, on) => {
    guard(event);
    return writePreferences(userData(), { checkForUpdates: !!on }).checkForUpdates;
  });
  ipcMain.handle('skilltree:updates-check', event => {
    guard(event);
    const mode = updateMode({ isPackaged: app.isPackaged, platform: process.platform, env: process.env });
    return checkNow({
      isPackaged: app.isPackaged, platform: process.platform, env: process.env,
      current: app.getVersion(), fetchJson: fetchReleaseJson,
      autoUpdater: mode === 'install' ? require('electron-updater').autoUpdater : null,
    });
  });
}

// Windows draws its window buttons above the page, out of reach of a modal's
// backdrop, so the page reports modals here and the overlay is repainted to
// match. macOS keeps its traffic lights, and Linux its native frame.
function registerModalDimming() {
  ipcMain.handle('skilltree:modal-open', (event, open) => {
    const url = event.senderFrame && event.senderFrame.url;
    if (!isAppUrl(url, server && server.port)) throw new Error('Not the Skill Tree page.');
    if (process.platform !== 'win32' || !mainWindow) return;
    mainWindow.setTitleBarOverlay(titleBarOverlay(!!open));
  });
}

async function fetchReleaseJson(url) {
  const response = await fetch(url, { headers: { Accept: 'application/vnd.github+json' } });
  if (!response.ok) throw new Error(`GitHub answered ${response.status}`);
  return response.json();
}

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#1a1d21',   // matches the app; avoids a white flash
    // Packaged builds carry their icon in the executable.
    icon: process.platform === 'win32' && !app.isPackaged ? ICON : undefined,
    show: false,
    // The app's toolbar is the title bar on Windows and macOS (shell.js).
    ...windowChrome(process.platform),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  guardWindow(mainWindow.webContents);
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
  // F12 / Ctrl+Shift+I toggles DevTools (Windows and Linux have no menu to provide it).
  mainWindow.webContents.on('before-input-event', (e, input) => {
    const ctrlShiftI = input.control && input.shift && input.key.toLowerCase() === 'i';
    if (input.key === 'F12' || ctrlShiftI) mainWindow.webContents.toggleDevTools();
  });
}

// The window shows the app and nothing else. Web and mail links open in the
// system's apps; anything else is refused (the server's own resource opener
// handles files and custom schemes, and asks first).
function guardWindow(contents) {
  contents.setWindowOpenHandler(({ url }) => {
    if (isExternalUrl(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  contents.on('will-navigate', (event, url) => {
    if (isAppUrl(url, server && server.port)) return;
    event.preventDefault();
    if (isExternalUrl(url)) shell.openExternal(url);
  });
  // A crashed or killed page leaves a blank window. The graph is saved as
  // the user works, so reloading loses nothing.
  contents.on('render-process-gone', (event, details) => {
    if (quitting || details.reason === 'clean-exit') return;
    const choice = dialog.showMessageBoxSync(mainWindow, {
      type: 'warning',
      message: "Skill Tree's window stopped unexpectedly.",
      detail: `Reason: ${details.reason}. Your graph is saved as you work, so reloading loses nothing.`,
      buttons: ['Reload', 'Quit'],
      defaultId: 0,
      cancelId: 1,
    });
    if (choice === 0) contents.reload();
    else app.quit();
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
    // macOS takes its clipboard shortcuts from the menu. Elsewhere the toolbar
    // is the whole title bar, and the shortcuts work without one.
    Menu.setApplicationMenu(process.platform === 'darwin'
      ? Menu.buildFromTemplate(macMenuTemplate(app.name))
      : null);
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
