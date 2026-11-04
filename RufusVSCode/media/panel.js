'use strict';
const vscode=acquireVsCodeApi(), $=id=>document.getElementById(id);
let submitting=false,processing=false,lastRendered=null;
const send=data=>vscode.postMessage(data);
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
function updateBusy(){$('send').disabled=submitting||processing;}
function signedIn(value){$('login').hidden=value;$('logout').hidden=!value;}
function render(state){
  const serialised=JSON.stringify(state);if(serialised===lastRendered)return;lastRendered=serialised;
  const transcript=$('transcript'),nearBottom=transcript.scrollTop+transcript.clientHeight>=transcript.scrollHeight-80;
  const opened=new Set([...document.querySelectorAll('details[data-key][open]')].map(d=>d.dataset.key));
  signedIn(true);$('connection').textContent=state.origin;
  $('conversations').replaceChildren(node('option','New conversation'));$('conversations').firstChild.value='';
  for(const c of state.conversations){const option=node('option',c.title);option.value=c.id;option.selected=c.id===state.selected;$('conversations').append(option);}
  const history=state.history;
  processing=!!history?.messages.some(m=>m.status==='processing');updateBusy();
  const entries=[...(history?.messages||[]).map(m=>({...m,kind:'message'})),...(history?.events||[]).filter(e=>e.kind==='response').map(e=>({role:'assistant',content:e.data.text,created:e.created}))].sort((a,b)=>a.created-b.created);
  $('messages').replaceChildren();$('events').replaceChildren();$('actions').replaceChildren();$('executions').replaceChildren();
  for(const m of entries){const card=node('article',undefined,'message '+(m.role==='assistant'?'assistant':'user'));card.append(node('h2',m.role==='assistant'?'Rufus':'You'),node('pre',m.content));
    if(m.repository_context){const detail=node('details',undefined,'repository');detail.dataset.key='repository-'+m.id;detail.open=opened.has(detail.dataset.key);detail.append(node('summary','Attached repository context'),node('pre',m.repository_context));card.append(detail);}
    if(['failed','interrupted'].includes(m.status))card.append(node('small',m.status+' · message retained'));
    $('messages').append(card);
  }
  for(const event of history?.events||[]){if(event.kind==='response')continue;const detail=node('details');detail.dataset.key='event-'+event.id;detail.open=opened.has(detail.dataset.key);detail.append(node('summary',event.kind+' · '+new Date(event.created*1000).toLocaleTimeString()),node('pre',JSON.stringify(event.data,null,2)));$('events').append(detail);}
  for(const action of state.actions){
    const spec=action.proposal.proposal,card=node('article',undefined,'approval');
    card.append(node('h2',action.status==='pending'?'Approval required':'Operation · '+action.status),node('p',spec.change),node('p','Risks: '+spec.risks));
    const detail=node('details');detail.dataset.key='action-'+action.id;detail.open=opened.has(detail.dataset.key);detail.append(node('summary','Exact operation and approval details'),node('pre',JSON.stringify({proposal:spec,hash:action.proposal_hash,expires:new Date(action.expires*1000).toLocaleString(),execution_id:action.execution_id,verification_id:action.verification_id},null,2)));card.append(detail);
    if(action.status==='pending')for(const decision of ['approve','reject']){const button=node('button',decision==='approve'?'Review and approve…':'Reject…');button.disabled=Date.now()>=action.expires*1000;button.onclick=()=>send({type:'decision',id:action.id,decision});card.append(button);}
    $('actions').append(card);
  }
  for(const execution of state.executions){const detail=node('details');detail.dataset.key='execution-'+execution.execution_id;detail.open=opened.has(detail.dataset.key);detail.append(node('summary','Execution '+execution.execution_id+' · '+execution.status),node('pre',JSON.stringify(execution,null,2)));$('executions').append(detail);}
  const recent=(history?.events||[]).filter(e=>['progress','error','outcome','context_budget'].includes(e.kind)).at(-1);
  $('progress').textContent=processing?'Rufus · '+(recent?.data.status||'Thinking')+'…':recent?.kind==='error'?recent.data.message:recent?.kind==='context_budget'&&recent.data.repository_shortened?'Repository excerpt shortened by Rufus; details in activity.':'';
  $('activity').hidden=!history?.events.length&&!state.executions.length;
  $('welcome').hidden=!!entries.length;$('welcome').textContent='Start a conversation with Rufus.';
  $('budget').textContent=state.limits?state.limits.context_tokens.toLocaleString()+' token window':'Backend limits apply';
  $('budget').title=state.limits?'Backend accounting: '+state.limits.accounting+'. Up to '+state.limits.repository_context_tokens+' estimated units for repository context; '+state.limits.generation_tokens+' tokens reserved for output, plus system/workflow headroom. Full current message preserved.':'Backend limits apply; full current message preserved.';
  if(nearBottom)transcript.scrollTop=transcript.scrollHeight;
}
window.addEventListener('message',event=>{const data=event.data;
  if(data.type==='state')render(data);
  if(data.type==='error'){$('error').hidden=false;$('error').textContent=data.message;}
  if(data.type==='busy'){submitting=data.value;updateBusy();}
  if(data.type==='sent'){$('message').value='';$('error').hidden=true;}
  if(data.type==='context'){$('context').textContent=data.text;$('attachment').hidden=!data.text;$('context-summary').textContent='Review excerpt · '+new TextEncoder().encode(data.text).length.toLocaleString()+' UTF-8 bytes';}
  if(data.type==='signedOut'){lastRendered=null;processing=false;updateBusy();signedIn(false);$('connection').textContent='Signed out';for(const id of ['messages','events','actions','executions'])$(id).replaceChildren();$('conversations').replaceChildren();$('welcome').hidden=false;$('welcome').textContent='Sign in from the ⋯ menu to continue your conversations.';$('activity').hidden=true;}
});
for(const button of document.querySelectorAll('[data-command]'))button.onclick=()=>send({type:button.dataset.command});
$('conversations').onchange=()=>{if($('conversations').value)send({type:'select',id:$('conversations').value});};
$('composer').onsubmit=event=>{event.preventDefault();if(!submitting&&!processing){$('error').hidden=true;send({type:'send',content:$('message').value});}};
$('message').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('composer').requestSubmit();}};
vscode.setState({open:true});send({type:'ready'});
