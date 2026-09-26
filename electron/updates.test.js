'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {
  RELEASES_API, isNewer, latestRelease, readPreferences, updateMode,
} = require('./updates');

test('Windows and the AppImage update themselves; macOS and the deb only say so', () => {
  assert.equal(updateMode({ isPackaged: true, platform: 'win32', env: {} }), 'install');
  assert.equal(updateMode({ isPackaged: true, platform: 'linux', env: { APPIMAGE: '/x.AppImage' } }),
    'install');
  assert.equal(updateMode({ isPackaged: true, platform: 'linux', env: {} }), 'notify');
  assert.equal(updateMode({ isPackaged: true, platform: 'darwin', env: {} }), 'notify');
});

test('a checkout and a user who turned checks off get no update checks', () => {
  assert.equal(updateMode({ isPackaged: false, platform: 'win32', env: {} }), 'off');
  assert.equal(updateMode({ isPackaged: true, platform: 'win32', env: {},
    preferences: { checkForUpdates: false } }), 'off');
});

test('versions compare as numbers, and a prerelease comes before its release', () => {
  assert.equal(isNewer('v1.0.0', '0.9.0'), true);
  assert.equal(isNewer('0.10.0', '0.9.0'), true);
  assert.equal(isNewer('0.9.0', '0.9.0'), false);
  assert.equal(isNewer('0.8.9', '0.9.0'), false);
  assert.equal(isNewer('1.0.0', '1.0.0-beta.2'), true);
  assert.equal(isNewer('1.0.0-beta.2', '1.0.0-beta.1'), true);
  assert.equal(isNewer('1.0.0-beta.1', '1.0.0'), false);
  assert.equal(isNewer('garbage', '0.9.0'), false);
});

test('the notify-only check reads the latest published release', async () => {
  let asked;
  const fetchJson = async url => {
    asked = url;
    return { tag_name: 'v1.2.0', html_url: 'https://github.com/jmaroszek/Skill-Tree/releases/tag/v1.2.0' };
  };
  assert.deepEqual(await latestRelease({ current: '1.1.0', fetchJson }),
    { version: '1.2.0', url: 'https://github.com/jmaroszek/Skill-Tree/releases/tag/v1.2.0' });
  assert.equal(asked, RELEASES_API);
  assert.equal(await latestRelease({ current: '1.2.0', fetchJson }), null);
});

test('being offline, or a strange answer, is not an error', async () => {
  assert.equal(await latestRelease({ current: '1.0.0', fetchJson: async () => { throw new Error('offline'); } }), null);
  assert.equal(await latestRelease({ current: '1.0.0', fetchJson: async () => ({}) }), null);
  assert.equal(await latestRelease({ current: '1.0.0',
    fetchJson: async () => ({ tag_name: 'v9.0.0', html_url: 'javascript:alert(1)' }) }), null);
});

test('preferences come from a small file, and a missing or broken one means defaults', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'st-prefs-'));
  assert.deepEqual(readPreferences(dir), {});
  fs.writeFileSync(path.join(dir, 'preferences.json'), '{"checkForUpdates": false}');
  assert.deepEqual(readPreferences(dir), { checkForUpdates: false });
  fs.writeFileSync(path.join(dir, 'preferences.json'), 'not json');
  assert.deepEqual(readPreferences(dir), {});
});
