'use strict';

// Starting and stopping the Python server, and reading its handshake.
//
// The server prints one line on stdout once it can answer:
//   SKILLTREE_READY port=<n>
// or, when another Skill Tree already owns this data, prints
//   SKILLTREE_RUNNING port=<n> token=<t>
// and exits with code 8. Any other exit before that is a refusal, and its
// code says why (docs/app_architecture.md lists them).
//
// The shell keeps the server's stdin open. Closing it asks the server to
// finish what it is doing and exit, and a crashed shell closes it too, so the
// server never outlives the window.

const { spawn } = require('child_process');
const crypto = require('crypto');

const EXIT_MESSAGES = {
  2: "Skill Tree couldn't open its data file.",
  3: 'Your Skill Tree data was saved by a newer version of Skill Tree. '
    + 'Install that version to open it. Nothing was changed.',
  4: 'Your Skill Tree data file is damaged. Nothing was changed. Backups are '
    + 'in the Backups folder beside it.',
  5: "This build of Skill Tree can't open its data because its SQLite is too old.",
  6: 'Your Skill Tree data file is in use by another program, such as a backup '
    + 'or sync tool. Close it and start Skill Tree again.',
  7: "Skill Tree can't write to its data folder. It may be read-only, or the "
    + 'disk may be full.',
  8: 'Skill Tree is already running, but it isn\'t answering.',
};

function parseServerLine(line) {
  const ready = /^SKILLTREE_READY port=(\d+)\s*$/.exec(line);
  if (ready) return { type: 'ready', port: Number(ready[1]) };
  const running = /^SKILLTREE_RUNNING port=(\d+) token=(\S*)\s*$/.exec(line);
  if (running) return { type: 'running', port: Number(running[1]), token: running[2] };
  return null;
}

// What to tell the user when the server exits before it is ready. The
// server's own last words (stderr) are the detail: they name the file.
function exitMessage(code, detail) {
  const base = EXIT_MESSAGES[code]
    || `Skill Tree's server stopped unexpectedly (exit code ${code}).`;
  const last = (detail || '').trim().split(/\r?\n/).filter(Boolean).pop();
  return last ? `${base}\n\n${last}` : base;
}

function newToken() {
  return crypto.randomBytes(32).toString('base64url');
}

function appUrl(port, token) {
  return `http://127.0.0.1:${port}/?token=${encodeURIComponent(token)}`;
}

// Resolves { proc, port } once the server is READY, or
// { proc, port, token, alreadyRunning: true } when another server owns the
// data. Rejects with an Error carrying exitCode and stderrTail if the server
// exits first, or timedOut (after killing it) if it isn't ready within
// timeoutMs.
function startServer({ command, args, cwd, env, timeoutMs = 90000, log = () => {} }) {
  return new Promise((resolve, reject) => {
    const proc = spawn(command, args, {
      cwd, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    });
    let settled = false;
    let pending = '';
    let stderrTail = '';
    const timer = setTimeout(() => {
      fail(Object.assign(new Error('The server did not start in time.'), { timedOut: true }));
      proc.kill();  // it is no use now, and must not outlive the shell
    }, timeoutMs);

    function succeed(value) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    }
    function fail(err) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      err.stderrTail = stderrTail;
      reject(err);
    }

    proc.stdout.setEncoding('utf8');
    proc.stdout.on('data', chunk => {
      log(chunk);
      pending += chunk;
      let end;
      while ((end = pending.indexOf('\n')) >= 0) {
        const parsed = parseServerLine(pending.slice(0, end).replace(/\r$/, ''));
        pending = pending.slice(end + 1);
        if (parsed && parsed.type === 'ready') {
          succeed({ proc, port: parsed.port });
        } else if (parsed && parsed.type === 'running') {
          succeed({ proc, port: parsed.port, token: parsed.token, alreadyRunning: true });
        }
      }
    });
    proc.stderr.setEncoding('utf8');
    proc.stderr.on('data', chunk => {
      log(chunk);
      stderrTail = (stderrTail + chunk).slice(-4000);
    });
    // e.g. the interpreter or the server binary isn't there.
    proc.on('error', err => fail(err));
    // 'close', not 'exit': it waits for stdout, so a READY or RUNNING line
    // printed just before exiting is read first.
    proc.on('close', code => {
      fail(Object.assign(new Error(`The server exited with code ${code}.`), { exitCode: code }));
    });
  });
}

function defaultKill(pid) {
  // Loaded here so the tests needn't install it.
  require('tree-kill')(pid);
}

// Ask the server to stop by closing its stdin; kill it if it hasn't exited
// within graceMs. Resolves once it is gone either way.
function stopServer(proc, { graceMs = 5000, kill = defaultKill } = {}) {
  return new Promise(resolve => {
    if (!proc || proc.exitCode !== null || proc.signalCode !== null) {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      kill(proc.pid);
      resolve();
    }, graceMs);
    proc.once('exit', () => {
      clearTimeout(timer);
      resolve();
    });
    try {
      proc.stdin.end();
    } catch (err) {
      // Already closed: the exit handler resolves.
    }
  });
}

module.exports = {
  EXIT_MESSAGES, appUrl, exitMessage, newToken, parseServerLine, startServer, stopServer,
};
