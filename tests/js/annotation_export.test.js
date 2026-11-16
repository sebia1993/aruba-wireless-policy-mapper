'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const staticDir = path.resolve(__dirname, '../../src/wlc_role_acl_collector/static');
const target = path.join(staticDir, 'annotation_export.js');
const exporter = fs.existsSync(target) ? require(target) : {};
const ExcelJS = require(path.join(staticDir, 'exceljs.min.js'));
const longNote = '한'.repeat(32766) + '😀' + '\n=1+1 끝';
function model() {
  const annotation = {text:longNote,status:'needs_review',updatedAt:'2026-11-16T12:00:00Z',confirmedAt:null,reasons:['규칙 순서 변경'],source:{projectId:'prior',snapshotId:'before',recordId:'old-rule',confirmedAt:'2026-11-15T00:00:00Z'}};
  return {projectId:'project-a',snapshotId:'snapshot-a',revision:7,collectedAt:'2026-11-16T10:00:00Z',updatedAt:'2026-11-16T12:00:00Z',exportedAt:'2026-11-16T13:00:00Z',scopeLabel:'선택 역할: selected',summary:{controllerCount:1,roleCount:1,ruleCount:1,annotatedRuleCount:1,needsReviewCount:1},controllers:[{id:'ctrl-a',name:'<controller>',host:'192.0.2.1',port:22,scope:'effective',identityKnown:true,coverage:'partial',failedCommands:['show rights']}],roles:[{id:'role-a',controllerId:'ctrl-a',controllerName:'<controller>',name:'selected',ssids:['ssid-a'],roleTypes:['user'],aclOrder:['acl-a'],bindingRaw:['access-list session acl-a'],contextComplete:false,observedUsers:2,annotation:{...annotation,text:'=1+1'}}],rules:[{id:'rule-a',controllerId:'ctrl-a',controllerName:'<controller>',roleId:'role-a',roleName:'selected',acl:'acl-a',sequence:'1',ordinal:1,raw:'any any any permit <script>alert(1)</script>',source:'any',destination:'any',service:'any',action:'permit',sourceInterpretation:'any',destinationInterpretation:'any',annotation}],aliases:[{id:'alias-a',controllerId:'ctrl-a',name:'office',entries:[{type:'host',value:'192.0.2.5',raw:'host 192.0.2.5'}]}],localNetworks:[],issues:[{controllerId:'ctrl-a',roleId:'role-a',message:'수집 불완전'}],changes:[{type:'changed',controllerId:'ctrl-a',roleId:'role-a',ruleId:'rule-a',message:'순서 변경',previousRaw:'old permit'}],unresolvedAnnotations:[{id:'orphan-a',kind:'rule',controllerId:'old-ctrl',controllerName:'old controller',roleName:'old role',acl:'old-acl',raw:'old deny',annotation:{...annotation,text:'unmatched note'},reason:'no exact match',candidateIds:['rule-a'],sourceProjectId:'prior',sourceSnapshotId:'before'}]};
}
test('exports the supplied scope into five readable sheets with coverage and provenance', () => {
  assert.equal(typeof exporter.createWorkbook, 'function');
  const book=exporter.createWorkbook(model(),ExcelJS);
  assert.deepEqual(book.worksheets.map(s=>s.name),['보고 요약','Role 설명','ACL 상세','변경·확인 사항','Alias 상세']);
  const all=book.worksheets.flatMap(s=>s.getSheetValues().flat(2)).join('\n');
  for (const value of ['project-a','snapshot-a','선택 역할: selected','partial','show rights','수집 불완전','old-rule','orphan-a','unmatched note','old-acl']) assert.ok(all.includes(value),value);
  assert.ok(!all.includes('hidden-role'));
  for (const sheet of book.worksheets) { assert.equal(sheet.views[0].state,'frozen');assert.ok(sheet.autoFilter);assert.equal(sheet.getRow(1).font.bold,true); }
});
test('preserves formula-like text and splits Korean and emoji losslessly at Excel limits', async () => {
  assert.equal(typeof exporter.workbookBytes,'function');
  const bytes=await exporter.workbookBytes(model(),ExcelJS);
  assert.ok(bytes instanceof Uint8Array); assert.equal(bytes[0],0x50);assert.equal(bytes[1],0x4b);
  const book=new ExcelJS.Workbook(); await book.xlsx.load(bytes);
  const roles=book.getWorksheet('Role 설명');
  assert.ok(roles.getSheetValues().some(row=>row&&row.some(v=>v==='=1+1')));
  const sheet=book.getWorksheet('ACL 상세');
  const headers=sheet.getRow(1).values;
  const noteColumn=headers.indexOf('주석');
  const reconstructed=[];
  sheet.eachRow((row,n)=>{ if(n>1) reconstructed.push(row.getCell(noteColumn).value||''); row.eachCell(c=>{if(typeof c.value==='string'){assert.ok(c.value.length<=32767);assert.ok(!/[\uD800-\uDBFF]$/.test(c.value));} assert.notEqual(c.type,ExcelJS.ValueType.Formula);}); });
  assert.equal(reconstructed.join(''),longNote);
});
test('print view is complete inert HTML with full notes and all report sections', () => {
  assert.equal(typeof exporter.printHtml,'function');
  const html=exporter.printHtml(model());
  assert.ok(html.startsWith('<!doctype html>'));assert.ok(html.includes('lang="ko"'));
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));assert.ok(!/<script\b|\bon\w+=|<iframe\b|<link\b/i.test(html));
  for(const text of [longNote,'=1+1','orphan-a','unmatched note','office','partial','2026-11-16T13:00:00Z','선택 역할: selected']) assert.ok(html.includes(text),text.slice(0,40));
  assert.ok(html.includes('A4 landscape'));assert.ok(html.includes('table-header-group'));assert.ok(html.includes('overflow-wrap:anywhere'));
});
test('browser UMD works offline from the supplied model without consulting document rows', () => {
  const sandbox = {document:new Proxy({}, {get(){throw new Error('Exporter must not read the editor DOM');}})};
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(target,'utf8'),sandbox);
  assert.equal(typeof sandbox.AnnotationExport.printHtml,'function');
  assert.ok(sandbox.AnnotationExport.printHtml(model()).includes('선택 역할: selected'));
  assert.equal(sandbox.AnnotationExport.createWorkbook(model(),ExcelJS).getWorksheet('Role 설명').rowCount,2);
});
module.exports={model,longNote};
