'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { findProblem } = require('./build/check-update-signature');

const BUILDER = fs.readFileSync(path.join(__dirname, 'electron-builder.yml'), 'utf8');
const RELEASE = fs.readFileSync(
  path.join(__dirname, '..', '.github', 'workflows', 'release.yml'), 'utf8');

test('installed copies are told whose signature an update must carry', {
  todo: 'needs the code signing certificate\'s subject',
}, () => {
  const options = /^ {2}signtoolOptions:\r?\n((?: {4}.*\r?\n)+)/m.exec(BUILDER)[1];
  // One name, or a list of them.
  assert.match(options, /^ {4}publisherName: *(?:\r?\n {6}- *\S|(?!null\b|~)\S)/m);
});

test('nothing turns the signature check off', () => {
  assert.doesNotMatch(BUILDER, /^\s*verifyUpdateCodeSignature: *false/m);
});

test('a tag build runs the check on its installer', () => {
  const step = /- name: Installed copies accept this installer\r?\n((?: {8}.*\r?\n)+)/.exec(RELEASE);
  assert.ok(step, 'release.yml has no such step');
  assert.match(step[1], /if: runner\.os == 'Windows' && env\.TAGGED == 'true'/);
  assert.match(step[1], /run: node build\/check-update-signature\.js dist/);
});

test('an installer passes only if the named publisher signed it', async () => {
  const verify = async (names, file) => (names.includes('Signer') && file === 'setup.exe'
    ? null : 'signed with incorrect certificate');
  assert.equal(await findProblem({ names: ['Signer'], installer: 'setup.exe', verify }), null);
  assert.match(await findProblem({ names: ['Other'], installer: 'setup.exe', verify }),
    /would refuse setup\.exe: signed with incorrect certificate/);
});

test('a build that names no publisher never reaches the signature check', async () => {
  const verify = async () => assert.fail('nothing to compare against');
  assert.match(await findProblem({ names: [], installer: 'setup.exe', verify }),
    /names no publisher/);
});
