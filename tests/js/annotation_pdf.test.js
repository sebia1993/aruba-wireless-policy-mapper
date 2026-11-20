'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const Core=require('../../src/wlc_role_acl_collector/static/annotation_core.js');
const Pdf=require('../../src/wlc_role_acl_collector/static/annotation_pdf.js');
const fixture=require('./editor_fixture.js');

function model(p=fixture(),scope={type:'all'}){
  return Core.buildExportModel(p,scope,'2026-11-18T14:00:00Z');
}
function allText(node){
  if(node==null)return '';
  if(typeof node==='string'||typeof node==='number')return String(node);
  if(Array.isArray(node))return node.map(allText).join('\n');
  if(typeof node==='object')return [allText(node.text),allText(node.content),allText(node.table?.body)].join('\n');
  return '';
}

test('simple and detailed PDFs identify Role, direct endpoint, short and appendix Alias network references',()=>{
  const p=fixture(),role=p.snapshot.roles[0],rule=p.snapshot.rules[0];
  role.networkReferences=['WLC 설정 · 역할 참조'];
  rule.source='host 192.0.2.7';rule.sourceNetworkReference='출발지 참조';rule.destination='alias SMALL';
  p.snapshot.rules.push({...rule,id:'second',ordinal:2,destination:'alias LARGE'});
  for(const [name,size] of [['SMALL',1],['LARGE',4]]){
    p.snapshot.aliases.push({id:name,name,controllerId:role.controllerId,entries:Array.from({length:size},(_,i)=>({
      type:'host',value:'192.0.2.'+(i+1),raw:'host 192.0.2.'+(i+1),networkReference:name+' 참조 '+i}))});
  }
  p.snapshot.rules.push({...rule,id:'common',acl:'ra-guard',ordinal:3,sourceNetworkReference:'HIDDEN LABEL'});
  for(const profile of ['simple','detailed']){
    const text=allText(Pdf.documentDefinition(model(p,{type:'all',showCommonAcl:false}),{profile}).content);
    for(const ref of [role.networkReferences[0],rule.sourceNetworkReference,'SMALL 참조 0','LARGE 참조 3']) assert.ok(text.includes(ref),ref);
    assert.ok(!text.includes('HIDDEN LABEL'));
  }
});

test('management PDF uses searchable A4 content with Korean summary, evidence and appendix',()=>{
  const p=fixture();
  p.annotations.roles['role-a']={...p.annotations.rules['rule-a'],manualSsid:'corp-ssid',deviceType:'macbook',text:'상급 보고용 설명'};
  p.annotations.rules['rule-a'].text='업무망 허용';
  const m=model(p),def=Pdf.documentDefinition(m),text=allText(def.content);
  assert.equal(def.pageSize,'A4');
  assert.equal(def.pageOrientation,'portrait');
  assert.equal(def.defaultStyle.font,'NanumGothic');
  assert.match(text,/무선랜 Role 및 ACL 정책 점검 보고서/);
  for(const part of ['컨트롤러 및 수집 신뢰도','Role별 정책 현황','추가 확인·변경','Role별 ACL 상세','공통 ACL','자료 범위','맥북','corp-ssid','업무망 허용','상급 보고용 설명']) {
    assert.ok(text.includes(part),part);
  }
  assert.equal(typeof def.footer,'function');
  assert.equal(typeof def.header,'function');
  assert.ok(def.content.some(x=>x.table&&x.table.headerRows===1),'table headers repeat across pages');
});

test('common ACL grouping preserves every occurrence and exact controller identity',()=>{
  const p=fixture(),base=p.snapshot.rules[0],controller=p.snapshot.controllers[0],role=p.snapshot.roles[0];
  p.snapshot.controllers.push({...controller,id:'controller-b',host:'192.0.2.2'});
  p.snapshot.roles.push({...role,id:'role-b',controllerId:'controller-b'});
  const names=['global-sacl','re-guard','logon-control','logon-control-v2'];
  for(let i=0;i<names.length;i++){
    const suffix=String(i),isOther=i===2;
    const rule={...base,id:'common-'+suffix,controllerId:isOther?'controller-b':'controller-a',
      roleId:isOther?'role-b':'role-a',acl:names[i],ordinal:i+2,raw:'raw '+names[i]};
    p.snapshot.rules.push(rule);
    p.annotations.rules[rule.id]={...p.annotations.rules['rule-a'],text:'주석 '+names[i]};
  }
  const output=allText(Pdf.documentDefinition(model(p)).content);
  for(const name of names)assert.ok(output.includes('주석 '+name),name);
  assert.ok(output.includes('192.0.2.1'));
  assert.ok(output.includes('192.0.2.2'));
  assert.match(output,/Role ID: role-b/);
  assert.match(output,/규칙 ID: common-2/);
  assert.match(output,/logon-control-v2/);
  assert.match(output,/공통 정책 규칙/);
  assert.match(output,/공통 ACL/);
});

test('PDF model scope remains the authoritative source, no stale DOM or extra controllers',()=>{
  const p=fixture();
  p.snapshot.controllers.push({...p.snapshot.controllers[0],id:'controller-b',host:'192.0.2.2'});
  p.snapshot.roles.push({...p.snapshot.roles[0],id:'role-b',controllerId:'controller-b',name:'GUEST'});
  p.snapshot.rules.push({...p.snapshot.rules[0],id:'rule-b',roleId:'role-b',controllerId:'controller-b'});
  const selected=model(p,{type:'selected',roleIds:['role-b']});
  const output=allText(Pdf.documentDefinition(selected).content);
  assert.ok(output.includes('GUEST'));
  assert.ok(!output.includes('Role ID: role-a'));
  assert.ok(!output.includes('192.0.2.1'));
  assert.ok(output.includes('192.0.2.2'));
});

test('hidden common ACLs have no PDF appendix, count or included-policy guidance',()=>{
  const report={...model(),showCommonAcl:false};
  const detailed=Pdf.documentDefinition(report);
  const headings=detailed.content.filter(item=>item.style==='sectionHeading').map(item=>item.text);
  assert.equal(headings.length,6);
  assert.equal(headings[5],'6. 자료 범위');
  assert.doesNotMatch(allText(detailed.content),/공통 정책 규칙|공통 0건|ra-guard|공통 ACL 규칙은 다음 부록/);
  assert.doesNotMatch(allText(Pdf.documentDefinition(report,{profile:'simple'}).content),/공통 ACL도 보고 범위에 포함/);
  report.rules=[];
  assert.match(allText(Pdf.documentDefinition(report).content),/표시할 전용 ACL 규칙이 없습니다/);
  assert.match(allText(Pdf.documentDefinition(report,{profile:'simple'}).content),/표시할 ACL 규칙이 없습니다/);
  const inclusive=Pdf.documentDefinition({...report,showCommonAcl:true});
  assert.ok(inclusive.content.some(item=>item.style==='sectionHeading' && item.text.startsWith('6. 공통 ACL')));
});

function aclTables(report,profile){
  return Pdf.documentDefinition(report,{profile}).content
    .map(item=>item.table)
    .filter(table=>table && ['순서','ACL / 순서','Role / 적용 정보'].includes(table.body[0][0].text));
}

test('both PDF profiles omit empty ACL columns based on the selected scope and keep all rows',()=>{
  const p=fixture(),base=p.snapshot.rules[0],annotation=p.annotations.rules['rule-a'];
  p.snapshot.roles.push({...p.snapshot.roles[0],id:'selected',name:'GUEST'});
  p.annotations.roles.selected={...annotation,text:'Role 설명만 작성'};
  for(const [id,acl] of [['own','GUEST'],['common-1','global-sacl'],['common-2','global-sacl']]){
    p.snapshot.rules.push({...base,id,roleId:'selected',acl});
  }
  p.annotations.rules.own={...annotation,status:'unreviewed',text:' \t\n '};
  const report=model(p,{type:'selected',roleIds:['selected']});
  for(const [profile,columns] of [['simple',5],['detailed',2]]){
    const tables=aclTables(report,profile);
    assert.deepEqual(tables.map(table=>table.body.length-1),[1,2]);
    for(const table of tables){
      assert.equal(table.widths.length,columns);
      for(const row of table.body)assert.equal(row.length,columns);
    }
  }
  const detailed=allText(Pdf.documentDefinition(report).content);
  assert.match(detailed,/Role 설명만 작성/);
  assert.doesNotMatch(detailed,/ACL 확인|주석 미작성|규칙 ID: rule-a/);
});

test('detailed PDF preserves explicit ACL statuses without adding a note column or empty placeholders',()=>{
  const p=fixture(),base=p.snapshot.rules[0],annotation=p.annotations.rules['rule-a'];
  Object.assign(annotation,{text:' ',status:'reviewed'});
  for(const [id,status] of [['common-1','needs_review'],['common-2','reused']]){
    p.snapshot.rules.push({...base,id,acl:'global-sacl'});
    p.annotations.rules[id]={...annotation,status};
  }
  const report=model(p);
  const tables=aclTables(report,'detailed');
  assert.deepEqual(tables.map(table=>table.body[0].map(cell=>cell.text)),[
    ['ACL / 순서','수집 규칙 원문'],['Role / 적용 정보','원문 정책']
  ]);
  assert.match(allText(tables[0].body[1]),/확인 상태: 확인 완료/);
  assert.match(allText(tables[1].body[1]),/확인 상태: 재확인 필요/);
  assert.match(allText(tables[1].body[2]),/확인 상태: 이전 주석 재사용/);
  const followups=Pdf.documentDefinition(report).content.find(item=>item.table?.body[0][0].text==='유형').table;
  assert.deepEqual(followups.body.slice(1).map(row=>allText(row[2]).trim()),['재확인 필요','이전 주석 재사용']);
  for(const table of aclTables(report,'simple'))assert.equal(table.widths.length,5);
});

test('one common ACL note enables the note column across the report and preserves the exact text',()=>{
  const p=fixture(),base=p.snapshot.rules[0],annotation=p.annotations.rules['rule-a'];
  const original='  공통 ACL\n두 번째 줄  ';
  Object.assign(annotation,{text:' \t ',status:'unreviewed'});
  p.snapshot.rules.push({...base,id:'common',acl:'ra-guard'});
  p.annotations.rules.common={...annotation,status:'reviewed',text:original};
  const report=model(p);
  for(const [profile,heading] of [['simple','행별 주석'],['detailed','주석 및 확인']]){
    const [own,shared]=aclTables(report,profile);
    for(const table of [own,shared]){
      assert.equal(table.body[0].at(-1).text,heading);
      assert.equal(table.widths.length,table.body[0].length);
    }
    assert.equal(own.body[1].at(-1).text,'');
    assert.equal(shared.body[1].at(-1).text,profile==='simple'?original:'확인 완료\n'+original);
  }
});

test('invalid source data and excessive text are rejected without partial PDF success',()=>{
  assert.throws(()=>Pdf.documentDefinition({roles:[],controllers:[]}),/모델/);
  const large=model();large.rules[0].annotation.text='x'.repeat(8*1024*1024);
  assert.throws(()=>Pdf.documentDefinition(large),/크기/);
});

test('pdfMake adapter creates actual binary and checks bundled Hangul font',async()=>{
  const fake={
    vfs:{'NanumGothic-Regular.ttf':'fake-font'},
    addFonts(f){this.registered=f;},
    createPdf(def){
      assert.equal(def.defaultStyle.font,'NanumGothic');
      return {getBuffer: cb=>cb(Uint8Array.from([37,80,68,70,45,49,46,55,10]))};
    }
  };
  const bytes=await Pdf.createPdfBytes(model(),fake);
  assert.equal(String.fromCharCode(...bytes.slice(0,5)),'%PDF-');
  assert.ok(fake.registered.NanumGothic);
  await assert.rejects(Pdf.createPdfBytes(model(),{createPdf:()=>{throw Error('should not run');}}),/글꼴/);
});

test('vendored pdfmake and Nanum font generate a real Korean PDF offline',async()=>{
  const staticPath=path.resolve(__dirname,'../../src/wlc_role_acl_collector/static');
  const pdfmakeFile=path.join(staticPath,'pdfmake.min.js');
  const fontFile=path.join(staticPath,'pdfmake_nanum.vfs.js');
  assert.ok(fs.existsSync(pdfmakeFile),'offline pdfmake vendor missing');
  assert.ok(fs.existsSync(fontFile),'offline Korean font vendor missing');
  const pdfMake=require(pdfmakeFile);
  const vfs=require(fontFile);
  assert.equal(typeof pdfMake.createPdf,'function');
  pdfMake.vfs=Object.assign({},pdfMake.vfs||{},vfs);
  const bytes=await Pdf.createPdfBytes(model(),pdfMake);
  assert.ok(bytes.length>2500,'PDF with embedded Korean font should not be empty');
  assert.equal(String.fromCharCode(...bytes.slice(0,5)),'%PDF-');
});

for (const [profile, annotationHeader] of [['simple', '행별 주석'], ['detailed', '주석 및 확인']]) {
  test(`vendored ${profile} PDF paginates a tall first ACL row with repeated headers`, async () => {
    const pdfMake = require('../../src/wlc_role_acl_collector/static/pdfmake.min.js');
    const vfs = require('../../src/wlc_role_acl_collector/static/pdfmake_nanum.vfs.js');
    const font = 'NanumGothic-Regular.ttf';
    const fonts = {NanumGothic: {normal: font, bold: font, italics: font, bolditalics: font}};
    const project = fixture();
    const first = project.snapshot.rules[0];
    const lines = Array.from({length: 100}, (_, i) => 'NOTE' + String(i + 1).padStart(3, '0'));
    const annotation = project.annotations.rules[first.id];
    Object.assign(annotation, {status: 'reviewed', text: lines.join('\n')});
    project.snapshot.rules.push({...first, id: 'second-rule', ordinal: 2, sequence: '2'});
    project.annotations.rules['second-rule'] = {...annotation, text: 'NEXTROW'};

    const definition = Pdf.documentDefinition(model(project), {profile});
    const pdf = pdfMake.createPdf(definition, undefined, fonts, vfs);
    // pdfmake returns its final rendered lines after it has flushed the PDF stream.
    const pages = await new Promise(resolve => pdf._getPages({}, resolve));
    const pageLines = pages.map(page => page.items
      .filter(item => item.type === 'line')
      .map(item => item.item.inlines.map(inline => inline.text).join('')));
    const notePages = pageLines.filter(page => page.some(line => /^NOTE\d{3}$/.test(line)));
    const rendered = pageLines.flat().filter(line => /^NOTE\d{3}$/.test(line) || line === 'NEXTROW');
    assert.deepEqual(rendered, [...lines, 'NEXTROW']);
    assert.ok(notePages.length >= 2, 'the first ACL row spans multiple pages');
    for (const page of notePages) assert.ok(page.includes(annotationHeader), 'the column header repeats');
  });
}

test('common ACL naming variants stay only in PDF shared-policy appendix',()=>{
  const p=fixture(),base=p.snapshot.rules[0];
  p.snapshot.rules.push({...base,id:'quoted-common',acl:'“re‑guard”',raw:'any any any permit',ordinal:2});
  p.snapshot.rules.push({...base,id:'own-policy',acl:'re-guard-extra',raw:'any any any deny',ordinal:3});
  p.snapshot.rules.push({...base,id:'ra-common',acl:'ra-guard',raw:'any any any permit',ordinal:4});
  p.snapshot.rules.push({...base,id:'ra-own',acl:'ra-guard-extra',raw:'any any any deny',ordinal:5});
  p.annotations.rules['quoted-common']={...p.annotations.rules['rule-a'],text:'공통 규칙 주석'};
  p.annotations.rules['own-policy']={...p.annotations.rules['rule-a'],text:'Role 전용 주석'};
  const report=model(p);
  const compact=Pdf.documentDefinition(report,{profile:'simple'});
  const headings=compact.content.filter(item=>item.style==='groupHeading').map(item=>item.text);
  assert.deepEqual(headings.map(text=>text.split('   |   ACL: ')[1]),p.snapshot.rules.map(rule=>rule.acl));
  const definition=Pdf.documentDefinition(report,{profile:'detailed'});
  const content=definition.content;
  const techStart=content.findIndex(item=>String(item.text||'').includes('5. Role별 ACL 상세'));
  const sharedStart=content.findIndex(item=>String(item.text||'').includes('6. 공통 ACL'));
  assert.ok(techStart>=0 && sharedStart>techStart);
  assert.match(allText(content.slice(0,techStart)),/전용 3건\n공통 2건/);
  const serialized=node=>JSON.stringify(node);
  const tech=serialized(content.slice(techStart,sharedStart));
  const shared=serialized(content.slice(sharedStart));
  assert.ok(!tech.includes('공통 규칙 주석'),'shared rule must not duplicate in Role-only appendix');
  assert.ok(tech.includes('Role 전용 주석'),'independent custom ACL stays in Role appendix');
  assert.ok(shared.includes('공통 규칙 주석'),'shared policy appendix keeps full source note');
  assert.ok(shared.includes('규칙 ID: ra-common') && !tech.includes('규칙 ID: ra-common'));
  assert.ok(tech.includes('규칙 ID: ra-own') && !shared.includes('규칙 ID: ra-own'));
  const legend=content.find(item=>String(item.text||'').includes('공통 정책명'));
  assert.match(legend.text,/\bra-guard\b/);
});


test('compact PDF uses grouped landscape ACL rows with no detailed appendix while preserving occurrences',()=>{
  const p=fixture(),r=p.snapshot.rules[0];
  p.snapshot.rules.push({...r,id:'another-rule',ordinal:2,sequence:'2',destination:'10.30.0.0/16'});
  p.annotations.rules['another-rule']={...p.annotations.rules['rule-a'],text:'다른 ACL 행 주석'};
  const m=model(p),doc=Pdf.documentDefinition(m,{profile:'simple'});
  const output=allText(doc.content);
  assert.equal(doc.pageSize,'A4');
  assert.equal(doc.pageOrientation,'landscape');
  assert.ok(output.includes('ACL 규칙 간단 보고서'));
  for(const field of ['컨트롤러:','Role:','ACL:','출발지','목적지','서비스','동작','행별 주석','다른 ACL 행 주석']) {
    assert.ok(output.includes(field),field);
  }
  for(const absent of ['Role별 정책 현황','Alias 상세','기술 부록','스냅샷','프로젝트 ID']) {
    assert.ok(!output.includes(absent),absent);
  }
  const tables=doc.content.filter(x=>x.table);
  assert.ok(tables.length);
  assert.equal(tables[0].table.body.length,3,'all same-ACL occurrences retained');
  assert.equal(tables[0].table.headerRows,1);
  assert.ok(!output.includes(r.raw));
  assert.equal(m.rules.length,2,'export data remains intact');
});

test('compact PDF warns on partial controller coverage without changing detailed PDF',()=>{
  const p=fixture();
  p.snapshot.controllers[0].coverage='partial';
  const m=model(p);
  const concise=allText(Pdf.documentDefinition(m,{profile:'simple'}).content);
  const detailed=Pdf.documentDefinition(m,{profile:'detailed'});
  assert.match(concise,/수집 미완료/);
  assert.equal(detailed.pageOrientation,'portrait');
  assert.match(allText(detailed.content),/자료 범위/);
});


test('compact PDF differentiates identically named WLCs by endpoint without exposing internal IDs',()=>{
  const p=fixture(),c=p.snapshot.controllers[0],r=p.snapshot.roles[0],rule=p.snapshot.rules[0];
  p.snapshot.controllers.push({...c,id:'controller-b',host:'192.0.2.99'});
  p.snapshot.roles.push({...r,id:'role-b',controllerId:'controller-b'});
  p.snapshot.rules.push({...rule,id:'rule-b',controllerId:'controller-b',roleId:'role-b'});
  const doc=Pdf.documentDefinition(model(p),{profile:'simple'});
  const output=allText(doc.content);
  assert.ok(output.includes('192.0.2.1'));
  assert.ok(output.includes('192.0.2.99'));
  assert.ok(!output.includes('controller-b'));
});

function aliasReportFixture(){
  const p=fixture(), base=p.snapshot.rules[0], ctrl=p.snapshot.controllers[0], role=p.snapshot.roles[0];
  p.snapshot.controllers.push({...ctrl,id:'controller-b',host:'192.0.2.2'});
  p.snapshot.roles.push({...role,id:'role-b',controllerId:'controller-b'});
  Object.assign(base,{source:'alias SHORT',destination:'alias LONG'});
  p.snapshot.rules.push({...base,id:'second',source:'alias LONG',destination:'alias EMPTY',ordinal:2},
    {...base,id:'other',roleId:'role-b',controllerId:'controller-b',source:'alias UNKNOWN',destination:'alias LONG'},
    {...base,id:'common-alias',acl:'ra-guard',source:'any',destination:'alias PRIVATE',ordinal:3});
  function alias(controllerId,name,members){
    const entries=[{type:'description',value:'설명',raw:'description 설명'}];
    for(const value of members)entries.push({type:'host',value,raw:'host '+value});
    return {controllerId,id:controllerId+'-'+name,name,entries};
  }
  p.snapshot.aliases.push(alias('controller-a','SHORT',['192.0.2.10','192.0.2.11','192.0.2.12']),
    alias('controller-a','LONG',['198.51.100.10','198.51.100.11','198.51.100.12','198.51.100.13']),
    alias('controller-a','EMPTY',[]),alias('controller-a','PRIVATE',['192.0.2.100']),
    alias('controller-b','LONG',['203.0.113.20']));
  return p;
}

for(const profile of ['simple','detailed']){
  test(profile+' PDF prints short aliases inline and links repeated long aliases to one scoped definition',async()=>{
    const project=aliasReportFixture();
    const short=project.snapshot.aliases.find(alias=>alias.name==='SHORT');
    short.entries[0]={type:'description',value:'단말 주소',raw:'description 단말 주소'};
    short.entries[1].raw='host 192.0.2.10 position 1';
    const report=model(project,{type:'all',showCommonAcl:false});
    const doc=Pdf.documentDefinition(report,{profile});
    const body=aclTables(report,profile).flatMap(table=>table.body.slice(1));
    const rules=allText(body);
    for(const address of ['192.0.2.10','192.0.2.11','192.0.2.12','203.0.113.20'])assert.ok(rules.includes(address),address);
    assert.match(rules,/198\.51\.100\.10 외 3개/);
    assert.doesNotMatch(rules,/198\.51\.100\.13/);
    assert.match(rules,/정의 미수집/);
    assert.match(rules,/구성원 미수집/);
    assert.doesNotMatch(allText(doc.content),/192\.0\.2\.100|alias PRIVATE/);
    const definition=doc.content.find(item=>item.id);
    assert.ok(definition && definition.text.includes('[A01]') && definition.text.includes('LONG'));
    const appendix=allText(doc.content.slice(doc.content.indexOf(definition)));
    assert.doesNotMatch(appendix,/192\.0\.2\.1[012]|203\.0\.113\.20|EMPTY|SHORT/);
    if(profile==='detailed'){
      assert.match(rules,/description 단말 주소/);
      assert.match(rules,/host 192\.0\.2\.10 position 1/);
    }
    const inlineLinks=[];
    JSON.stringify(body,(key,value)=>{if(key==='linkToDestination')inlineLinks.push(value);return value;});
    assert.deepEqual(inlineLinks,[definition.id,definition.id]);
    assert.ok(allText(doc.content).includes('198.51.100.13'));
    const selected=Pdf.documentDefinition(model(project,{type:'selected',roleIds:['role-b'],showCommonAcl:false}),{profile});
    assert.doesNotMatch(allText(selected.content),/198\.51\.100\.1|\[A01\]|Alias 상세/);
    const inclusive=Pdf.documentDefinition(model(project,{type:'all',showCommonAcl:true}),{profile});
    assert.match(allText(inclusive.content),/192\.0\.2\.100/);
    const pdfMake=require('../../src/wlc_role_acl_collector/static/pdfmake.min.js');
    pdfMake.vfs=require('../../src/wlc_role_acl_collector/static/pdfmake_nanum.vfs.js');
    const binary=Buffer.from(await Pdf.createPdfBytes(report,pdfMake,{profile})).toString('latin1');
    assert.equal((binary.match(/\/S \/GoTo\s+\/D \(alias-A01\)/g)||[]).length,2);
    assert.match(binary,/\/Names\s*\[\s*\(alias-A01\)\s*\[\d+ \d+ R \/XYZ/);
  });
}

test('PDF limits account for repeated expansion of large short-alias definitions',()=>{
  const report=model();
  const base={...report.rules[0],destination:'alias LARGE'};
  report.aliases=[{id:'large',name:'LARGE',controllerId:base.controllerId,
    entries:[{type:'name',value:'z'.repeat(600000),raw:''}]}];
  report.rules=Array.from({length:16},(_,i)=>({...base,id:'rule-'+i}));
  for(const profile of ['simple','detailed']){
    assert.throws(()=>Pdf.documentDefinition(report,{profile}),/Alias.*범위/);
  }
});
