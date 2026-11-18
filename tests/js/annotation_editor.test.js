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
  let downloads = 0, downloadedBlob;
  window.URL.createObjectURL = blob => {downloadedBlob=blob;return 'blob:test';};
  window.URL.revokeObjectURL = () => {};
  window.HTMLAnchorElement.prototype.click = () => { downloads++; };
  if (storage) Object.defineProperty(window, 'localStorage', {value:storage});
  window.addEventListener('error', event=>{throw event.error;});
  const app = Editor.init({document:window.document,window,core:Core,importer:Importer});
  return {window,app,downloads:()=>downloads,close:()=>window.close(),downloadedText:()=>new Promise((resolve,reject)=>{
    const reader=new window.FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(reader.error);reader.readAsText(downloadedBlob);
  })};
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
  env.window.document.getElementById('ann-tab-btn-access').click();
  assert.equal(env.window.document.getElementById('ann-tab-access').hidden,false);
  assert.match(env.window.document.getElementById('ann-access-message').textContent,/수집본.*다르/);
  assert.equal(env.window.document.getElementById('source-report').hidden,true);
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


function sharedStorage() {
  const data=new Map();
  return {getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};
}
function editRule(env,text) {
  const input=env.window.document.querySelector('[data-note-id="rule-a"]');
  input.value=text;input.dispatchEvent(new env.window.Event('input',{bubbles:true}));
}
async function downloadedProject(env,method) {
  assert.equal(env.app[method](),true);
  return Importer.parse(await env.downloadedText(),env.window.document,Core);
}

for(const method of ['saveProject','saveHtml']) {
  test(method+' download anchors recover later edits from every saved and original revision',async()=>{
    const original=fixture(),storage=sharedStorage(),env=mount(original,storage),anchors=[original];
    try {
      editRule(env,'first saved note');anchors.push(await downloadedProject(env,method));
      editRule(env,'second saved note');anchors.push(await downloadedProject(env,method));
      editRule(env,'latest unsaved note');
      for(const anchor of anchors) {
        const reopened=mount(anchor,storage);
        try {
          assert.deepEqual(reopened.app.getProject(),anchor,'file remains authoritative before explicit restore');
          assert.equal(reopened.window.document.getElementById('ann-recovery').hidden,false);
          assert.equal(reopened.app.restoreDraft(),true);
          assert.equal(reopened.app.getProject().annotations.rules['rule-a'].text,'latest unsaved note');
        } finally {reopened.close();}
      }
    } finally {env.close();}
  });
}

test('download recovery rejects different snapshot content and divergent same-revision files',async()=>{
  const storage=sharedStorage(),env=mount(fixture(),storage);
  try {
    editRule(env,'saved branch');const saved=await downloadedProject(env,'saveProject');
    editRule(env,'later in saved branch');
    for(const mutate of [p=>p.snapshot.rules[0].raw='any any any deny',p=>p.annotations.rules['rule-a'].text='different branch',p=>p.projectId='other-project',p=>p.revision++,p=>p.updatedAt='2026-11-16T05:00:00Z']) {
      const other=structuredClone(saved);mutate(other);
      const reopened=mount(other,storage);
      try {assert.equal(reopened.app.restoreDraft(),false);assert.deepEqual(reopened.app.getProject(),other);}finally{reopened.close();}
    }
  }finally{env.close();}
});

test('pending recovery survives downloads and restoring it never writes to an abandoned download branch',async()=>{
  const original=fixture(),storage=sharedStorage(),draft=fixture();
  draft.revision=1;draft.annotations.rules['rule-a'].text='pending recovery';
  Editor.saveRecovery(storage,original,draft);
  const env=mount(original,storage);
  try {
    editRule(env,'separate branch');const abandoned=await downloadedProject(env,'saveHtml');
    editRule(env,'still separate');
    assert.equal(Editor.readRecovery(storage,original,Core).annotations.rules['rule-a'].text,'pending recovery');
    assert.equal(env.app.restoreDraft(),true);editRule(env,'continued recovered branch');
    assert.equal(Editor.readRecovery(storage,original,Core).annotations.rules['rule-a'].text,'continued recovered branch');
    const reopened=mount(abandoned,storage);
    try{assert.equal(reopened.app.restoreDraft(),false);}finally{reopened.close();}
  }finally{env.close();}
});

test('partial recovery quota failure remains visible after a successful download request',async()=>{
  const storage=sharedStorage(),env=mount(fixture(),storage);
  try {
    editRule(env,'saved note');const saved=await downloadedProject(env,'saveProject');
    const set=storage.setItem;storage.setItem=(key,value)=>{if(key===Editor.recoveryKey(saved))throw Error('quota');set(key,value);};
    editRule(env,'unsaved note');
    assert.match(env.window.document.getElementById('ann-status').textContent,/임시저장.*불가/);
    assert.equal(env.app.saveHtml(),true);
    assert.match(env.window.document.getElementById('ann-status').textContent,/다운로드.*요청/);
    assert.match(env.window.document.getElementById('ann-status').textContent,/임시저장.*불가/);
    assert.equal(Editor.readRecovery(storage,fixture(),Core).annotations.rules['rule-a'].text,'unsaved note');
  }finally{env.close();}
});

test('competing workspaces cannot overwrite recovery from a different branch',()=>{
  const original=fixture(),storage=sharedStorage(),first=mount(original,storage),second=mount(original,storage);
  try {
    editRule(first,'first branch');editRule(second,'second branch');
    assert.equal(Editor.readRecovery(storage,original,Core).annotations.rules['rule-a'].text,'first branch');
    assert.match(second.window.document.getElementById('ann-status').textContent,/임시저장.*불가/);
  }finally{first.close();second.close();}
});

test('same revision and timestamp cannot recover annotations belonging to another base branch',()=>{
  const storage=sharedStorage(),base=fixture(),draft=fixture();
  draft.revision=1;draft.annotations.rules['rule-a'].text='draft from original branch';
  Editor.saveRecovery(storage,base,draft);
  const different=fixture();different.annotations.rules['rule-a'].text='other base branch';
  assert.equal(Editor.readRecovery(storage,different,Core),null);
});

test('large valid recovery reports failure instead of claiming to save an unreadable draft',()=>{
  const storage=sharedStorage(),base=fixture();
  base.annotations.rules['rule-a'].reasons=Array.from({length:13},()=> 'r'.repeat(1000000));
  const draft=structuredClone(base);draft.revision=1;draft.annotations.rules['rule-a'].text='large draft';
  Core.validateProject(base);Core.validateProject(draft);
  const result=Editor.saveRecovery(storage,base,draft);
  if(result.ok) assert.equal(Editor.readRecovery(storage,base,Core)?.annotations.rules['rule-a'].text,'large draft');
  else assert.equal(storage.getItem(Editor.recoveryKey(base)),null);
});

test('different snapshot or base branch edits cannot replace existing recovery with reused IDs',()=>{
  for(const mutate of [p=>p.snapshot.rules[0].raw='any any any deny',p=>p.annotations.rules['rule-a'].text='another base']) {
    const original=fixture(),storage=sharedStorage(),first=mount(original,storage);
    try {
      editRule(first,'original branch recovery');
      const different=fixture();mutate(different);const second=mount(different,storage);
      try {
        editRule(second,'different branch edit');
        assert.equal(Editor.readRecovery(storage,original,Core).annotations.rules['rule-a'].text,'original branch recovery');
        assert.match(second.window.document.getElementById('ann-status').textContent,/임시저장.*불가/);
      } finally {second.close();}
    } finally {first.close();}
  }
});

test('discarding a pending draft cannot delete a newer draft written by another workspace',()=>{
  const original=fixture(),draft=fixture(),storage=sharedStorage();
  draft.revision=1;draft.annotations.rules['rule-a'].text='pending';Editor.saveRecovery(storage,original,draft);
  const first=mount(original,storage),second=mount(original,storage);
  try {
    assert.equal(first.app.restoreDraft(),true);editRule(first,'newer recovery');
    second.window.document.getElementById('ann-discard-draft').click();
    assert.equal(Editor.readRecovery(storage,original,Core)?.annotations.rules['rule-a'].text,'newer recovery');
  } finally {first.close();second.close();}
});

test('discarding the pending draft permits current branch recovery after a download',async()=>{
  const original=fixture(),draft=fixture(),storage=sharedStorage();
  draft.revision=1;draft.annotations.rules['rule-a'].text='pending';Editor.saveRecovery(storage,original,draft);
  const env=mount(original,storage);
  try {
    editRule(env,'chosen branch');const saved=await downloadedProject(env,'saveProject');
    env.window.document.getElementById('ann-discard-draft').click();editRule(env,'continued chosen branch');
    for(const anchor of [original,saved]) assert.equal(Editor.readRecovery(storage,anchor,Core)?.annotations.rules['rule-a'].text,'continued chosen branch');
  } finally {env.close();}
});

test('C layout has one Role workspace with three internal tabs and no legacy mode buttons', () => {
  const env=mount(); const doc=env.window.document;
  try {
    const ids=['policy','access','collection'];
    assert.deepEqual(Array.from(doc.querySelectorAll('[data-unified-tab]')).map(el=>el.dataset.unifiedTab),ids);
    assert.equal(doc.getElementById('ann-source-mode'),null);
    assert.equal(doc.getElementById('ann-editor-mode'),null);
    assert.equal(doc.getElementById('ann-tab-policy').hidden,false);
    for(const name of ids){
      doc.getElementById('ann-tab-btn-'+name).click();
      for(const other of ids) assert.equal(doc.getElementById('ann-tab-'+other).hidden,other!==name);
      assert.equal(doc.getElementById('ann-tab-btn-'+name).getAttribute('aria-selected'),'true');
    }
  } finally {env.close();}
});

test('exact-name common ACLs are hidden by default, reversible, and preserved in snapshots and export', () => {
  const p=fixture(), original=p.snapshot.rules[0];
  const names=['global-sacl','re-guard','logon-control','Re-Guard','LOGON-CONTROL','re-guardian','logon-control-v2','custom-global-sacl','role-specific'];
  names.forEach((acl,i)=>{
    const rule={...original,id:'test-rule-'+i,acl,ordinal:i+2,raw:'policy '+acl};
    p.snapshot.rules.push(rule);
    p.annotations.rules[rule.id]={text:'주석 '+acl,status:'reviewed',updatedAt:p.updatedAt,confirmedAt:p.updatedAt,reasons:[],source:null};
  });
  const env=mount(p),doc=env.window.document;
  try {
    const count=()=>doc.querySelectorAll('.ann-rules tbody tr').length;
    assert.equal(count(),5);
    assert.equal(doc.getElementById('ann-show-common-acl').checked,false);
    assert.match(doc.querySelector('.ann-role-header').textContent,/전용 5개.*공통 5개/);
    assert.match(doc.getElementById('ann-role-list').textContent,/5 전용 규칙.*5 공통 규칙/);
    const text=doc.querySelector('.ann-rules').textContent;
    for(const name of ['re-guardian','logon-control-v2','custom-global-sacl','role-specific']) assert.ok(text.includes(name),name);
    for(const name of ['global-sacl','re-guard','logon-control']) {
      assert.ok(!Array.from(doc.querySelectorAll('.ann-rules tbody strong')).some(x=>x.textContent.toLowerCase()===name),name);
    }
    assert.equal(env.app.exportModel().rules.length,10);
    for(const name of names) assert.ok(env.app.exportModel().rules.some(x=>x.acl===name));
    const control=doc.getElementById('ann-show-common-acl');
    control.checked=true;control.dispatchEvent(new env.window.Event('change',{bubbles:true}));
    assert.equal(count(),10);
    assert.deepEqual(Array.from(doc.querySelectorAll('.ann-rules tbody tr strong')).map(x=>x.textContent),[original.acl,...names]);
    assert.equal(env.app.getProject().revision,p.revision);
    const reset=doc.getElementById('ann-show-common-acl');
    reset.checked=false;reset.dispatchEvent(new env.window.Event('change',{bubbles:true}));
    assert.equal(count(),5);
    for(let i=0;i<names.length;i++) assert.equal(env.app.getProject().annotations.rules['test-rule-'+i].text,'주석 '+names[i]);
  } finally {env.close();}
});

test('Role with only common ACLs does not claim no ACL policy was collected', () => {
  const p=fixture();
  p.snapshot.rules=p.snapshot.rules.map(r=>({...r,acl:'logon-control'}));
  const env=mount(p),doc=env.window.document;
  try {
    assert.match(doc.querySelector('.ann-rules').textContent,/전용 ACL이 표시되지 않습니다/);
    assert.match(doc.querySelector('.ann-rules').textContent,/공통 ACL 1개가 숨겨져 있습니다/);
    assert.doesNotMatch(doc.querySelector('.ann-rules').textContent,/수집된 ACL 규칙이 없습니다/);
    assert.equal(env.app.exportModel().rules.length,p.snapshot.rules.length);
    const check=doc.getElementById('ann-show-common-acl');
    check.checked=true;check.dispatchEvent(new env.window.Event('change',{bubbles:true}));
    assert.match(doc.querySelector('.ann-rules').textContent,/logon-control/);
  } finally {env.close();}
});

test('moving original Access Check preserves listeners and disables stale sources', () => {
  const p=fixture(),docHtml=`<!doctype html><div id="annotation-workspace"></div>
    <div id="source-report" data-source-snapshot-id="snapshot-a">
      <main><section class="role-panel" id="original-role" data-controller-id="controller-a" data-role="EMPLOYEE" data-role-key="EMPLOYEE"></section>
      <button class="role-tab" data-panel-id="original-role"></button>
      <section class="access-check"><button id="test-check">Run</button></section></main></div>
    <script id="annotation-project-data" type="application/json"></script>`;
  const dom=new JSDOM(docHtml,{url:'https://offline.test/report.html'});
  const {window}=dom,doc=window.document;
  doc.getElementById('annotation-project-data').textContent=JSON.stringify(p);
  let clicks=0;
  doc.getElementById('test-check').addEventListener('click',()=>clicks++);
  const app=Editor.init({document:doc,window,core:Core,importer:Importer});
  try {
    doc.getElementById('ann-tab-btn-access').click();
    assert.equal(doc.querySelector('#ann-access-slot #test-check')!==null,true);
    doc.getElementById('test-check').click();
    assert.equal(clicks,1);
    const modified=fixture();modified.snapshot.rules[0].raw+=' modified';
    assert.equal(app.openText(JSON.stringify(modified)),true);
    doc.getElementById('ann-tab-btn-access').click();
    assert.equal(doc.querySelector('#ann-access-slot .access-check').hidden,true);
    assert.equal(doc.querySelector('#source-report').hidden,true);
  } finally {window.close();}
});
