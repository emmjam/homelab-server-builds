'use strict';
// Actual extension transport against deployed Web/API/Ollama. No infrastructure jobs.
const assert = require('node:assert/strict');
const {Client,message} = require('../RufusVSCode/client');
const readline = require('node:readline');
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
const report = (check,details={})=>console.log(JSON.stringify({check,...details}));
async function main() {
  const input=readline.createInterface({input:process.stdin});
  const {value}=await input[Symbol.asyncIterator]().next();input.close();
  const auth=JSON.parse(value), values=new Map();
  const vault={get:async k=>values.get(k),store:async(k,v)=>values.set(k,v),delete:async k=>values.delete(k)};
  const client=new Client(auth.url,vault);
  assert.equal((await client.request('/api/conversations')).status,401);
  await client.login(auth.username,auth.password);
  try {
    const limits=(await client.api('/conversations')).limits;
    assert.equal(limits.accounting,'conservative-utf8-byte-estimate');
    assert.equal(limits.context_tokens,8192);
    const {id}=await client.api('/conversations',{});
    report('live-login-and-capabilities',{conversation:id,limits});
    const route='/conversations/'+id+'/messages';
    await assert.rejects(client.api(route,message('x'.repeat(limits.current_message_tokens+1),'')),error=>{
      assert.equal(error.status,413);assert.equal(error.code,'message_too_large');return true;
    });
    await assert.rejects(client.api(route,message('Hello','x'.repeat(limits.repository_max_bytes+1))),error=>{
      assert.equal(error.status,413);assert.equal(error.code,'repository_too_large');return true;
    });
    assert.equal((await client.api('/conversations/'+id)).messages.length,0);
    report('structured-413-rejections-no-persistence');
    const sent=[];
    async function send(content,context='') {
      const body=message(content,context), accepted=await client.api(route,body);
      const deadline=Date.now()+540000;let history, progress=false;
      report('message-accepted',{message:accepted.id,characters:content.length,repositoryBytes:Buffer.byteLength(context)});
      while(Date.now()<deadline) {
        history=await client.api('/conversations/'+id);
        const user=history.messages.find(m=>m.id===accepted.id);
        if(user.status!=='processing') {
          assert.equal(user.status,'completed',JSON.stringify(history.events.filter(e=>e.kind==='error').map(e=>e.data)));
          const reply=history.messages.find(m=>m.reply_to===accepted.id);
          assert.ok(reply?.content.trim());assert.ok(!reply.content.includes('<think>'));
          assert.equal(user.content,content);assert.equal(user.repository_context,context);
          assert.equal(history.actions.length,0);
          const usage=history.events.filter(e=>e.kind==='context_budget').at(-1)?.data;
          report('message-completed',{message:accepted.id,replyCharacters:reply.content.length,progressObserved:progress,usage});
          sent.push(accepted.id);return {history,reply:reply.content,usage};
        }
        if(!progress&&history.events.some(e=>e.kind==='progress')) {progress=true;report('live-progress-observed',{message:accepted.id});}
        await delay(2500);
      }
      throw new Error('Live conversation exceeded its acceptance deadline; inspect persisted history before any retry.');
    }
    const prose='This is harmless sample prose about a fictional garden. ';
    const long='Ordinary conversation only. Please reply with just READY. '+prose.repeat(48)+' End of sample prose. Reply with just READY.';
    assert.ok(long.length>2048&&Buffer.byteLength(long)<=limits.current_message_tokens);
    const repo='File: acceptance-example.txt\nLanguage: plaintext\nThe fictional garden name is Willow.\n';
    const first=await send(long,repo);
    assert.ok(first.usage.repository_bytes_used>0);
    const follow=await send('What is the fictional garden name in this attached file? Reply with just its name.',repo);
    assert.match(follow.reply,/willow/i);
    const remembered=await send('Which fictional garden name did we just discuss? Reply with just its name.');
    assert.match(remembered.reply,/willow/i);
    assert.ok(remembered.usage.history_exchanges_used>0);
    const restored=new Client(auth.url,vault);await restored.restore();
    const saved=await restored.api('/conversations/'+id);
    assert.ok(sent.every(mid=>saved.messages.some(m=>m.reply_to===mid)));
    report('persistent-conversation-restored',{conversation:id,messages:sent.length});
    await assert.rejects(client.api('/executions',{operation:'apt-cache-restart',options:{}}),e=>e.status===403);
    assert.equal((await client.request('/api/executions',{},client.session.cookie,'')).status,403);
    assert.equal((await client.request('/api/commands',{},client.session.cookie,client.session.csrf)).status,404);
    await assert.rejects(client.api('/actions/00000000-0000-0000-0000-000000000000/decision',{
      conversation_id:id,proposal_hash:'unapproved',decision:'approve'}),e=>e.status===404||e.status===409);
    report('sensitive-direct-operation-csrf-command-and-forged-approval-denied');
    const previous=restored.session;
    await client.logout();
    assert.equal((await restored.request('/api/conversations',undefined,previous.cookie,previous.csrf)).status,401);
    report('logout-revocation');
    report('PASS',{conversation:id,limitation:'Transport/API acceptance, not interactive VS Code visual acceptance; no real repair proposal was created.'});
  } finally {if(client.session)await client.logout();}
}
main().catch(error=>{console.error(JSON.stringify({check:'FAIL',message:error.message,code:error.code}));process.exitCode=1;});
