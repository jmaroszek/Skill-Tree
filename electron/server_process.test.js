'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  appUrl, exitMessage, newToken, parseServerLine, restorePrompt, startServer, stopServer,
} = require('./server_process');

// A stand-in server: node running a small script.
function fake(script, extra = {}) {
  return { command: process.execPath, args: ['-e', script], env: process.env, ...extra };
}

test('the handshake lines parse, and nothing else does', () => {
  assert.deepEqual(parseServerLine('SKILLTREE_READY port=51234'), { type: 'ready', port: 51234 });
  assert.deepEqual(parseServerLine('SKILLTREE_READY port=51234\r'), { type: 'ready', port: 51234 });
  assert.deepEqual(parseServerLine('SKILLTREE_RUNNING port=8050 token=abc_-1'),
    { type: 'running', port: 8050, token: 'abc_-1' });
  for (const line of ['', 'SKILLTREE_READY', 'SKILLTREE_READY port=', 'x SKILLTREE_READY port=1',
    '2026-09-26 [INFO] Serving on http://127.0.0.1:5000']) {
    assert.equal(parseServerLine(line), null, line);
  }
});

test('every refusal code has its own message, and the detail is the last line', () => {
  const messages = [2, 3, 4, 5, 6, 7, 8].map(code => exitMessage(code));
  assert.equal(new Set(messages).size, messages.length);
  assert.match(exitMessage(4), /damaged/);
  assert.match(exitMessage(6), /in use by another program/);
  assert.match(exitMessage(1), /exit code 1/);
  assert.equal(exitMessage(3, 'noise\nSkill Tree can\'t start: saved by v2\n').split('\n\n')[1],
    'Skill Tree can\'t start: saved by v2');
});

test('tokens are long, URL-safe and new each time', () => {
  const a = newToken();
  assert.match(a, /^[A-Za-z0-9_-]{40,}$/);
  assert.notEqual(a, newToken());
  assert.equal(appUrl(5000, 'a b'), 'http://127.0.0.1:5000/?token=a%20b');
});

test('the server is ready when it says so, not before', async () => {
  const started = await startServer(fake(`
    console.log("2026 [INFO] still starting");
    setTimeout(() => console.log("SKILLTREE_READY port=40123"), 50);
    process.stdin.resume();
    process.stdin.on("end", () => process.exit(0));
  `));
  assert.equal(started.port, 40123);
  assert.equal(started.alreadyRunning, undefined);
  await stopServer(started.proc, { kill: () => assert.fail('it should stop on its own') });
  assert.equal(started.proc.exitCode, 0);
});

test('another running Skill Tree is handed over, with its token', async () => {
  const started = await startServer(fake(`
    console.log("SKILLTREE_RUNNING port=8050 token=theirs");
    process.exit(8);
  `));
  assert.deepEqual([started.port, started.token, started.alreadyRunning], [8050, 'theirs', true]);
});

test('a refusal rejects with its exit code and the server\'s last words', async () => {
  await assert.rejects(startServer(fake(`
    console.error("Skill Tree can't start: the data file is damaged");
    process.exit(4);
  `)), err => {
    assert.equal(err.exitCode, 4);
    assert.match(err.stderrTail, /damaged/);
    return true;
  });
});

test('a server that never gets ready times out, and is stopped', async () => {
  await assert.rejects(startServer(fake('setInterval(() => {}, 1000);', { timeoutMs: 200 })),
    err => err.timedOut === true);
});

test('a missing server binary is an error, not a hang', async () => {
  await assert.rejects(startServer({
    command: 'definitely-not-a-skill-tree-binary', args: [], env: process.env, timeoutMs: 5000,
  }));
});

test('a server that ignores stdin closing is killed after the grace period', async () => {
  const started = await startServer(fake(`
    console.log("SKILLTREE_READY port=1");
    process.stdin.on("end", () => {});
    setInterval(() => {}, 1000);
  `));
  let killed = null;
  await stopServer(started.proc, {
    graceMs: 100,
    kill: pid => { killed = pid; started.proc.kill(); },
  });
  assert.equal(killed, started.proc.pid);
});

test("a damaged database's offer of a backup parses", () => {
  assert.deepEqual(
    parseServerLine('SKILLTREE_DAMAGED backup=skilltree_20260926-100000_daily.db when=2026-09-26T10:00:00'),
    { type: 'damaged', backup: 'skilltree_20260926-100000_daily.db', when: '2026-09-26T10:00:00' });
  assert.equal(parseServerLine('SKILLTREE_DAMAGED backup= when=x'), null);
});

test('a refusal over a damaged database carries the backup it offered', async () => {
  const failed = await startServer(fake(`
    console.log("SKILLTREE_DAMAGED backup=skilltree_20260926-100000_daily.db when=2026-09-26T10:00:00");
    console.error("Skill Tree can't start: the database is damaged");
    process.exit(4);
  `)).then(() => assert.fail('it should refuse'), err => err);
  assert.equal(failed.exitCode, 4);
  assert.deepEqual(failed.restoreOffer,
    { backup: 'skilltree_20260926-100000_daily.db', when: '2026-09-26T10:00:00' });
});

test('any other refusal offers nothing', async () => {
  const failed = await startServer(fake('process.exit(6);')).then(
    () => assert.fail('it should refuse'), err => err);
  assert.equal(failed.restoreOffer, undefined);
});

test('the restore prompt says what happens to each file', () => {
  const prompt = restorePrompt({ backup: 'skilltree_20260926-100000_daily.db',
    when: '2026-09-26T10:00:00' });
  assert.match(prompt.message, /damaged/);
  assert.match(prompt.detail, /2026/);
  assert.match(prompt.detail, /kept/);
  assert.deepEqual(prompt.buttons, ['Restore the backup', 'Quit']);
  assert.equal(prompt.defaultId, 0);
  assert.equal(prompt.cancelId, 1);
});
