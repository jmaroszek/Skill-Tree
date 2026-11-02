'use strict';

// Runs the check installed copies will run, on the installer being released.
//
// An installed copy refuses an update unless it is validly signed by a name in
// its own app-update.yml (win.signtoolOptions.publisherName in
// electron-builder.yml). With no name there, it checks nothing. A wrong name
// locks that copy out of every later update, and no later release can repair
// either mistake, since a copy keeps the names it was built with. So a tag
// build stops here (.github/workflows/release.yml):
//   node build/check-update-signature.js dist

const fs = require('fs');
const path = require('path');

const INSTALLER = /^Skill-Tree-Setup-.*\.exe$/;

// What's wrong with releasing this installer, or null.
async function findProblem({ names, installer, verify }) {
  if (!names.length) {
    return 'app-update.yml names no publisher, so installed copies would not check '
      + 'signatures. Set win.signtoolOptions.publisherName in electron-builder.yml.';
  }
  const refusal = await verify(names, installer);
  return refusal ? `Installed copies would refuse ${installer}: ${refusal}` : null;
}

async function checkDist(distDir) {
  // Here, not at the top: the shell's tests run without its packages installed.
  const yaml = require('js-yaml');
  const { verifySignature } = require('electron-updater/out/windowsExecutableCodeSignatureVerifier');

  const dist = path.resolve(distDir);
  const installers = fs.readdirSync(dist).filter(name => INSTALLER.test(name));
  if (installers.length !== 1) {
    return `Expected one installer in ${dist}, found ${installers.length}.`;
  }
  const config = yaml.load(fs.readFileSync(
    path.join(dist, 'win-unpacked', 'resources', 'app-update.yml'), 'utf8'));
  return findProblem({
    names: [].concat(config.publisherName || []),
    installer: path.join(dist, installers[0]),
    verify: (names, file) => verifySignature(names, file, console),
  });
}

module.exports = { findProblem };

if (require.main === module) {
  checkDist(process.argv[2]).then(problem => {
    if (!problem) return;
    console.error(problem);
    process.exitCode = 1;
  }).catch(err => {
    console.error(err);
    process.exitCode = 1;
  });
}
