'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {JSDOM} = require('jsdom');
const Core = require('../../src/wlc_role_acl_collector/static/annotation_core.js');
const fixture = require('./editor_fixture.js');
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
test('detailed Excel reports which common ACL visibility its counts reflect', () => {
  for (const [showCommonAcl,expected] of [[false,/공통 ACL을 제외/],[true,/공통 ACL을 포함/]]) {
    const book=exporter.createWorkbook({...model(),showCommonAcl},ExcelJS);
    const row=book.getWorksheet('보고 요약').getSheetValues().find(cells=>cells?.includes('보고서 수치'));
    assert.match(row.at(-1),expected);
    assert.doesNotMatch(row.at(-1),/숨긴 행도 보고 범위에 포함/);
  }
});
test('print view is complete inert HTML with full notes and all report sections', () => {
  assert.equal(typeof exporter.printHtml,'function');
  const html=exporter.printHtml(model());
  assert.ok(html.startsWith('<!doctype html>'));assert.ok(html.includes('lang="ko"'));
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));assert.ok(!/<script\b|\bon\w+=|<iframe\b|<link\b/i.test(html));
  for(const text of [longNote,'=1+1','orphan-a','unmatched note','office','partial','2026-11-16T13:00:00Z','선택 역할: selected']) assert.ok(html.includes(text),text.slice(0,40));
  assert.ok(html.includes('A4 landscape'));assert.ok(html.includes('table-header-group'));assert.ok(html.includes('overflow-wrap:anywhere'));
});
test('PDF detail rows keep same-named controllers and policy occurrences distinguishable', () => {
  const p=fixture(), controller=p.snapshot.controllers[0], role=p.snapshot.roles[0], rule=p.snapshot.rules[0];
  const annotation=p.annotations.rules['rule-a'];
  const cases=[
    {suffix:'a',host:'192.0.2.1',port:22,scope:'/md/first',aliasValue:'198.51.100.10'},
    {suffix:'b',host:'192.0.2.2',port:2222,scope:'/md/second',aliasValue:'203.0.113.10'}
  ];
  p.snapshot.controllers=[];p.snapshot.roles=[];p.snapshot.rules=[];p.annotations.rules={};
  for (const c of cases) {
    const cid='controller-'+c.suffix, rid='role-'+c.suffix, ruleId='rule-'+c.suffix;
    p.snapshot.controllers.push({...controller,id:cid,host:c.host,port:c.port,scope:c.scope});
    p.snapshot.roles.push({...role,id:rid,controllerId:cid});
    p.snapshot.rules.push({...rule,id:ruleId,controllerId:cid,roleId:rid});
    p.snapshot.aliases.push({id:'alias-'+c.suffix,controllerId:cid,name:'SAME_ALIAS',entries:[{type:'host',value:c.aliasValue,raw:'host '+c.aliasValue}]});
    p.annotations.roles[rid]={...annotation,text:'Role note '+c.suffix};
    p.annotations.rules[ruleId]={...annotation,text:'Rule note '+c.suffix};
    p.changes.push({type:'context_changed',controllerId:cid,roleId:rid,ruleId:ruleId,message:'Change '+c.suffix,previousRaw:rule.raw});
  }
  const dom=new JSDOM(exporter.printHtml(Core.buildExportModel(p,{type:'all'})));
  try {
    const sections=new Map(Array.from(dom.window.document.querySelectorAll('section'),s=>[s.querySelector('h2').textContent,s]));
    for (const c of cases) {
      const expectations=[
        ['Role 설명','Role note '+c.suffix,'role-'+c.suffix],
        ['ACL 상세','Rule note '+c.suffix,'rule-'+c.suffix],
        ['변경·확인 사항','Change '+c.suffix,'rule-'+c.suffix],
        ['Alias 상세',c.aliasValue,'alias-'+c.suffix]
      ];
      for (const [section,marker,entityId] of expectations) {
        const row=Array.from(sections.get(section).querySelectorAll('tbody tr')).find(r=>r.textContent.includes(marker));
        assert.ok(row,section+' row exists');
        const target=row.cells[0].textContent;
        for (const value of ['controller-'+c.suffix,c.host,String(c.port),c.scope,entityId]) {
          assert.ok(target.includes(value),section+' target must identify '+value);
        }
        assert.ok(!target.includes(c.suffix==='a'?'192.0.2.2':'192.0.2.1'),section+' must not identify the other controller');
      }
    }
  } finally {dom.window.close();}
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

test('Excel and print-ready PDF source show readable Windows PC and MacBook labels', () => {
  for(const [deviceType,label] of [['windows_pc','윈도우 PC'],['macbook','맥북'],['PC','PC']]) {
    const p=fixture(),roleNote={...p.annotations.rules['rule-a'],deviceType,manualSsid:'test-ssid'};
    p.annotations.roles['role-a']=roleNote;
    const report=Core.buildExportModel(p,{type:'all'},'2026-11-18T00:00:00Z');
    const sheet=exporter.createWorkbook(report,ExcelJS).getWorksheet('Role 설명');
    const headers=sheet.getRow(1).values,column=headers.indexOf('단말 구분');
    assert.ok(column>0);
    assert.equal(sheet.getRow(2).getCell(column).value,label);
    const pdfHtml=exporter.printHtml(report);
    assert.ok(pdfHtml.includes('단말 구분: '+label),deviceType);
  }
});


test('compact ACL workbook defaults to nine visible reporting fields and preserves every annotation chunk', async () => {
  const m=model(), book=exporter.createWorkbook(m,ExcelJS,{profile:'simple'});
  assert.deepEqual(book.worksheets.map(s=>s.name),['ACL 간단 보고']);
  const sheet=book.getWorksheet('ACL 간단 보고');
  const headers=sheet.getRow(1).values.slice(1,10);
  assert.deepEqual(headers,['컨트롤러','Role','ACL','순서','출발지','목적지','서비스','동작','행별 주석']);
  assert.ok(sheet.getColumn(10).hidden);
  assert.ok(sheet.getColumn(11).hidden);
  assert.deepEqual(sheet.autoFilter.from,{row:1,column:1});
  assert.deepEqual(sheet.autoFilter.to,{row:sheet.rowCount,column:9});
  assert.ok(sheet.getRow(2).getCell(1).value.includes('<controller>'));
  assert.equal(sheet.getRow(2).getCell(3).value,'acl-a');
  assert.equal(sheet.getRow(2).getCell(8).value,'permit');
  const chunks=[];
  sheet.eachRow((row,n)=>{if(n>1){chunks.push(row.getCell(9).value||'');
    row.eachCell(cell=>{assert.notEqual(cell.type,ExcelJS.ValueType.Formula);});}});
  assert.equal(chunks.join(''),longNote);
  assert.equal(sheet.getRow(2).getCell(10).value,'1');
  const bytes=await exporter.workbookBytes(m,ExcelJS,{profile:'simple'});
  const roundtrip=new ExcelJS.Workbook(); await roundtrip.xlsx.load(bytes);
  assert.equal(roundtrip.getWorksheet('ACL 간단 보고').getRow(2).getCell(3).value,'acl-a');
  assert.equal(roundtrip.getWorksheet('Role 설명'),undefined);
});

test('compact ACL output keeps duplicate rule occurrences and scope filtering without leaking internal IDs',()=>{
  const p=fixture(), rule=p.snapshot.rules[0];
  rule.acl='ra-guard';
  p.snapshot.rules.push({...rule,id:'duplicate-rule',ordinal:2,sequence:'2'});
  p.annotations.rules['duplicate-rule']={...p.annotations.rules['rule-a'],text:'별도 규칙 설명'};
  const m=Core.buildExportModel(p,{type:'all'});
  const sheet=exporter.createWorkbook(m,ExcelJS,{profile:'simple'}).getWorksheet('ACL 간단 보고');
  assert.equal(sheet.rowCount,3);
  assert.equal(sheet.getRow(2).getCell(9).value,p.annotations.rules['rule-a'].text);
  assert.equal(sheet.getRow(3).getCell(9).value,'별도 규칙 설명');
  assert.deepEqual(sheet.getColumn(3).values.slice(2),['ra-guard','ra-guard']);
  const detail=exporter.createWorkbook(m,ExcelJS,{profile:'detailed'}).getWorksheet('ACL 상세');
  const aclColumn=detail.getRow(1).values.indexOf('ACL');
  assert.deepEqual(detail.getColumn(aclColumn).values.slice(2),['ra-guard','ra-guard']);
  const headers=sheet.getRow(1).values.join('|');
  assert.ok(!headers.includes('규칙 ID'));
  assert.ok(!headers.includes('수집본'));
  const empty=Core.buildExportModel(p,{type:'selected',roleIds:[]});
  assert.equal(exporter.createWorkbook(empty,ExcelJS,{profile:'simple'}).getWorksheet('ACL 간단 보고').rowCount,1);
});


test('compact Excel disambiguates controllers with the same display name by actual endpoint',()=>{
  const p=fixture(),c=p.snapshot.controllers[0],r=p.snapshot.roles[0],rule=p.snapshot.rules[0];
  p.snapshot.controllers.push({...c,id:'controller-b',host:'192.0.2.99'});
  p.snapshot.roles.push({...r,id:'role-b',controllerId:'controller-b'});
  p.snapshot.rules.push({...rule,id:'rule-b',controllerId:'controller-b',roleId:'role-b'});
  const model=Core.buildExportModel(p,{type:'all'});
  const sheet=exporter.createWorkbook(model,ExcelJS,{profile:'simple'}).getWorksheet('ACL 간단 보고');
  const labels=[sheet.getRow(2).getCell(1).value,sheet.getRow(3).getCell(1).value];
  assert.ok(labels[0].includes('192.0.2.1'),labels[0]);
  assert.ok(labels[1].includes('192.0.2.99'),labels[1]);
  assert.notEqual(labels[0],labels[1]);
});

test('compact XLSX omits blank notes and keeps continuation markers beside the eight visible columns', async () => {
  const m=model();
  m.rules[0].source=longNote;
  m.rules[0].annotation.text=' \t\n\u00a0';
  m.rules.push({...m.rules[0],id:'rule-b',source:'any',annotation:null});
  const bytes=await exporter.workbookBytes(m,ExcelJS,{profile:'simple'});
  const book=new ExcelJS.Workbook();
  await book.xlsx.load(bytes);
  const sheet=book.getWorksheet('ACL 간단 보고');
  assert.deepEqual(sheet.getRow(1).values.slice(1),[
    '컨트롤러','Role','ACL','순서','출발지','목적지','서비스','동작','_레코드 번호','_조각 / 전체'
  ]);
  assert.equal(sheet.autoFilter,'A1:H4');
  assert.equal(sheet.getColumn(8).width,14);
  assert.equal(sheet.getColumn(8).hidden,false);
  assert.equal(sheet.getColumn(9).hidden,true);
  assert.equal(sheet.getColumn(10).hidden,true);
  assert.deepEqual(sheet.getColumn(9).values.slice(2),['1','1','2']);
  assert.deepEqual(sheet.getColumn(10).values.slice(2),['1/2','2/2','1/1']);
  assert.equal(sheet.getCell('E2').value+sheet.getCell('E3').value,longNote);
  assert.equal(sheet.getCell('H3').value,'permit');
});

test('Excel note columns follow the selected and review scopes and keep original text in mixed scopes', () => {
  const p=fixture(), note=p.annotations.rules['rule-a'];
  const realNote='  =운영 메모\n둘째 줄  ', blankNote=' \t ';
  note.text=realNote;
  p.snapshot.roles.push({...p.snapshot.roles[0],id:'role-b',name:'GUEST'});
  p.snapshot.rules.push({...p.snapshot.rules[0],id:'rule-b',roleId:'role-b'});
  p.annotations.rules['rule-b']={...note,text:blankNote,status:'needs_review',reasons:['순서 변경']};
  for(const [profile,sheetName,header] of [['simple','ACL 간단 보고','행별 주석'],['detailed','ACL 상세','주석']]){
    const sheetFor=scope=>exporter.createWorkbook(Core.buildExportModel(p,scope),ExcelJS,{profile}).getWorksheet(sheetName);
    for(const scope of [{type:'selected',roleIds:[]},{type:'selected',roleIds:['role-b']},{type:'review'}]){
      assert.equal(sheetFor(scope).getRow(1).values.includes(header),false);
    }
    const all=sheetFor({type:'all'});
    const column=all.getRow(1).values.indexOf(header);
    assert.deepEqual(all.getColumn(column).values.slice(2),[realNote,blankNote]);
  }
});

test('detailed XLSX decides each note column independently and retains review metadata under its header', async () => {
  const m=model();
  m.rules[0].annotation.text=' \t ';
  async function detailBook(){
    const bytes=await exporter.workbookBytes(m,ExcelJS,{profile:'detailed'});
    const book=new ExcelJS.Workbook();
    await book.xlsx.load(bytes);
    return book;
  }
  function cellFor(sheet,rowNumber,header){
    const index=sheet.getRow(1).values.indexOf(header);
    assert.ok(index>0,header);
    return sheet.getRow(rowNumber).getCell(index).value;
  }
  let book=await detailBook();
  const acl=book.getWorksheet('ACL 상세');
  assert.equal(acl.getRow(1).values.includes('주석'),false);
  assert.equal(cellFor(acl,2,'확인 상태'),'needs_review');
  assert.equal(cellFor(acl,2,'검토 사유'),'규칙 순서 변경');
  assert.equal(cellFor(acl,2,'원본 주석 ID'),'old-rule');
  assert.equal(cellFor(acl,2,'원본 확인 시각'),'2026-11-15T00:00:00Z');
  assert.equal(cellFor(book.getWorksheet('Role 설명'),2,'주석'),'=1+1');
  assert.equal(cellFor(book.getWorksheet('변경·확인 사항'),3,'주석'),'unmatched note');

  m.roles[0].annotation.text='';
  m.unresolvedAnnotations[0].annotation.text='\n';
  book=await detailBook();
  const roles=book.getWorksheet('Role 설명'), changes=book.getWorksheet('변경·확인 사항');
  assert.equal(roles.getRow(1).values.includes('주석'),false);
  assert.equal(cellFor(roles,2,'확인 상태'),'needs_review');
  assert.equal(changes.getRow(1).values.includes('주석'),false);
  assert.equal(cellFor(changes,2,'사유 / 변경 내용'),'순서 변경');
  assert.equal(cellFor(changes,3,'원본 주석 ID'),'old-rule');
});

test('unreviewed whitespace alone adds no review row while manual role fields still require review', () => {
  const report={
    roles:[
      {id:'manual-ssid',annotation:{status:'unreviewed',manualSsid:'기업망'}},
      {id:'manual-device',annotation:{status:'unreviewed',deviceType:'PC'}}
    ],
    rules:[{id:'spaces-only',roleId:'manual-ssid',annotation:{status:'unreviewed',text:' \t\n'}}]
  };
  const changes=exporter.createWorkbook(report,ExcelJS).getWorksheet('변경·확인 사항');
  const idColumn=changes.getRow(1).values.indexOf('레코드 ID');
  assert.deepEqual(changes.getColumn(idColumn).values.slice(2),['manual-ssid','manual-device']);
});
