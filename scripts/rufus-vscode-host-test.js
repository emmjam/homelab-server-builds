'use strict';
// Real VS Code extension-host acceptance, run with --extensionTestsPath.
// Uses a disposable profile; does not claim visual or normal-profile acceptance.
const vscode=require('vscode'),assert=require('node:assert/strict');
const fs=require('node:fs');
const report=check=>console.log(JSON.stringify({check}));
async function findTab() {
  for(let n=0;n<100;n++) {
    const tab=vscode.window.tabGroups.all.flatMap(group=>group.tabs).find(tab=>
      tab.input instanceof vscode.TabInputWebview && tab.input.viewType.includes('rufus.chat'));
    if(tab)return tab;
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  throw new Error('Rufus webview tab did not appear');
}
exports.run=async function() {
  const extension=vscode.extensions.getExtension('emmjam.rufus-chat');
  assert.ok(extension,'Installed extension is not recognised');
  assert.equal(extension.packageJSON.version,'0.2.0');
  assert.equal(JSON.parse(fs.readFileSync(extension.extensionPath+'/package.json','utf8')).version,'0.2.0');
  await extension.activate();assert.ok(extension.isActive);report('real-host-0.2.0-activation');
  assert.ok((await vscode.commands.getCommands(true)).includes('rufus.open'));report('real-host-command-registered');
  await vscode.commands.executeCommand('rufus.open');
  const first=await findTab();assert.equal(first.label,'Rufus');report('real-host-webview-opened');
  assert.ok(await vscode.window.tabGroups.close(first));
  await vscode.commands.executeCommand('rufus.open');
  const reopened=await findTab();assert.equal(reopened.label,'Rufus');report('real-host-webview-reopened');
  await vscode.window.tabGroups.close(reopened);
  report('PASS-real-host-lifecycle-not-visual-acceptance');
};
