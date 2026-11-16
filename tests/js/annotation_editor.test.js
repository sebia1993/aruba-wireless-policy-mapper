'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const Core = require('../../src/wlc_role_acl_collector/static/annotation_core.js');
const Importer = require('../../src/wlc_role_acl_collector/static/annotation_import.js');
const Editor = require('../../src/wlc_role_acl_collector/static/annotation_editor.js');
const fixture = require('./editor_fixture.js');

function mount(project = fixture(), storage) {
  const dom = new JSDOM('<!doctype html><div id="annotation-workspace"></div><div id="source-report" data-source-snapshot-id="snapshot-a">ORIGINAL_SOURCE_SECRET</div><script id="annotation-project-data" type="application/json"></script>', {url:'https://offline.test/report.html'});
  const {window} = dom;
  window.document.getElementById('annotation-project-data').textContent = JSON.stringify(project);
  window.confirm = () => true;
  let downloads = 0;
  window.URL.createObjectURL = () => 'blob:test';
  window.URL.revokeObjectURL = () => {};
  window.HTMLAnchorElement.prototype.click = () => { downloads++; };
  if (storage) Object.defineProperty(window, 'localStorage', {value:storage});
  window.addEventListener('error', event=>{throw event.error;});
  const app = Editor.init({document:window.document,window,core:Core,importer:Importer});
  return {window,app,downloads:()=>downloads,close:()=>window.close()};
}

test('recovery keys isolate project, snapshot, revision and base timestamp', () => {
  const p = fixture(), key = Editor.recoveryKey(p);
  for (const change of [x=>x.projectId='another',x=>x.snapshot.id='another',x=>x.revision++,x=>x.updatedAt='2026-11-16T02:00:00Z']) {
    const q = structuredClone(p); change(q); assert.notEqual(Editor.recoveryKey(q),key);
  }
});

test('storage failures are nonfatal, and recovery preserves explicit empty notes', () => {
  const base = fixture(), edited = fixture(); edited.revision++; edited.annotations.rules['rule-a'].text='';
  assert.equal(Editor.saveRecovery({setItem(){throw Error('quota');}},base,edited).ok,false);
  const data = new Map(), storage={setItem:(k,v)=>data.set(k,v),getItem:k=>data.get(k)};
  assert.equal(Editor.saveRecovery(storage,base,edited).ok,true);
  assert.equal(Editor.readRecovery(storage,base,Core).annotations.rules['rule-a'].text,'');
  const different = fixture(); different.revision++;
  assert.equal(Editor.readRecovery(storage,different,Core),null);
});

test('files remain authoritative until the user explicitly restores recovery', () => {
  const base=fixture(), edited=fixture(); edited.revision=1; edited.annotations.rules['rule-a'].text='';
  const data=new Map(), storage={setItem:(k,v)=>data.set(k,v),getItem:k=>data.get(k),removeItem:k=>data.delete(k)};
  Editor.saveRecovery(storage,base,edited);
  const env=mount(base,storage);
  assert.equal(env.app.getProject().annotations.rules['rule-a'].text,'기존 설명');
  env.app.restoreDraft();
  assert.equal(env.app.getProject().annotations.rules['rule-a'].text,'');
  assert.equal(env.window.document.querySelector('[data-note-id="rule-a"]').value,'');
  env.close();
});

test('quota failures do not block project downloads or claim a file was saved', () => {
  const env=mount(fixture(),{getItem:()=>null,setItem(){throw Error('quota');},removeItem(){}});
  const input=env.window.document.querySelector('[data-note-id="rule-a"]');
  input.value='수정 내용'; input.dispatchEvent(new env.window.Event('input',{bubbles:true}));
  assert.equal(env.app.getProject().annotations.rules['rule-a'].text,'수정 내용');
  assert.match(env.window.document.getElementById('ann-status').textContent,/임시저장.*불가/);
  assert.equal(env.app.saveProject(),true);
  assert.equal(env.downloads(),1);
  assert.match(env.window.document.getElementById('ann-status').textContent,/다운로드.*요청/);
  env.close();
});

test('invalid imports do not replace the current project', () => {
  const env=mount(), invalid=fixture(); invalid.schemaVersion=999;
  assert.equal(env.app.openText(JSON.stringify(invalid)),false);
  assert.deepEqual(env.app.getProject(),fixture());
  assert.match(env.window.document.getElementById('ann-status').textContent,/열기 실패/);
  env.close();
});

test('standalone HTML contains only the current project and escapes executable markup', () => {
  const env=mount(), p=fixture(); p.projectId='new-project';p.snapshot.id='new-snapshot';
  p.annotations.rules['rule-a'].text='</script><script>window.PWNED=true</script>';
  assert.equal(env.app.openText(JSON.stringify(p)),true);
  const html=Editor.standaloneHtml(p,env.window.document);
  assert.ok(!html.includes('ORIGINAL_SOURCE_SECRET'));
  assert.ok(!html.includes('</script><script>window.PWNED=true'));
  const doc=new JSDOM(html).window.document;
  assert.deepEqual(Core.parseProject(doc.getElementById('annotation-project-data').textContent),p);
  assert.equal(env.window.document.getElementById('source-report').hidden,true);
  env.close();
});
test('leading newlines survive display, editing and re-render', () => {
  const p=fixture();p.annotations.rules['rule-a'].text='\n첫 줄은 비워 둠';
  const env=mount(p), input=env.window.document.querySelector('[data-note-id="rule-a"]');
  assert.equal(input.value,'\n첫 줄은 비워 둠');
  input.value+='!';input.dispatchEvent(new env.window.Event('input',{bubbles:true}));
  assert.equal(env.app.getProject().annotations.rules['rule-a'].text,'\n첫 줄은 비워 둠!');
  env.close();
});
test('manual controller mapping controls only unknown identities and explains automatic matching', () => {
  const p=fixture();p.annotations.rules={};const env=mount(p), previous=fixture();
  previous.snapshot.controllers.push({...previous.snapshot.controllers[0],id:'unknown',name:'장비 미확인',host:'',port:0,identityKnown:false});
  assert.equal(env.app.reuseText(JSON.stringify(previous)),true);
  const selects=env.window.document.querySelectorAll('[data-map-controller]');
  assert.equal(selects.length,1);assert.equal(selects[0].dataset.mapController,'unknown');
  assert.match(env.window.document.getElementById('ann-import-map').textContent,/주소가 확인된.*자동/);
  env.close();
});
test('unresolved target choices are populated on demand instead of a Cartesian product', () => {
  const p=fixture(), row=p.snapshot.rules[0];
  p.snapshot.rules=Array.from({length:100},(_,i)=>({...row,id:'rule-'+i,ordinal:i+1}));
  p.annotations.rules={};
  p.unresolvedAnnotations=Array.from({length:100},(_,i)=>({id:'orphan-'+i,kind:'rule',controllerId:'controller-a',controllerName:'WLC-A',roleName:'EMPLOYEE',acl:'EMPLOYEE',raw:row.raw,annotation:{text:'이전 설명',status:'needs_review',updatedAt:p.updatedAt,confirmedAt:'',reasons:[],source:null},reason:'규칙 중복',candidateIds:[],sourceProjectId:'previous',sourceSnapshotId:'previous-snapshot'}));
  const env=mount(p);
  assert.equal(env.window.document.querySelectorAll('[data-link-target] option').length,100);
  env.window.document.querySelector('[data-link-target]').focus();
  assert.equal(env.window.document.querySelectorAll('[data-link-target] option').length,200);
  env.close();
});
test('a reused snapshot ID cannot expose a mismatched original source view or recovery', () => {
  const base=fixture(), edited=fixture();edited.revision=1;edited.snapshot.rules[0].raw='any any any deny';
  const data=new Map(), storage={setItem:(k,v)=>data.set(k,v),getItem:k=>data.get(k)};
  Editor.saveRecovery(storage,base,edited);
  assert.equal(Editor.readRecovery(storage,base,Core),null);
  const env=mount();env.app.openText(JSON.stringify(edited));
  assert.equal(env.window.document.getElementById('ann-source-mode').hidden,true);
  env.close();
});
test('restoring a different draft at the same revision invalidates the review filter cache', () => {
  const base=fixture(), draft=fixture();draft.revision=1;
  const data=new Map(), storage={setItem:(k,v)=>data.set(k,v),getItem:k=>data.get(k),removeItem:k=>data.delete(k)};
  Editor.saveRecovery(storage,base,draft);
  const env=mount(base,storage),input=env.window.document.querySelector('[data-note-id="rule-a"]');
  input.value='지금 수정';input.dispatchEvent(new env.window.Event('input',{bubbles:true}));
  assert.equal(env.app.getProject().revision,1);
  assert.match(env.window.document.getElementById('ann-review-button').textContent,/1 Role/);
  env.app.restoreDraft();
  assert.equal(Core.buildExportModel(env.app.getProject(),{type:'review'}).roles.length,0);
  assert.match(env.window.document.getElementById('ann-review-button').textContent,/0 Role/);
  env.close();
});

function deferredFile(env, mode='open') {
  let resolve, reject;
  const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
  env.window.document.getElementById(mode==='open'?'ann-open':'ann-reuse').click();
  const input=env.window.document.getElementById('ann-file');
  Object.defineProperty(input,'files',{value:[{size:100,text:()=>promise}],configurable:true});
  input.dispatchEvent(new env.window.Event('change',{bubbles:true}));
  return {resolve:p=>resolve(JSON.stringify(p)),reject};
}
const flushReads=()=>new Promise(resolve=>setImmediate(resolve));
function unloadBlocked(env) {
  const event=new env.window.Event('beforeunload',{cancelable:true});
  env.window.dispatchEvent(event);
  return event.defaultPrevented;
}

test('latest selected file wins when reads finish out of order', async () => {
  const env=mount();
  try {
    const first=deferredFile(env),second=deferredFile(env);
    const a=fixture(),b=fixture();a.projectId='first-file';b.projectId='second-file';
    second.resolve(b);await flushReads();first.resolve(a);await flushReads();
    assert.equal(env.app.getProject().projectId,'second-file');
  } finally {env.close();}
});

test('pending reuse cannot mutate or display controller mapping in a newly opened project', async () => {
  for (const unknown of [false,true]) {
    const env=mount();
    try {
      const read=deferredFile(env,'reuse'),next=fixture(),previous=fixture();
      next.projectId='new-work';next.annotations.rules={};
      previous.snapshot.controllers[0].identityKnown=!unknown;
      assert.equal(env.app.openText(JSON.stringify(next)),true);
      read.resolve(previous);await flushReads();
      assert.deepEqual(env.app.getProject(),next);
      assert.equal(env.window.document.getElementById('ann-import-map').hidden,true);
    } finally {env.close();}
  }
});

test('stale read failures do not replace a newer success status', async () => {
  const env=mount();
  try {
    const first=deferredFile(env),second=deferredFile(env),next=fixture();next.projectId='latest';
    second.resolve(next);await flushReads();
    const status=env.window.document.getElementById('ann-status').textContent;
    first.reject(Error('old failure'));await flushReads();
    assert.equal(env.window.document.getElementById('ann-status').textContent,status);
  } finally {env.close();}
});

test('restoring a different saved-revision draft warns on unload and replacement until downloaded', () => {
  for (const save of ['saveProject','saveHtml']) {
    const base=fixture(),draft=fixture();draft.revision=1;draft.annotations.rules['rule-a'].text='recovered note';
    const data=new Map(),storage={setItem:(k,v)=>data.set(k,v),getItem:k=>data.get(k),removeItem:k=>data.delete(k)};
    Editor.saveRecovery(storage,base,draft);
    const env=mount(base,storage);
    try {
      const input=env.window.document.querySelector('[data-note-id="rule-a"]');
      input.value='different revision one';input.dispatchEvent(new env.window.Event('input',{bubbles:true}));
      assert.equal(env.app[save](),true);assert.equal(unloadBlocked(env),false);
      assert.equal(env.app.restoreDraft(),true);assert.equal(unloadBlocked(env),true);
      let confirmations=0;env.window.confirm=()=>{confirmations++;return false;};
      assert.equal(env.app.openText(JSON.stringify(fixture())),false);assert.equal(confirmations,1);
      assert.equal(env.app.getProject().annotations.rules['rule-a'].text,'recovered note');
      assert.equal(env.app[save](),true);assert.equal(unloadBlocked(env),false);
    } finally {env.close();}
  }
});

function nearTextLimit(p=fixture(), headroom=100) {
  p.snapshot.roles.push({...p.snapshot.roles[0],id:'role-padding',name:'SYNTHETIC-PADDING',bindingRaw:[]});
  const padding=p.snapshot.roles[1].bindingRaw;
  for(let i=0;i<20;i++)padding.push('');
  // Build a valid synthetic document with the requested amount of aggregate headroom.
  const size=value=>typeof value==='string'?value.length:Array.isArray(value)?value.reduce((n,v)=>n+size(v),0):value&&typeof value==='object'?Object.entries(value).reduce((n,[k,v])=>n+k.length+size(v),0):0;
  let remaining=20000000-headroom-size(p);
  for(let i=0;i<padding.length;i++){padding[i]='p'.repeat(Math.min(1000000,remaining));remaining-=padding[i].length;}
  return Core.validateProject(p);
}

test('aggregate text-limit rejection preserves project, input, recovery and download ability', () => {
  const p=nearTextLimit(),data=new Map(),storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};
  const env=mount(p,storage),errors=[];
  env.window.addEventListener('error',event=>{errors.push(event.error);event.preventDefault();});
  try {
    const input=env.window.document.querySelector('[data-note-id="rule-a"]');
    input.value='x'.repeat(300);input.dispatchEvent(new env.window.Event('input',{bubbles:true}));
    assert.deepEqual(env.app.getProject(),p);
    assert.equal(errors.length,0);assert.equal(input.value,p.annotations.rules['rule-a'].text);
    assert.equal(data.size,0);assert.equal(unloadBlocked(env),false);
    assert.equal(env.window.document.getElementById('ann-status').dataset.state,'error');
    assert.equal(env.app.saveProject(),true);assert.equal(env.downloads(),1);
    input.value='ok';input.dispatchEvent(new env.window.Event('input',{bubbles:true}));
    assert.equal(env.app.getProject().annotations.rules['rule-a'].text,'ok');
    assert.equal(data.size,1);assert.equal(unloadBlocked(env),true);
  } finally {env.close();}
});


test('status, template and orphan-link edits reject aggregate growth without partial changes', () => {
  for(const action of ['status','template','link']) {
    const base=fixture();
    base.annotations.rules['rule-a'].status='unreviewed';
    base.annotations.rules['rule-a'].confirmedAt='';
    if(action==='link') base.unresolvedAnnotations.push({id:'orphan-a',kind:'rule',controllerId:'controller-a',controllerName:'WLC-A',roleName:'EMPLOYEE',acl:'EMPLOYEE',raw:'any any any permit',annotation:{...base.annotations.rules['rule-a'],text:'previous note'},reason:'synthetic conflict',candidateIds:['rule-a'],sourceProjectId:'previous',sourceSnapshotId:'previous-snapshot'});
    const p=nearTextLimit(base,1),env=mount(p);
    try {
      if(action==='status') {
        const select=env.window.document.querySelector('[data-status-id="rule-a"]');
        select.value='reviewed';select.dispatchEvent(new env.window.Event('change',{bubbles:true}));
        assert.equal(select.value,'unreviewed');
      } else if(action==='template') {
        env.window.document.querySelector('[data-template-id="role-a"]').click();
        assert.equal(env.window.document.querySelector('[data-note-id="role-a"]').value,'');
      } else {
        const select=env.window.document.querySelector('[data-link-target="orphan-a"]');
        select.focus();select.value='rule-a';
        env.window.document.querySelector('[data-link-orphan="orphan-a"]').click();
      }
      assert.deepEqual(env.app.getProject(),p);
      assert.equal(unloadBlocked(env),false);
      assert.equal(env.window.document.getElementById('ann-status').dataset.state,'error');
      assert.equal(env.app.saveProject(),true);
    } finally {env.close();}
  }
});

test('manual orphan linking commits valid notes, preserves conflicts and warns until saved', () => {
  const p=fixture();
  p.unresolvedAnnotations.push({id:'orphan-a',kind:'rule',controllerId:'controller-a',controllerName:'WLC-A',roleName:'EMPLOYEE',acl:'EMPLOYEE',raw:'any any any permit',annotation:{...p.annotations.rules['rule-a'],text:'previous note'},reason:'synthetic conflict',candidateIds:['rule-a'],sourceProjectId:'previous',sourceSnapshotId:'previous-snapshot'});
  const env=mount(p);
  try {
    const select=env.window.document.querySelector('[data-link-target="orphan-a"]');
    select.focus();select.value='rule-a';env.window.document.querySelector('[data-link-orphan="orphan-a"]').click();
    const next=Core.validateProject(env.app.getProject());
    assert.equal(next.annotations.rules['rule-a'].text,'previous note');
    assert.equal(next.annotations.rules['rule-a'].status,'needs_review');
    assert.equal(next.unresolvedAnnotations.length,1);
    assert.equal(next.unresolvedAnnotations[0].annotation.text,p.annotations.rules['rule-a'].text);
    assert.equal(next.changes.length,1);assert.equal(next.revision,1);
    assert.equal(unloadBlocked(env),true);assert.equal(env.app.saveProject(),true);assert.equal(unloadBlocked(env),false);
  } finally {env.close();}
});

function collidingRecordIds() {
  const p=fixture(),note=p.annotations.rules['rule-a'];
  p.snapshot.roles[0].id='shared';p.snapshot.rules[0].roleId='shared';p.snapshot.rules[0].id='shared';
  p.annotations.roles={shared:{...note,text:'role note'}};
  p.annotations.rules={shared:{...note,text:'rule note'}};
  return p;
}

test('rejected edits restore the correct kind when role and rule IDs coincide', () => {
  const p=collidingRecordIds();p.revision=Number.MAX_SAFE_INTEGER;
  const env=mount(p);
  try {
    const role=env.window.document.querySelector('[data-note-kind="roles"][data-note-id="shared"]');
    const rule=env.window.document.querySelector('[data-note-kind="rules"][data-note-id="shared"]');
    rule.value='rejected rule edit';rule.dispatchEvent(new env.window.Event('input',{bubbles:true}));
    assert.equal(role.value,'role note');assert.equal(rule.value,'rule note');
    assert.deepEqual(env.app.getProject(),p);assert.equal(unloadBlocked(env),false);
    assert.equal(env.window.document.getElementById('ann-status').dataset.state,'error');
  } finally {env.close();}
});

test('successful edits update only the matching kind status when IDs coincide', () => {
  const env=mount(collidingRecordIds());
  try {
    const rule=env.window.document.querySelector('[data-note-kind="rules"][data-note-id="shared"]');
    rule.value='updated rule';rule.dispatchEvent(new env.window.Event('input',{bubbles:true}));
    assert.equal(env.window.document.querySelector('[data-status-kind="roles"][data-status-id="shared"]').value,'reviewed');
    assert.equal(env.window.document.querySelector('[data-status-kind="rules"][data-status-id="shared"]').value,'unreviewed');
    assert.equal(env.app.getProject().annotations.roles.shared.text,'role note');
    assert.equal(env.app.getProject().annotations.rules.shared.text,'updated rule');
  } finally {env.close();}
});
