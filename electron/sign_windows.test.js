'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { signCommand, signFile } = require('./build/sign-windows');

test('the file goes wherever the template says', () => {
  assert.equal(
    signCommand('C:\\build\\Skill Tree.exe', 'signtool sign /fd sha256 "{file}"'),
    'signtool sign /fd sha256 "C:\\build\\Skill Tree.exe"');
  assert.equal(signCommand('a.exe', 'tool "{file}" --verify "{file}"'),
    'tool "a.exe" --verify "a.exe"');
});

test('with no signing service configured, nothing is signed', () => {
  assert.equal(signCommand('a.exe', undefined), null);
  assert.equal(signCommand('a.exe', ''), null);
  assert.equal(signFile('a.exe', ''), false);
});

test('a configured command runs, and its failure fails the build', () => {
  const node = JSON.stringify(process.execPath);
  assert.equal(signFile('ignored', `${node} -e "process.exit(0)" "{file}"`), true);
  assert.throws(() => signFile('ignored', `${node} -e "process.exit(3)" "{file}"`));
});
