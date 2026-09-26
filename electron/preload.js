'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('skillTreeDesktop', {
  pickFile: options => ipcRenderer.invoke('skilltree:pick-file', options),
});

// Tag the document so the app's CSS can lay out the integrated title bar:
// electron-shell, plus platform-win32, platform-darwin or platform-linux.
// Runs sandboxed, in an isolated context, before page scripts.

window.addEventListener('DOMContentLoaded', () => {
  document.documentElement.classList.add('electron-shell', `platform-${process.platform}`);
});
