'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { registerResourceDialog } = require('./resource_dialog');

test('native picker accepts only the local app and returns the selected file', async () => {
  let handler;
  const calls = [];
  const window = {};
  registerResourceDialog(
    { handle: (name, fn) => { assert.equal(name, 'skilltree:pick-file'); handler = fn; } },
    { showOpenDialog: async (...args) => {
      calls.push(args);
      return { canceled: false, filePaths: ['/Library/file.md'] };
    } },
    () => window,
    () => 8051,
  );
  const event = { senderFrame: { url: 'http://127.0.0.1:8051/' } };
  assert.equal(await handler(event, { defaultPath: '/Library' }),
               '/Library/file.md');
  assert.equal(calls[0][0], window);
  assert.deepEqual(calls[0][1].properties, ['openFile']);
  assert.equal(calls[0][1].filters, undefined);
  assert.equal(calls[0][1].defaultPath,
               process.platform === 'win32' ? undefined : '/Library');
  await assert.rejects(() => handler(
    { senderFrame: { url: 'https://example.com/' } }, {}), /local Skill Tree/);
  assert.equal(calls.length, 1);
});

test('imported network roots never reach the native picker', async () => {
  let handler;
  let options;
  registerResourceDialog(
    { handle: (_name, fn) => { handler = fn; } },
    { showOpenDialog: async (_window, opts) => {
      options = opts;
      return { canceled: true, filePaths: [] };
    } },
    () => null,
    () => 8051,
  );
  const event = { senderFrame: { url: 'http://127.0.0.1:8051/' } };
  await handler(event, { defaultPath: '\\\\attacker\\share', directory: true });
  assert.equal(options.defaultPath, undefined);
});

test('a local root still starts the native picker there', async () => {
  let handler;
  let options;
  registerResourceDialog(
    { handle: (_name, fn) => { handler = fn; } },
    { showOpenDialog: async (_window, opts) => {
      options = opts;
      return { canceled: true, filePaths: [] };
    } },
    () => null,
    () => 8051,
  );
  const local = process.platform === 'win32' ? 'C:\\Library' : '/Library';
  await handler({ senderFrame: { url: 'http://127.0.0.1:8051/' } },
                { defaultPath: local });
  assert.equal(options.defaultPath, local);
});

test('a pick with no root starts where the last pick ended', async () => {
  let handler;
  const local = process.platform === 'win32' ? 'C:\\Library' : '/Library';
  const starts = [];
  let picks = [`${local}${path.sep}Notes${path.sep}file.md`, `${local}${path.sep}Folder`, ''];
  registerResourceDialog(
    { handle: (_name, fn) => { handler = fn; } },
    { showOpenDialog: async (_window, opts) => {
      starts.push(opts.defaultPath);
      const picked = picks.shift();
      return { canceled: !picked, filePaths: picked ? [picked] : [] };
    } },
    () => null,
    () => 8051,
  );
  const event = { senderFrame: { url: 'http://127.0.0.1:8051/' } };
  await handler(event, {});
  assert.equal(starts[0], undefined);
  await handler(event, { directory: true });
  assert.equal(starts[1], `${local}${path.sep}Notes`);
  // A cancelled pick leaves it where it was, and a folder pick starts in that folder.
  await handler(event, {});
  assert.equal(starts[2], `${local}${path.sep}Folder`);
  // A section's own root still wins.
  picks = [''];
  await handler(event, { defaultPath: local });
  assert.equal(starts[3], local);
});

test('a picked network folder is not the next starting point', async () => {
  let handler;
  const starts = [];
  registerResourceDialog(
    { handle: (_name, fn) => { handler = fn; } },
    { showOpenDialog: async (_window, opts) => {
      starts.push(opts.defaultPath);
      return { canceled: false, filePaths: ['\\\\host\\share\\Folder'] };
    } },
    () => null,
    () => 8051,
  );
  const event = { senderFrame: { url: 'http://127.0.0.1:8051/' } };
  await handler(event, { directory: true });
  await handler(event, { directory: true });
  assert.deepEqual(starts, [undefined, undefined]);
});

test('native picker can choose a folder', async () => {
  let handler;
  const calls = [];
  registerResourceDialog(
    { handle: (_name, fn) => { handler = fn; } },
    { showOpenDialog: async (...args) => {
      calls.push(args);
      return { canceled: false, filePaths: ['/Library/Notes'] };
    } },
    () => null,
    () => 8051,
  );
  const event = { senderFrame: { url: 'http://127.0.0.1:8051/' } };
  assert.equal(await handler(event, { directory: true }), '/Library/Notes');
  assert.deepEqual(calls[0][1].properties, ['openDirectory']);
});

test('cancelled native picker returns an empty path', async () => {
  let handler;
  registerResourceDialog(
    { handle: (_name, fn) => { handler = fn; } },
    { showOpenDialog: async () => ({ canceled: true, filePaths: [] }) },
    () => null,
    () => 8051,
  );
  assert.equal(await handler({ senderFrame: { url: 'http://127.0.0.1:8051/' } }), '');
});

test('native picker refuses everyone until the server has a port', async () => {
  let handler;
  registerResourceDialog(
    { handle: (_name, fn) => { handler = fn; } },
    { showOpenDialog: async () => assert.fail('no dialog before the server is ready') },
    () => null,
    () => null,
  );
  await assert.rejects(() => handler({ senderFrame: { url: 'http://127.0.0.1:8051/' } }, {}),
    /local Skill Tree/);
});
