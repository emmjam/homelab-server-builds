'use strict';
const vscode = require('vscode');
const fs = require('node:fs');
const crypto = require('node:crypto');
const {Client, message, uuid, origin} = require('./client');

function contextText(editor, mode, workspace, limits) {
  if (!limits) throw new Error('Refresh to obtain backend context capabilities before attaching a file.');
  if (!workspace.isTrusted) throw new Error('Trust the workspace before attaching context.');
  if (!editor || editor.document.uri.scheme !== 'file' || !workspace.getWorkspaceFolder(editor.document.uri)) throw new Error('Open a file inside the current workspace first.');
  const name = workspace.asRelativePath(editor.document.uri);
  if (/(^|[/\\])(?:\.env(?:\..*)?|secrets?(?:\..*)?|credentials?(?:\..*)?|id_(?:rsa|ed25519)(?:\..*)?)$|\.(?:pem|key|p12|pfx)$/i.test(name)) throw new Error('Credential files cannot be attached.');
  const metadata = 'File: '+name+'\nLanguage: '+editor.document.languageId+'\nUnsaved edits: '+editor.document.isDirty;
  if (mode === 'Repository/file details only') return metadata;
  const raw = mode === 'Current selection' ? editor.document.getText(editor.selection) : editor.document.getText();
  if (!raw) throw new Error('Select some text first.');
  if (/-----BEGIN .*PRIVATE KEY-----|\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b/.test(raw)) throw new Error('Recognised credential material cannot be attached.');
  // Prefer selected text; for whole files use a line-aligned window around the cursor.
  const lines=raw.split('\n'), cursor=mode==='Current selection'?0:editor.selection.start.line;
  const window=lines.slice(Math.max(0,cursor-20),cursor+81).join('\n');
  const source=Buffer.byteLength(raw,'utf8')<=limits.repository_max_bytes?raw:window;
  let text='';for(const character of source){if(Buffer.byteLength(text+character,'utf8')>Math.max(0,limits.repository_max_bytes-256-Buffer.byteLength(metadata,'utf8')))break;text+=character;}
  const shortened=text!==raw;
  if(shortened)text+='\n[… repository excerpt; remaining content omitted …]';
  return metadata+'\n'+(mode === 'Current selection' ? 'Selection lines: '+(editor.selection.start.line+1)+'–'+(editor.selection.end.line+1) : shortened ? 'Active file excerpt around cursor' : 'Whole active file')+'\n'+text;
}
function activate(context) {
  let panel, timer, client, selected, attachment = '', refreshing = false, submitting = false;
  let observedExecutions = new Set(), backendLimits;
  let lastEditor = vscode.window.activeTextEditor;
  const post = data => panel?.webview.postMessage(data);
  const stop = () => { clearInterval(timer); timer = undefined; };
  const guard = async fn => { try { await fn(); } catch (error) { post({type:'error', message:error.message}); } };
  async function connect() {
    const url = origin(vscode.workspace.getConfiguration('rufus').get('serverUrl'));
    if (!client || client.url !== url) {
      client = new Client(url, context.secrets); await client.restore();
      selected = context.globalState.get('conversation.'+client.url);
      observedExecutions = new Set(context.globalState.get('executions.'+client.url, []));
    }
    return client;
  }
  async function refresh() {
    if (!panel || refreshing) return;
    refreshing = true;
    try {
      const current = await connect();
      if (!current.session) { post({type:'signedOut'}); return; }
      const snapshotSelected = selected;
      const conversations = await current.api('/conversations');
      backendLimits=conversations.limits;
      let history = null, actions = [], executions = [];
      if (snapshotSelected && conversations.conversations.some(c => c.id === snapshotSelected)) {
        history = await current.api('/conversations/'+snapshotSelected);
        actions = await Promise.all(history.actions.map(a => current.api('/actions/'+a.id)));
        for (const event of history.events) if (Number.isSafeInteger(event.data?.execution_id)) observedExecutions.add(event.data.execution_id);
        for (const action of actions) for (const id of [action.execution_id,action.verification_id]) if (Number.isSafeInteger(id)) observedExecutions.add(id);
      } else if (selected === snapshotSelected) { selected = undefined; }
      // Bound both persisted IDs and polling overhead; arbitrary execution IDs cannot be requested.
      observedExecutions = new Set([...observedExecutions].slice(-10));
      for (const id of observedExecutions) {
        try { executions.push(await current.api('/executions/'+id)); }
        catch { executions.push({execution_id:id,status:'unavailable',failure:'Execution monitoring unavailable; no operation was retried.'}); }
      }
      await context.globalState.update('executions.'+current.url,[...observedExecutions]);
      if (client === current && selected === snapshotSelected) post({type:'state', origin:current.url, selected, conversations:conversations.conversations, history, actions, executions,limits:backendLimits});
    } finally { refreshing = false; }
  }
  async function choose(id) {
    if (!uuid.test(id)) throw new Error('Invalid conversation.');
    selected = id; attachment = ''; post({type:'context', text:''});
    await context.globalState.update('conversation.'+client.url,id); await refresh();
  }
  async function receive(data) {
    if (!data || typeof data.type !== 'string') return;
    if (data.type === 'ready' || data.type === 'refresh') { await refresh(); return; }
    if (data.type === 'login') {
      await connect();
      const username = await vscode.window.showInputBox({title:'Rufus username',ignoreFocusOut:true}); if (!username) return;
      const password = await vscode.window.showInputBox({title:'Rufus password · '+client.url,password:true,ignoreFocusOut:true}); if (password === undefined) return;
      await client.login(username,password); await refresh(); return;
    }
    if (data.type === 'logout') { await connect(); await client.logout(); attachment='';post({type:'context',text:''});post({type:'signedOut'}); return; }
    await connect();
    if (!client.session) throw new Error('Sign in to Rufus first.');
    if (data.type === 'new') { const conversation = await client.api('/conversations',{}); await choose(conversation.id); }
    else if (data.type === 'select') { await choose(data.id); }
    else if (data.type === 'clearContext') { attachment = ''; post({type:'context',text:''}); }
    else if (data.type === 'attach') {
      const editor = vscode.window.activeTextEditor || lastEditor;
      const mode = await vscode.window.showQuickPick(['Current selection','Whole active file','Repository/file details only'],{title:'Explicitly attach context to the next message'});
      if (mode) { attachment = contextText(editor,mode,vscode.workspace,backendLimits); post({type:'context',text:attachment}); }
    }
    else if (data.type === 'send') {
      if (submitting || typeof data.content !== 'string') return;
      const body = message(data.content,attachment,backendLimits);
      submitting = true; post({type:'busy',value:true});
      try {
        if (!selected) { const conversation = await client.api('/conversations',{}); await choose(conversation.id); }
        await client.api('/conversations/'+selected+'/messages',body);
        attachment = ''; post({type:'sent'}); post({type:'context',text:''}); await refresh();
      } finally { submitting = false; post({type:'busy',value:false}); }
    }
    else if (data.type === 'decision') {
      if (!uuid.test(data.id || '') || !['approve','reject'].includes(data.decision)) throw new Error('Invalid decision.');
      const action = await client.api('/actions/'+data.id);
      if (action.conversation !== selected || action.status !== 'pending' || Date.now() >= action.expires*1000) throw new Error('Proposal changed or expired. Refresh the conversation.');
      const details = JSON.stringify({proposal:action.proposal.proposal,proposal_hash:action.proposal_hash,expires:new Date(action.expires*1000).toISOString()},null,2);
      const label = data.decision === 'approve' ? 'Approve exact operation' : 'Reject operation';
      if (await vscode.window.showWarningMessage(label+'?',{modal:true,detail:details},label) !== label) return;
      await client.api('/actions/'+action.id+'/decision',{conversation_id:action.conversation,proposal_hash:action.proposal_hash,decision:data.decision}); await refresh();
    }
    else if (data.type === 'operation') {
      const {jobs} = await client.api('/jobs');
      const picked = await vscode.window.showQuickPick(jobs.map(job=>({label:job.operation,description:job.name,job})),{title:'Backend-approved operations · sensitive changes still require chat approval'});
      if (!picked) return;
      const options = {};
      for (const [name,rule] of Object.entries(picked.job.options)) {
        const value = await vscode.window.showInputBox({title:'Operation parameter: '+name,prompt:rule.required?'Required':'Optional'});
        if (value === undefined) return;
        if (value || rule.required) options[name] = value;
      }
      if (await vscode.window.showWarningMessage('Submit this approved operation?',{modal:true,detail:JSON.stringify({operation:picked.job.operation,options},null,2)},'Submit') !== 'Submit') return;
      const result = await client.api('/executions',{operation:picked.job.operation,options});
      observedExecutions.add(result.execution_id); await refresh();
    }
  }
  function initialise(view) {
    panel = view;
    view.webview.options = {enableScripts:true,localResourceRoots:[vscode.Uri.joinPath(context.extensionUri,'media')]};
    const nonce = crypto.randomBytes(24).toString('hex');
    const asset = name => view.webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri,'media',name)).toString();
    view.webview.html = fs.readFileSync(context.asAbsolutePath('media/index.html'),'utf8')
      .replaceAll('{{NONCE}}',nonce).replaceAll('{{CSP}}',view.webview.cspSource)
      .replace('{{SCRIPT}}',asset('panel.js')).replace('{{STYLE}}',asset('panel.css'));
    view.webview.onDidReceiveMessage(data=>guard(()=>receive(data)),undefined,context.subscriptions);
    view.onDidDispose(()=>{stop();panel=undefined;attachment='';},undefined,context.subscriptions);
    stop(); timer = setInterval(()=>guard(refresh),2500);
  }
  context.subscriptions.push(vscode.commands.registerCommand('rufus.open',()=>{
    if (panel) panel.reveal(); else initialise(vscode.window.createWebviewPanel('rufus.chat','Rufus',vscode.ViewColumn.Beside,{enableScripts:true}));
  }));
  context.subscriptions.push(vscode.window.registerWebviewPanelSerializer('rufus.chat',{async deserializeWebviewPanel(view) { initialise(view); }}));
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(event=>{
    if (event.affectsConfiguration('rufus.serverUrl')) { attachment='';client=undefined;selected=undefined;post({type:'context',text:''});guard(refresh); }
  }));
  context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(editor=>{if(editor)lastEditor=editor;}));
  context.subscriptions.push({dispose:stop});
}
module.exports = {activate,contextText};
