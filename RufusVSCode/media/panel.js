'use strict';
const vscode = acquireVsCodeApi();
const $ = id => document.getElementById(id);
let submitting = false, processing = false, lastRendered = null;
const send = data => vscode.postMessage(data);
function node(tag,text) { const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el; }
function updateBusy() { $('send').disabled = submitting || processing; }
function render(state) {
  const serialised=JSON.stringify(state);if(serialised===lastRendered)return;lastRendered=serialised;
  const opened=new Set([...document.querySelectorAll('details[data-key][open]')].map(detail=>detail.dataset.key));
  $('connection').textContent='Connected to '+state.origin;
  $('conversations').replaceChildren(node('option','Choose a conversation'));
  $('conversations').firstChild.value='';
  for(const conversation of state.conversations) { const option=node('option',conversation.title);option.value=conversation.id;option.selected=conversation.id===state.selected;$('conversations').append(option); }
  const history=state.history;
  $('messages').replaceChildren();$('events').replaceChildren();$('actions').replaceChildren();$('executions').replaceChildren();
  processing=!!history?.messages.some(m=>m.status==='processing');updateBusy();
  for(const m of history?.messages || []) { const card=node('article');card.append(node('h2',m.role==='assistant'?'Rufus':'You'),node('pre',m.content),node('small',m.status || ''));$('messages').append(card); }
  for(const event of history?.events || []) {
    if(event.kind==='response') { const card=node('article');card.append(node('h2','Rufus'),node('pre',event.data.text));$('messages').append(card); }
    else { const detail=node('details');detail.dataset.key='event-'+event.id;detail.open=opened.has(detail.dataset.key);detail.append(node('summary',event.kind+' · '+new Date(event.created*1000).toLocaleString()),node('pre',JSON.stringify(event.data,null,2)));$('events').append(detail); }
  }
  for(const action of state.actions) {
    const card=node('article');card.append(node('h2','Operation · '+action.status),node('pre',JSON.stringify({proposal:action.proposal.proposal,hash:action.proposal_hash,expires:new Date(action.expires*1000).toLocaleString(),execution_id:action.execution_id,verification_id:action.verification_id},null,2)));
    if(action.status==='pending') for(const decision of ['approve','reject']) { const button=node('button',decision==='approve'?'Approve exact operation…':'Reject…');button.disabled=Date.now()>=action.expires*1000;button.onclick=()=>send({type:'decision',id:action.id,decision});card.append(button); }
    $('actions').append(card);
  }
  for(const execution of state.executions) { const detail=node('details');detail.dataset.key='execution-'+execution.execution_id;detail.open=opened.has(detail.dataset.key);detail.append(node('summary','Execution '+execution.execution_id+' · '+execution.status),node('pre',JSON.stringify(execution,null,2)));$('executions').append(detail); }
  $('progress').textContent=processing?'Rufus is processing. Saved progress updates appear below the messages.':'Ready. Progress/results refresh every 2.5 seconds; there is no token-by-token stream.';
}
window.addEventListener('message',event=>{
  const data=event.data;
  if(data.type==='state')render(data);
  if(data.type==='error') { $('error').hidden=false;$('error').textContent=data.message; }
  if(data.type==='busy') {submitting=data.value;updateBusy();}
  if(data.type==='sent') { $('message').value='';$('error').hidden=true; }
  if(data.type==='context') { $('context').textContent=data.text;$('attachment').open=!!data.text;$('attachment').querySelector('summary').textContent=data.text?'Context for the next message · review before sending':'Context for the next message (nothing attached)'; }
  if(data.type==='signedOut') { lastRendered=null;processing=false;updateBusy();$('connection').textContent='Signed out. Sign in to your existing Rufus account.';for(const id of ['messages','events','actions','executions'])$(id).replaceChildren();$('conversations').replaceChildren(); }
});
for(const button of document.querySelectorAll('[data-command]'))button.onclick=()=>send({type:button.dataset.command});
$('conversations').onchange=()=>{if($('conversations').value)send({type:'select',id:$('conversations').value});};
$('composer').onsubmit=event=>{event.preventDefault();if(!submitting&&!processing){$('error').hidden=true;send({type:'send',content:$('message').value});}};
vscode.setState({open:true});send({type:'ready'});
