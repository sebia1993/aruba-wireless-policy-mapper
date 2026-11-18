'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const Core = require('../../src/wlc_role_acl_collector/static/annotation_core.js');
const Editor = require('../../src/wlc_role_acl_collector/static/annotation_editor.js');
const Export = require('../../src/wlc_role_acl_collector/static/annotation_export.js');
const ExcelJS = require('../../src/wlc_role_acl_collector/static/exceljs.min.js');
const fixture = require('./editor_fixture.js');

function record(manualSsid, deviceType) {
  return {text:'',status:'unreviewed',updatedAt:'2026-11-16T01:00:00Z',
    confirmedAt:'',reasons:[],source:null,manualSsid,deviceType};
}

function mount(p = fixture()) {
  const dom = new JSDOM(
    '<!doctype html><div id="annotation-workspace"></div>' +
    '<div id="source-report" data-source-snapshot-id="snapshot-a"></div>' +
    '<script id="annotation-project-data" type="application/json"></script>',
    {url:'https://offline.test/report.html'});
  const {window} = dom;
  window.document.getElementById('annotation-project-data').textContent = JSON.stringify(p);
  window.confirm = () => true;
  let downloaded;
  window.URL.createObjectURL = blob => {downloaded = blob; return 'blob:download';};
  window.URL.revokeObjectURL = () => {};
  window.HTMLAnchorElement.prototype.click = () => {};
  const app = Editor.init({document:window.document, window, core:Core});
  return {window,app,close:()=>window.close(),downloaded:()=>new Promise((resolve,reject)=>{
    const reader = new window.FileReader();
    reader.onload=()=>resolve(reader.result);
    reader.onerror=()=>reject(reader.error);
    reader.readAsText(downloaded);
  })};
}

test('old JSON projects remain valid and manual Role fields are strictly validated', () => {
  const p = fixture();
  assert.deepEqual(Core.validateProject(p),p);
  p.annotations.roles['role-a'] = record('sWave_works', 'PC');
  assert.equal(Core.parseProject(JSON.stringify(p)).annotations.roles['role-a'].deviceType,'PC');
  for (const device of ['', 'PC', 'windows_pc', 'macbook', 'mobile', 'ETC']) {
    p.annotations.roles['role-a'].deviceType = device;
    assert.doesNotThrow(()=>Core.validateProject(p));
  }
  for (const invalid of ['tablet','Mobile',null,123]) {
    p.annotations.roles['role-a'].deviceType = invalid;
    assert.throws(()=>Core.validateProject(p),/deviceType/);
  }
  p.annotations.roles['role-a'].deviceType = 'ETC';
  p.annotations.roles['role-a'].manualSsid = 'A'.repeat(513);
  assert.throws(()=>Core.validateProject(p),/manualSsid/);
  p.annotations.roles['role-a'].manualSsid = 'corp';
  p.annotations.rules['rule-a'].deviceType = 'PC';
  assert.throws(()=>Core.validateProject(p),/deviceType/);
});

test('HTML Role header permits manual SSID, Windows PC, MacBook and legacy categories', () => {
  const env=mount(),doc=env.window.document;
  try {
    const ssid=doc.querySelector('[data-manual-ssid="role-a"]');
    const type=doc.querySelector('[data-device-type="role-a"]');
    assert.ok(ssid);assert.ok(type);
    assert.deepEqual(Array.from(type.options,o=>o.value),['','windows_pc','macbook','PC','mobile','ETC']);
    assert.equal(Array.from(type.options).find(o=>o.value==='windows_pc').textContent,'윈도우 PC');
    assert.equal(Array.from(type.options).find(o=>o.value==='macbook').textContent,'맥북');
    assert.equal(Array.from(type.options).find(o=>o.value==='PC').textContent,'PC (기존 분류)');
    assert.equal(ssid.value,'');assert.equal(type.value,'');
    assert.match(doc.querySelector('.ann-role-header').textContent,/수집 SSID: corp/);
    ssid.value='sWave_works';ssid.dispatchEvent(new env.window.Event('input',{bubbles:true}));
    type.value='mobile';type.dispatchEvent(new env.window.Event('change',{bubbles:true}));
    const p=env.app.getProject();
    assert.equal(p.annotations.roles['role-a'].manualSsid,'sWave_works');
    assert.equal(p.annotations.roles['role-a'].deviceType,'mobile');
    assert.equal(p.snapshot.roles[0].ssids[0],'corp');
    assert.equal(p.annotations.roles['role-a'].text,'');
    assert.equal(p.annotations.roles['role-a'].status,'unreviewed');
    assert.match(doc.querySelector('#ann-role-list').textContent,/SSID: sWave_works/);
    assert.ok(Core.buildExportModel(p,{type:'review'}).roles.some(x=>x.id==='role-a'));
    type.value='';type.dispatchEvent(new env.window.Event('change',{bubbles:true}));
    assert.equal(env.app.getProject().annotations.roles['role-a'].deviceType,'');
  } finally {env.close();}
});

test('manual fields survive JSON/HTML saves and work-file reopening', async () => {
  const env=mount(),doc=env.window.document;
  try {
    const ssid=doc.querySelector('[data-manual-ssid]');
    ssid.value='company-guest';ssid.dispatchEvent(new env.window.Event('input',{bubbles:true}));
    const type=doc.querySelector('[data-device-type]');
    type.value='ETC';type.dispatchEvent(new env.window.Event('change',{bubbles:true}));
    assert.equal(env.app.saveProject(),true);
    const json=await env.downloaded(), parsed=Core.parseProject(json);
    assert.equal(parsed.annotations.roles['role-a'].manualSsid,'company-guest');
    assert.equal(parsed.annotations.roles['role-a'].deviceType,'ETC');
    assert.equal(env.app.openText(json),true);
    assert.equal(doc.querySelector('[data-manual-ssid]').value,'company-guest');
    assert.equal(doc.querySelector('[data-device-type]').value,'ETC');
    assert.equal(env.app.saveHtml(),true);
    const html=await env.downloaded();
    const parsedHtml=new JSDOM(html).window.document;
    const restored=Core.parseProject(parsedHtml.getElementById('annotation-project-data').textContent);
    assert.equal(restored.annotations.roles['role-a'].manualSsid,'company-guest');
    assert.equal(restored.annotations.roles['role-a'].deviceType,'ETC');
  } finally {env.close();}
});

test('manual fields are reused only for the exact controller and Role', () => {
  const old=fixture();
  old.annotations.roles['role-a']=record('visitor-wireless','PC');
  const next=fixture();
  next.projectId='later-project';
  next.snapshot.id='later-snapshot';
  const result=Core.reconcileProjects(next,old,{now:'2026-11-17T00:00:00Z'});
  const reused=result.project.annotations.roles['role-a'];
  assert.equal(reused.manualSsid,'visitor-wireless');
  assert.equal(reused.deviceType,'PC');
  const other=fixture();
  other.snapshot.controllers[0].host='192.0.2.99';
  const unresolved=Core.reconcileProjects(other,old,{now:'2026-11-17T00:00:00Z'});
  assert.equal(unresolved.project.annotations.roles['role-a'],undefined);
  assert.equal(unresolved.project.unresolvedAnnotations[0].annotation.manualSsid,'visitor-wireless');
});

test('same-named Roles on different controllers keep independent manual assignments', () => {
  const p=fixture();
  p.snapshot.controllers.push({...p.snapshot.controllers[0],id:'controller-b',host:'192.0.2.2'});
  p.snapshot.roles.push({...p.snapshot.roles[0],id:'role-b',controllerId:'controller-b'});
  p.annotations.roles['role-a']=record('corp-a','PC');
  p.annotations.roles['role-b']=record('corp-b','mobile');
  const env=mount(p);
  try {
    assert.equal(env.window.document.querySelector('[data-manual-ssid]').value,'corp-a');
    env.window.document.querySelector('[data-open-role="role-b"]').click();
    assert.equal(env.window.document.querySelector('[data-manual-ssid]').value,'corp-b');
    assert.equal(env.window.document.querySelector('[data-device-type]').value,'mobile');
    assert.equal(env.app.getProject().annotations.roles['role-a'].manualSsid,'corp-a');
  } finally {env.close();}
});

test('PDF and Excel include manually entered SSID and device beside Role, not collected SSID', () => {
  const p=fixture();
  p.annotations.roles['role-a']=record('<SSID>&guest','mobile');
  const model=Core.buildExportModel(p,{type:'all'});
  const workbook=Export.createWorkbook(model,ExcelJS);
  const sheet=workbook.getWorksheet('Role 설명');
  const header=sheet.getRow(1).values;
  const row=sheet.getRow(2);
  assert.equal(row.getCell(header.indexOf('수집 SSID')).value,'corp');
  assert.equal(row.getCell(header.indexOf('SSID 명 (직접 입력)')).value,'<SSID>&guest');
  assert.equal(row.getCell(header.indexOf('단말 구분')).value,'mobile');
  const html=Export.printHtml(model);
  assert.match(html,/직접 입력 SSID \/ 단말/);
  assert.match(html,/&lt;SSID&gt;&amp;guest/);
  assert.match(html,/mobile/);
  assert.ok(!html.includes('<SSID>&guest'));
});

test('invalid manual SSID edits restore prior value without corrupting workspace', () => {
  const env=mount();
  try {
    const input=env.window.document.querySelector('[data-manual-ssid]');
    input.value='x'.repeat(513);
    input.dispatchEvent(new env.window.Event('input',{bubbles:true}));
    assert.equal(input.value,'');
    assert.equal(env.app.getProject().annotations.roles['role-a'],undefined);
    assert.equal(env.window.document.getElementById('ann-status').dataset.state,'error');
  } finally {env.close();}
});
