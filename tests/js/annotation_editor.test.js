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
