'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const Module=require('node:module');const path=require('node:path');
const vscode={};const originalLoad=Module._load;
Module._load=function(name,...args){return name==='vscode'?vscode:originalLoad.call(this,name,...args);};
const {activate,contextText:backendContextText}=require('../extension');Module._load=originalLoad;
const {Client}=require('../client');
const contextText=(...args)=>backendContextText(...args,{repository_max_bytes:8192});
const document={uri:{scheme:'file'},languageId:'javascript',isDirty:true,getText:()=>'<script>untrusted text</script>'};
const editor={document,selection:{start:{line:1},end:{line:2}}};
const workspace={isTrusted:true,getWorkspaceFolder:()=>({}),asRelativePath:()=> 'repo/file.js'};
test('context requires explicit trusted in-workspace editor and refuses credential files/material and excerpts large files',()=>{
  assert.match(contextText(editor,'Current selection',workspace),/Selection lines: 2–3/);
  assert.doesNotMatch(contextText(editor,'Repository/file details only',workspace),/<script>/);
  assert.throws(()=>contextText(editor,'Whole active file',{...workspace,isTrusted:false}),/Trust/);
  assert.throws(()=>contextText(editor,'Whole active file',{...workspace,getWorkspaceFolder:()=>undefined}),/workspace/);
  for(const name of ['.env','repo/secrets.txt','id_ed25519','key.pem'])assert.throws(()=>contextText(editor,'Whole active file',{...workspace,asRelativePath:()=>name}),/Credential/);
  const excerpt=contextText({...editor,document:{...document,getText:()=> '🙂'.repeat(4000)}},'Whole active file',workspace);assert.ok(Buffer.byteLength(excerpt,'utf8')<=8192);assert.match(excerpt,/omitted/);assert.ok(!excerpt.includes('�'));
  assert.throws(()=>contextText({...editor,document:{...document,getText:()=> '-----BEGIN OPENSSH PRIVATE KEY-----'}},'Whole active file',workspace),/credential/);
});
test('panel lifecycle keeps secrets out of webview and native approval sends exact backend identity only after confirmation',async t=>{
  const id='11111111-1111-4111-8111-111111111111';const aid='22222222-2222-4222-8222-222222222222';
  const calls=[],posted=[],registrations={},state=new Map([['conversation.http://rufus.lan:8788',id]]);
  const session=JSON.stringify({cookie:'test-cookie-never-in-webview',csrf:'test-csrf-never-in-webview'});
  let receiver,dispose,confirm=false;
  const proposal={id:aid,conversation:id,status:'pending',expires:Date.now()/1000+100,proposal_hash:'exact-backend-hash',proposal:{proposal:{operation:'approved-restart',parameters:{},risks:'Brief outage'}}};
  const original=Client.prototype.api;
  Client.prototype.api=async function(route,body){calls.push({route,body});if(route==='/conversations')return {conversations:[{id,title:'saved'}]};if(route==='/conversations/'+id)return {messages:[],events:[],actions:[proposal]};if(route==='/actions/'+aid)return proposal;return {};};
  t.after(()=>{Client.prototype.api=original;dispose?.();});
  Object.assign(vscode,{Uri:{joinPath:(_, ...parts)=>({toString:()=>path.join(__dirname,'../',...parts)})},ViewColumn:{Beside:2},
    commands:{registerCommand:(name,fn)=>{registrations[name]=fn;return {dispose(){}};}},
    workspace:{...workspace,getConfiguration:()=>({get:()=> 'http://rufus.lan:8788'}),onDidChangeConfiguration:()=>({dispose(){}})},
    window:{onDidChangeActiveTextEditor:()=>({dispose(){}}),registerWebviewPanelSerializer:()=>({dispose(){}}),showWarningMessage:async(_,__,label)=>confirm?label:undefined,
      createWebviewPanel:()=>({webview:{cspSource:'test-source',asWebviewUri:uri=>uri,onDidReceiveMessage:fn=>{receiver=fn;return {dispose(){}};},postMessage:async data=>posted.push(data)},onDidDispose:fn=>{dispose=fn;return {dispose(){}};}})}});
  const context={subscriptions:[],extensionUri:{},asAbsolutePath:p=>path.join(__dirname,'..',p),secrets:{get:async()=>session},globalState:{get:(k,fallback)=>state.get(k)??fallback,update:async(k,v)=>state.set(k,v)}};
  activate(context);registrations['rufus.open']();await receiver({type:'ready'});
  assert.ok(posted.some(m=>m.type==='state'));assert.doesNotMatch(JSON.stringify(posted),/test-cookie|test-csrf/);
  const updates=posted.filter(m=>m.type==='state').length;
  await new Promise(resolve=>setTimeout(resolve,2700));
  assert.ok(posted.filter(m=>m.type==='state').length>updates,'Progress polling must continue after connecting');
  const before=calls.length;await receiver({type:'decision',id:aid,decision:'approve'});assert.ok(!calls.slice(before).some(c=>c.body));
  confirm=true;await receiver({type:'decision',id:aid,decision:'approve'});
  const decision=calls.find(c=>c.route.endsWith('/decision'));assert.deepEqual(decision.body,{conversation_id:id,proposal_hash:'exact-backend-hash',decision:'approve'});
  const last=calls.length;await receiver({type:'arbitrary',path:'/commands',body:{shell:'whoami'}});assert.equal(calls.length,last);
});
