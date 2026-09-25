'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
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
    8051,
  );
  const event = { senderFrame: { url: 'http://127.0.0.1:8051/' } };
  assert.equal(await handler(event, { markdown: true, defaultPath: '/Library' }),
               '/Library/file.md');
  assert.equal(calls[0][0], window);
  assert.deepEqual(calls[0][1].properties, ['openFile']);
  assert.deepEqual(calls[0][1].filters[0].extensions, ['md']);
  await assert.rejects(() => handler(
    { senderFrame: { url: 'https://example.com/' } }, {}), /local Skill Tree/);
  assert.equal(calls.length, 1);
});

test('cancelled native picker returns an empty path', async () => {
  let handler;
  registerResourceDialog(
    { handle: (_name, fn) => { handler = fn; } },
    { showOpenDialog: async () => ({ canceled: true, filePaths: [] }) },
    () => null,
    8051,
  );
  assert.equal(await handler({ senderFrame: { url: 'http://127.0.0.1:8051/' } }), '');
});
