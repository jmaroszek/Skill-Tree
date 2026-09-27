'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  isAppUrl, isExternalUrl, macMenuTemplate, serverCommand, windowChrome,
} = require('./shell');

const none = () => false;

test('a packaged app runs the bundled server binary', () => {
  assert.deepEqual(serverCommand({
    isPackaged: true, platform: 'win32', resourcesPath: 'C:\\Program Files\\Skill Tree\\resources',
    repo: 'unused', env: {}, exists: none,
  }), {
    command: 'C:\\Program Files\\Skill Tree\\resources\\server\\skilltree-server.exe',
    args: ['--desktop'],
    cwd: 'C:\\Program Files\\Skill Tree\\resources\\server',
  });
  const mac = serverCommand({
    isPackaged: true, platform: 'darwin', resourcesPath: '/Applications/Skill Tree.app/Contents/Resources',
    repo: 'unused', env: {}, exists: none,
  });
  assert.equal(mac.command, '/Applications/Skill Tree.app/Contents/Resources/server/skilltree-server');
});

test('a packaged app ignores --sandbox: that data is for developers', () => {
  const cmd = serverCommand({
    isPackaged: true, platform: 'linux', resourcesPath: '/opt/skill-tree/resources',
    repo: 'unused', env: {}, exists: none, sandbox: true,
  });
  assert.deepEqual(cmd.args, ['--desktop']);
});

test('in development, SKILLTREE_PYTHON names the interpreter', () => {
  const cmd = serverCommand({
    isPackaged: false, platform: 'linux', resourcesPath: '', repo: '/src/skill-tree',
    env: { SKILLTREE_PYTHON: '/opt/py/bin/python3' }, exists: none, sandbox: true,
  });
  assert.deepEqual(cmd, {
    command: '/opt/py/bin/python3', args: ['app.py', '--desktop', '--sandbox'], cwd: '/src/skill-tree',
  });
});

test('in development on Windows, a conda env named skill-tree is found without setup', () => {
  const env = { USERPROFILE: 'C:\\Users\\someone' };
  const found = 'C:\\Users\\someone\\miniconda3\\envs\\skill-tree\\pythonw.exe';
  const cmd = serverCommand({
    isPackaged: false, platform: 'win32', resourcesPath: '', repo: 'C:\\src\\Skill-Tree',
    env, exists: p => p === found,
  });
  assert.equal(cmd.command, found);
});

test('in development, the interpreter on PATH is the last resort', () => {
  const base = { isPackaged: false, resourcesPath: '', repo: '/src', env: {}, exists: none };
  assert.equal(serverCommand({ ...base, platform: 'win32' }).command, 'pythonw');
  assert.equal(serverCommand({ ...base, platform: 'darwin' }).command, 'python3');
});

test('each platform gets its own window chrome', () => {
  const win = windowChrome('win32');
  assert.equal(win.titleBarStyle, 'hidden');
  assert.equal(typeof win.titleBarOverlay, 'object');
  const mac = windowChrome('darwin');
  assert.equal(mac.titleBarStyle, 'hiddenInset');
  assert.equal(mac.titleBarOverlay, true);   // exposes env(titlebar-area-x)
  assert.deepEqual(windowChrome('linux'), {});   // the native frame
});

test('only the app itself may load in the window', () => {
  assert.equal(isAppUrl('http://127.0.0.1:5123/', 5123), true);
  assert.equal(isAppUrl('http://127.0.0.1:5123/?token=x', 5123), true);
  assert.equal(isAppUrl('http://127.0.0.1:5124/', 5123), false);
  assert.equal(isAppUrl('http://localhost:5123/', 5123), false);
  assert.equal(isAppUrl('https://127.0.0.1:5123/', 5123), false);
  assert.equal(isAppUrl('https://example.com/', 5123), false);
  assert.equal(isAppUrl('not a url', 5123), false);
  assert.equal(isAppUrl('http://127.0.0.1:5123/', null), false);
});

test('web and mail links go to the system, and nothing else does', () => {
  assert.equal(isExternalUrl('https://example.com/x'), true);
  assert.equal(isExternalUrl('http://example.com'), true);
  assert.equal(isExternalUrl('mailto:someone@example.com'), true);
  for (const url of ['file:///etc/passwd', 'javascript:alert(1)', 'ms-msdt:/id x',
    'smb://host/share', 'notion://x', 'garbage']) {
    assert.equal(isExternalUrl(url), false, url);
  }
});

test('the macOS menu carries the Edit roles that make Cmd+C and Cmd+V work', () => {
  const menu = macMenuTemplate('Skill Tree');
  const roles = JSON.stringify(menu);
  for (const role of ['undo', 'redo', 'cut', 'copy', 'paste', 'selectAll', 'quit']) {
    assert.ok(roles.includes(`"role":"${role}"`), role);
  }
  assert.equal(menu[0].label, 'Skill Tree');
});
