'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const removeUnusedFiles = require('./build/unused-files');

test("WebGPU's shader compiler is left out of the Windows app only", () => {
  assert.deepEqual(removeUnusedFiles.unusedFiles('win32'), ['dxcompiler.dll', 'dxil.dll']);
  assert.deepEqual(removeUnusedFiles.unusedFiles('darwin'), []);
  assert.deepEqual(removeUnusedFiles.unusedFiles('linux'), []);
});

test('the packed app loses those files and keeps the rest', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'skilltree-pack-'));
  try {
    for (const name of ['dxcompiler.dll', 'dxil.dll', 'd3dcompiler_47.dll', 'Skill Tree.exe']) {
      fs.writeFileSync(path.join(dir, name), '');
    }
    const context = { appOutDir: dir, electronPlatformName: 'win32' };
    await removeUnusedFiles(context);
    assert.deepEqual(fs.readdirSync(dir).sort(), ['Skill Tree.exe', 'd3dcompiler_47.dll']);
    // An Electron that no longer ships them is fine too.
    await removeUnusedFiles(context);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
