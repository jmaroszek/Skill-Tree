'use strict';

// Do not let an imported UNC root make a native dialog visit another host.
// Import also clears device-local roots, so a newly selected local root is
// still a convenient starting folder for later Browse clicks.
function localStartingPath(value) {
  if (typeof value !== 'string' || !value) return undefined;
  if (value.startsWith('\\\\') || value.startsWith('//')) return undefined;
  if (process.platform === 'win32') {
    return /^[A-Za-z]:[\\/]/.test(value) ? value : undefined;
  }
  return value.startsWith('/') ? value : undefined;
}

// getPort returns the server's port, which is only known once it is ready.
function registerResourceDialog(ipcMain, dialog, getWindow, getPort) {
  ipcMain.handle('skilltree:pick-file', async (event, options) => {
    const senderUrl = new URL(event.senderFrame.url);
    const port = getPort();
    if (!port || senderUrl.protocol !== 'http:' || senderUrl.hostname !== '127.0.0.1'
        || senderUrl.port !== String(port)) {
      throw new Error('File picker is only available to the local Skill Tree page.');
    }
    const opts = options && typeof options === 'object' ? options : {};
    const result = await dialog.showOpenDialog(getWindow(), {
      title: typeof opts.title === 'string' ? opts.title.slice(0, 100) : 'Select file',
      defaultPath: localStartingPath(opts.defaultPath),
      properties: [opts.directory ? 'openDirectory' : 'openFile'],
      filters: !opts.directory && opts.markdown ? [
        { name: 'Markdown files', extensions: ['md'] },
        { name: 'All files', extensions: ['*'] },
      ] : undefined,
    });
    return result.canceled ? '' : result.filePaths[0] || '';
  });
}

module.exports = { registerResourceDialog };
