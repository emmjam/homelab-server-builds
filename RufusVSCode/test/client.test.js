'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {createInterface} = require('node:readline');
const http = require('node:http');
const path = require('node:path');
const {Client,origin,route,message} = require('../client');
function secrets() { const data=new Map();return {data,get:async k=>data.get(k),store:async(k,v)=>data.set(k,v),delete:async k=>data.delete(k)}; }
test('configured origin and route allowlists reject credential URLs, redirects and arbitrary paths',()=>{
  for(const url of ['file:///etc/passwd','http://user:pass@host','http://host/path','http://host/?token=x'])assert.throws(()=>origin(url));
  for(const [p,b] of [['https://evil/'],['/jobs',{}],['/executions/0'],['/executions/1?wait=30'],['/commands',{}]])assert.throws(()=>route(p,b));
  assert.doesNotThrow(()=>route('/jobs'));assert.doesNotThrow(()=>route('/executions/12'));
});
test('explicit context is bounded and request identity is generated without automatic context',()=>{
  assert.equal(message('Hello','').content,'Hello');assert.equal(message('Hello','File: one').repository_context,'File: one');
  assert.equal(message('x'.repeat(3000),'y',{message_max_bytes:5000}).content.length,3000);assert.throws(()=>message('x'.repeat(5001),'',{message_max_bytes:5000}),/not truncated/);assert.throws(()=>message('',''));
  assert.notEqual(message('Hello','').request_id,message('Hello','').request_id);
});
test('transport never follows redirects or retries ambiguous POSTs and clears expired sessions',async t=>{
  let count=0,mode='redirect';
  const server=http.createServer((req,res)=>{count++;if(mode==='disconnect'){req.socket.destroy();return;}res.writeHead(mode==='expired'?401:302,{Location:'http://127.0.0.1:9/steal'});res.end('{}');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>{server.closeAllConnections();server.close();});
  const client=new Client('http://127.0.0.1:'+server.address().port,secrets());client.session={cookie:'test',csrf:'test'};
  await assert.rejects(client.api('/conversations'));assert.equal(count,1);
  mode='disconnect';await assert.rejects(client.api('/executions',{}),/No POST was retried/);assert.equal(count,2);
  mode='expired';await assert.rejects(client.api('/conversations'),/expired/);assert.equal(client.session,null);
});
test('actual Web/Auth/API/SQLite end-to-end: chat, restored session/history, operation logs and exact approval/rejection',async t=>{
  const backend=spawn('python3',[path.join(__dirname,'backend.py')],{stdio:['pipe','pipe','pipe']});
  let diagnostic='';backend.stderr.on('data',data=>diagnostic+=data);
  t.after(()=>{backend.stdin.end('stop\n');setTimeout(()=>backend.kill(),1500).unref();});
  const lines=createInterface({input:backend.stdout});const iterator=lines[Symbol.asyncIterator]();
  const first=await iterator.next();assert.ok(!first.done,diagnostic);const fixture=JSON.parse(first.value);
  const vault=secrets(),client=new Client(fixture.url,vault);
  await assert.rejects(client.login('test','wrong'),/failed/);
  await client.login('test','test-only-password');
  assert.ok(!JSON.stringify([...vault.data]).includes('test-only-password'));
  backend.stdin.write('stats\n');const initial=JSON.parse((await iterator.next()).value).executions;
  const conversation=await client.api('/conversations',{});
  const capabilities=(await client.api('/conversations')).limits;
  await assert.rejects(client.api('/conversations/'+conversation.id+'/messages',message('x'.repeat(capabilities.current_message_tokens+1),'')),error=>{
    assert.equal(error.status,413);assert.equal(error.code,'message_too_large');assert.equal(error.budget,'incoming_message');return true;
  });
  assert.equal((await client.api('/conversations/'+conversation.id)).messages.length,0);
  const longText='Remember Willow '+ 'x'.repeat(2500);
  const longBody=message(longText,'File: test.js\n'+'const x=1;'.repeat(1500));assert.ok(Buffer.byteLength(JSON.stringify(longBody))>8192);
  await client.api('/conversations/'+conversation.id+'/messages',longBody);
  let history;
  for(let n=0;n<60;n++){history=await client.api('/conversations/'+conversation.id);if(history.messages.some(m=>m.role==='assistant'))break;await new Promise(r=>setTimeout(r,30));}
  assert.match(history.messages.at(-1).content,/Willow/);assert.equal(history.messages[0].content,longText);assert.ok(history.messages[0].content.length>2048);assert.match(history.messages[0].repository_context,/File: test.js/);assert.equal((await client.api('/conversations')).limits.context_tokens,8192);
  const restored=new Client(fixture.url,vault);await restored.restore();assert.deepEqual(await restored.api('/conversations/'+conversation.id),history);
  backend.stdin.write('stats\n');assert.equal(JSON.parse((await iterator.next()).value).executions,initial,'Ordinary chat must start zero jobs');
  const {jobs}=await client.api('/jobs');assert.ok(jobs.length);
  await assert.rejects(client.api('/executions',{operation:'fixture-restart',options:{}}),/403/);
  const operation=await client.api('/executions',{operation:'health-check',options:{}});
  const logs=await client.api('/executions/'+operation.execution_id);assert.equal(logs.status,'succeeded');assert.ok(logs.output.length);
  for(const [action,decision] of [[fixture.reject,'reject'],[fixture.approve,'approve']]){
    const body={conversation_id:action.conversation,proposal_hash:action.proposal_hash,decision};
    await assert.rejects(client.api('/actions/'+action.id+'/decision',{...body,proposal_hash:'changed'}));
    await client.api('/actions/'+action.id+'/decision',body);
    await assert.rejects(client.api('/actions/'+action.id+'/decision',body));
    let result;
    for(let n=0;n<60;n++){result=await client.api('/actions/'+action.id);if(!['running','approved','submitting','verifying','verification_submitting'].includes(result.status))break;await new Promise(r=>setTimeout(r,30));}
    assert.equal(result.status,decision==='reject'?'rejected':'recovered');
  }
  await client.logout();assert.equal(vault.data.size,0);
  await assert.rejects(restored.api('/conversations'),/expired/);
});
