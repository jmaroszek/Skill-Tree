'use strict';

// Minimal preload: tag the document so the app's CSS/JS can adapt when it's
// running inside the Electron shell (used from Phase 2 onward for the draggable
// integrated title bar). Runs in an isolated context before page scripts.

window.addEventListener('DOMContentLoaded', () => {
  document.documentElement.classList.add('electron-shell');
});
