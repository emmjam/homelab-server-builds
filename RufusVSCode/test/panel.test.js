'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
test('conversation rendering, safe text, context removal and multiline composer protocol',()=>{
  class Element{
    constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.hidden=false;this.scrollTop=0;this.clientHeight=500;this.scrollHeight=500;}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.children=nodes;}
    get firstChild(){return this.children[0];}
  }
  const ids=['send','login','logout','connection','conversations','transcript','messages','events','actions','executions','progress','activity','welcome','budget','error','message','context','attachment','context-summary','composer'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)])),posted=[],commands=['attach','clearContext','operation'].map(type=>Object.assign(new Element('button'),{dataset:{command:type}}));
  let receive;
  const document={getElementById:id=>elements[id],createElement:tag=>new Element(tag),querySelectorAll:selector=>selector==='[data-command]'?commands:[]};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../media/panel.js'),'utf8'),{document,window:{addEventListener:(_,fn)=>receive=fn},acquireVsCodeApi:()=>({postMessage:data=>posted.push(data),setState(){}}),TextEncoder});
  elements.composer.requestSubmit=()=>elements.composer.onsubmit({preventDefault(){}});
  receive({data:{type:'state',origin:'test',conversations:[],actions:[],executions:[],limits:{context_tokens:8192},history:{messages:[{role:'user',content:'<script>evil</script>',created:1,status:'completed'},{role:'assistant',content:'Reply',created:2,status:'completed'}],events:[]}}});
  assert.match(elements.messages.children[0].className,/user/);assert.match(elements.messages.children[1].className,/assistant/);
  assert.equal(elements.messages.children[0].children[1].textContent,'<script>evil</script>');
  elements.message.value='a\nb';elements.message.onkeydown({key:'Enter',shiftKey:true});assert.equal(posted.length,1);
  elements.message.onkeydown({key:'Enter',shiftKey:false,preventDefault(){}});assert.equal(posted.at(-1).content,'a\nb');
  receive({data:{type:'error',message:'Message exceeds supported input budget'}});
  assert.equal(elements.message.value,'a\nb');
  assert.match(elements.error.textContent,/input budget/);
  receive({data:{type:'context',text:'File: test'}});assert.equal(elements.attachment.hidden,false);
  commands[1].onclick();assert.equal(posted.at(-1).type,'clearContext');
  receive({data:{type:'context',text:''}});assert.equal(elements.attachment.hidden,true);
  receive({data:{type:'state',origin:'test',conversations:[],actions:[],executions:[],history:{messages:[{role:'user',content:'wait',status:'processing',created:3}],events:[{kind:'progress',created:3,data:{status:'responding'}}]}}});
  assert.equal(elements.send.disabled,true);assert.match(elements.progress.textContent,/responding/);
});
