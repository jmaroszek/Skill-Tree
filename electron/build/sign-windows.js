'use strict';

// Windows code signing, whatever the signing service.
//
// electron-builder calls this for each file it signs (win.signtoolOptions.sign
// in electron-builder.yml): the app, its installer and uninstaller. The
// release workflow also runs it on the PyInstaller server before packaging:
//   node electron/build/sign-windows.js dist/skilltree-server/skilltree-server.exe
//
// The service is configured by one secret, WINDOWS_SIGN_COMMAND: the command
// that signs one file, with {file} where its path goes. For example:
//   AzureSignTool sign -kvu <vault> -kvi <id> -kvs <secret> -kvc <cert> -tr http://timestamp.digicert.com -td sha256 "{file}"
//   signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a "{file}"
// Without it nothing is signed, which suits trial builds; a tag build
// requires it (see .github/workflows/release.yml).

const { execSync } = require('child_process');

function signCommand(file, template) {
  if (!template) return null;
  return template.split('{file}').join(file);
}

function signFile(file, template = process.env.WINDOWS_SIGN_COMMAND) {
  const command = signCommand(file, template);
  if (!command) {
    console.log(`  • not signing ${file}: WINDOWS_SIGN_COMMAND is unset`);
    return false;
  }
  // The template is a repository secret and the path comes from the build;
  // neither is user input.
  execSync(command, { stdio: 'inherit' });
  return true;
}

module.exports = async function sign(configuration) {
  signFile(configuration.path);
};
module.exports.signCommand = signCommand;
module.exports.signFile = signFile;

if (require.main === module) {
  for (const file of process.argv.slice(2)) signFile(file);
}
