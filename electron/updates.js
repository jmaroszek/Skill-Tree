'use strict';

// Updates, from published GitHub Releases (drafts are invisible).
//
// - "install": the Windows installer and the AppImage use electron-updater,
//   which downloads in the background and installs when the app quits.
// - "notify": macOS can't replace an app that isn't Developer ID signed, and
//   a deb belongs to the package manager, so those only say a new version is
//   out and offer its download page.
// - "off": a developer's checkout, or a user who turned checks off
//   (preferences.json in the shell's userData folder: {"checkForUpdates": false}).
//
// One check per launch. It asks GitHub for the latest release and sends
// nothing about the user or their graph.

const fs = require('fs');
const path = require('path');

const OWNER = 'jmaroszek';
const REPO = 'Skill-Tree';
const RELEASES_API = `https://api.github.com/repos/${OWNER}/${REPO}/releases/latest`;
const RELEASES_PAGE = `https://github.com/${OWNER}/${REPO}/releases/`;

function readPreferences(userDataDir) {
  try {
    const prefs = JSON.parse(fs.readFileSync(path.join(userDataDir, 'preferences.json'), 'utf8'));
    return prefs && typeof prefs === 'object' ? prefs : {};
  } catch (err) {
    return {};
  }
}

function writePreferences(userDataDir, changes) {
  const prefs = { ...readPreferences(userDataDir), ...changes };
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(path.join(userDataDir, 'preferences.json'), JSON.stringify(prefs, null, 2));
  return prefs;
}

function updateMode({ isPackaged, platform, env, preferences = {} }) {
  if (!isPackaged || preferences.checkForUpdates === false) return 'off';
  if (platform === 'win32' || (platform === 'linux' && env.APPIMAGE)) return 'install';
  return 'notify';
}

// [major, minor, patch, prerelease parts] from "v1.2.3" or "1.2.3-beta.1".
function parse(version) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(String(version).trim());
  if (!match) return null;
  return { core: match.slice(1, 4).map(Number), pre: match[4] ? match[4].split('.') : [] };
}

function comparePre(a, b) {
  // A release outranks any of its prereleases.
  if (!a.length || !b.length) return a.length ? -1 : b.length ? 1 : 0;
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    if (a[i] === undefined) return -1;
    if (b[i] === undefined) return 1;
    const x = /^\d+$/.test(a[i]) ? Number(a[i]) : a[i];
    const y = /^\d+$/.test(b[i]) ? Number(b[i]) : b[i];
    if (x !== y) return x > y ? 1 : -1;
  }
  return 0;
}

function isNewer(candidate, current) {
  const a = parse(candidate);
  const b = parse(current);
  if (!a || !b) return false;
  for (let i = 0; i < 3; i += 1) {
    if (a.core[i] !== b.core[i]) return a.core[i] > b.core[i];
  }
  return comparePre(a.pre, b.pre) > 0;
}

// The notify-only check: { version, url } of a newer release, or null.
// Offline, rate-limited or odd answers all mean "nothing to say".
async function latestRelease({ current, fetchJson }) {
  let release;
  try {
    release = await fetchJson(RELEASES_API);
  } catch (err) {
    return null;
  }
  const tag = release && release.tag_name;
  const url = release && release.html_url;
  if (!tag || !isNewer(tag, current)) return null;
  // Only ever open this repository's own release pages.
  if (typeof url !== 'string' || !url.startsWith(RELEASES_PAGE)) return null;
  return { version: String(tag).replace(/^v/, ''), url };
}

// Settings > About's "Check now": says what it found, as { message, url? }.
// It runs even with automatic checks off, since the user asked. A failure's
// details go to the log, never to the page: they are long and mean nothing
// to the reader.
async function checkNow({
  isPackaged, platform, env, current, fetchJson, autoUpdater, log = console.error,
}) {
  const mode = updateMode({ isPackaged, platform, env });
  const latest = { message: 'You have the latest version.' };
  if (mode === 'off') {
    return { message: 'This is a development copy; it updates from its checkout.' };
  }
  try {
    if (mode === 'install') {
      const result = await autoUpdater.checkForUpdates();
      const version = result && result.updateInfo && result.updateInfo.version;
      if (!version || !isNewer(version, current)) return latest;
      return { message: `Skill Tree ${version} is downloading. It installs when you quit Skill Tree.` };
    }
    const release = await fetchJson(RELEASES_API);
    const found = await latestRelease({ current, fetchJson: async () => release });
    if (!found) return latest;
    return { message: `Skill Tree ${found.version} is available.`, url: found.url };
  } catch (err) {
    log(`Update check failed: ${err && err.stack ? err.stack : err}`);
    return { message: "Couldn't check for updates. Try again later." };
  }
}

module.exports = {
  RELEASES_API, RELEASES_PAGE, checkNow, isNewer, latestRelease, readPreferences,
  updateMode, writePreferences,
};
