'use strict';
const csrf = document.querySelector('meta[name=csrf-token]').content;
const $ = id => document.getElementById(id);
let selected = null, polling = null, revision = 0, busy = false, submitting = false;
function showError(error) { $('error').hidden = false; $('error').textContent = error.message || String(error); }
function clearError() { $('error').hidden = true; }
async function api(path, body) {
  const response = await fetch('/api' + path, {method: body === undefined ? 'GET' : 'POST', headers: {'Content-Type':'application/json','X-CSRF-Token':csrf}, body: body === undefined ? undefined : JSON.stringify(body), credentials:'same-origin'});
  const data = await response.json();
  if (!response.ok) { if (response.status === 401) { location.href = '/'; } throw new Error(data.error || 'Request failed'); }
  return data;
}
function node(tag, text, cls) { const el=document.createElement(tag); if(text!==undefined) el.textContent=text; if(cls) el.className=cls; return el; }
async function list() {
  const data=await api('/conversations'); $('conversations').replaceChildren();
  for(const conversation of data.conversations) { const b=node('button',conversation.title,conversation.id===selected?'active':''); b.type='button'; b.title=conversation.title; b.onclick=()=>select(conversation.id); $('conversations').append(b); }
  return data.conversations;
}
function actionCard(action) {
  const spec=action.proposal.proposal;
  const card=node('article',undefined,'action');card.append(node('h2',action.status==='pending'?'Approval required':'Operation · '+action.status));
  card.append(node('p',spec.change),node('p',spec.summary),node('p','Expected effect: '+spec.expected_effect),node('p','Risks: '+spec.risks));
  card.append(node('pre',JSON.stringify({operation:spec.operation,target:spec.target,parameters:spec.parameters,job_id:spec.job_id,action_id:action.id,proposal_hash:action.proposal_hash,expires:new Date(action.expires*1000).toLocaleString()},null,2)));
  if(action.execution_id) card.append(node('p','Repair execution: '+action.execution_id));
  if(action.verification_id) card.append(node('p','Verification execution: '+action.verification_id));
  if(action.status==='pending') {
    const buttons=node('div',undefined,'buttons');
    for(const decision of ['approve','reject']) {
      const b=node('button',decision==='approve'?'Approve exact operation':'Reject',decision==='reject'?'reject':'');b.type='button';b.disabled=Date.now()>=action.expires*1000;
      b.onclick=async()=>{
        if(!confirm((decision==='approve'?'Approve':'Reject')+' this exact operation?\n'+spec.change+'\n'+spec.operation+' '+JSON.stringify(spec.parameters)+'\n'+spec.risks))return;
        buttons.querySelectorAll('button').forEach(button=>button.disabled=true);
        try { await api('/actions/'+action.id+'/decision',{conversation_id:action.conversation,proposal_hash:action.proposal_hash,decision}); await refresh(); }
        catch(error) { showError(error); }
      };buttons.append(b);
    }card.append(buttons);
  }
  return card;
}
async function refresh() {
  if(!selected)return;
  const id=selected,version=revision;
  const history=await api('/conversations/'+id);
  if(version!==revision)return;
  // Action GET resumes only the existing AI2 execution monitor; it cannot approve.
  const actions=await Promise.all(history.actions.map(action=>api('/actions/'+action.id)));
  if(version!==revision)return;
  const nearBottom=window.innerHeight+window.scrollY>=document.body.scrollHeight-160;
  const messages=$('messages');messages.replaceChildren();
  for(const message of history.messages) {
    const article=node('article',undefined,'message '+(message.role||'user'));
    article.append(node('div',message.role==='assistant'?'RUFUS':'YOU','label'),node('div',message.content,'text'));
    if(message.status==='failed'||message.status==='interrupted') article.append(node('small',message.status+' · Your message has been retained.'));
    messages.append(article);
  }
  for(const event of history.events.filter(e=>e.kind==='response')) { const article=node('article',undefined,'message assistant');article.append(node('div','RUFUS','label'),node('div',event.data.text,'text'));messages.append(article); }
  $('actions').replaceChildren(...actions.map(actionCard));
  busy=history.messages.some(message=>message.status==='processing');$('send').disabled=busy||submitting;
  const recent=history.events.filter(e=>['progress','error','outcome','approval_required'].includes(e.kind)).slice(-1)[0];
  $('progress').textContent=busy?'Rufus is '+(recent?.data.status||'thinking')+'…':actions.some(a=>a.status==='pending')?'Review the proposed operation below.':recent?.kind==='error'?recent.data.message:'Ready for your next message.';
  if(nearBottom)window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});
}
async function select(id) {
  revision++;selected=id;location.hash=id;clearError();clearInterval(polling);
  try { await list();await refresh();polling=setInterval(()=>refresh().catch(showError),2500); }
  catch(error) {showError(error);}
}
$('new').onclick=async()=>{try { const conversation=await api('/conversations',{});await select(conversation.id);$('message').focus(); }catch(error){showError(error);}};
$('composer').onsubmit=async event=>{
  event.preventDefault();if(busy||submitting)return;
  const content=$('message').value.trim();if(!content)return;
  submitting=true;$('send').disabled=true;clearError();
  try {
    if(!selected){const conversation=await api('/conversations',{});await select(conversation.id);}
    await api('/conversations/'+selected+'/messages',{request_id:crypto.randomUUID(),content});$('message').value='';await list();await refresh();
  }catch(error){showError(error);}finally{submitting=false;$('send').disabled=busy;}
};
$('message').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('composer').requestSubmit();}};
$('logout').onclick=async()=>{await fetch('/logout',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'});location.href='/';};
(async()=>{try{const conversations=await list();const requested=location.hash.slice(1);if(conversations.length)await select(conversations.some(c=>c.id===requested)?requested:conversations[0].id);}catch(error){showError(error);}})();
