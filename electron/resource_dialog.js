'use strict';

function registerResourceDialog(ipcMain, dialog, getWindow, port) {
  ipcMain.handle('skilltree:pick-file', async (event, options) => {
    const senderUrl = new URL(event.senderFrame.url);
    if (senderUrl.protocol !== 'http:' || senderUrl.hostname !== '127.0.0.1'
        || senderUrl.port !== String(port)) {
      throw new Error('File picker is only available to the local Skill Tree page.');
    }
    const opts = options && typeof options === 'object' ? options : {};
    const result = await dialog.showOpenDialog(getWindow(), {
      title: typeof opts.title === 'string' ? opts.title.slice(0, 100) : 'Select file',
      defaultPath: typeof opts.defaultPath === 'string' ? opts.defaultPath : undefined,
      properties: ['openFile'],
      filters: opts.markdown ? [
        { name: 'Markdown files', extensions: ['md'] },
        { name: 'All files', extensions: ['*'] },
      ] : undefined,
    });
    return result.canceled ? '' : result.filePaths[0] || '';
  });
}

module.exports = { registerResourceDialog };
