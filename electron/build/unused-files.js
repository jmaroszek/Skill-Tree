'use strict';

// Files Electron ships that Skill Tree never uses. electron-builder runs this
// on the packed app, before it signs it and builds the installer (afterPack in
// electron-builder.yml).
//
// dxcompiler.dll and dxil.dll are the DirectX shader compiler behind
// Chromium's WebGPU on Windows, about 26 MB. Nothing Skill Tree loads uses
// WebGPU: the graphs and charts draw with Canvas 2D, SVG and WebGL, which
// don't need it.

const fs = require('fs');
const path = require('path');

const UNUSED = {
  win32: ['dxcompiler.dll', 'dxil.dll'],
};

function unusedFiles(platform) {
  return UNUSED[platform] || [];
}

module.exports = async function removeUnusedFiles(context) {
  const names = unusedFiles(context.electronPlatformName);
  for (const name of names) {
    fs.rmSync(path.join(context.appOutDir, name), { force: true });
  }
  if (names.length) console.log(`  • left out ${names.join(', ')}: Skill Tree doesn't use WebGPU`);
};
module.exports.unusedFiles = unusedFiles;
