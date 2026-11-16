'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,ResourceLoader}=require('jsdom');
const Core=require('../../src/wlc_role_acl_collector/static/annotation_core.js');
const target=path.resolve(__dirname,'../../src/wlc_role_acl_collector/static/annotation_import.js');
const Import=fs.existsSync(target)?require(target):{};
function document(){return new JSDOM('<!doctype html><p>Current editor stays here</p>').window.document;}
function panel(name='guest',controller='') {return `<section class="role-panel" data-role="${name}" ${controller?`data-controller="${controller}"`:''}><h3>${name}</h3><textarea class="role-description-input" data-role="${name}">textarea role fallback</textarea><table><thead><tr><th>ACL</th><th>#</th><th>Action</th><th>Source</th><th>Destination</th><th>Service</th><th>Raw</th><th>Comment</th></tr></thead><tbody><tr class="acl-rule-row other-acl-rule" hidden><td>other-acl</td><td>9</td><td><span>permit</span></td><td><span class="alias-prefix">alias</span><button class="alias-link">office &quot;A&quot;</button><div class="notice">interpreted endpoint</div></td><td>any</td><td>svc-https</td><td class="raw">alias &quot;office A&quot; any svc-https permit log</td><td><textarea class="comment-input" data-comment-id="comment-${name}">textarea rule fallback</textarea></td></tr><tr class="alias-detail-row" hidden><td colspan="8"><div class="alias-detail-title">Source alias: office &quot;A&quot;</div><div><span class="alias-chip"><span class="alias-type">NETWORK</span><span>192.0.2.0 255.255.255.0</span></span></div></td></tr></tbody></table></section>`;}
function legacy(body=panel()){return '<!doctype html><html><body><header><p>생성시각: 2026-11-16T12:34:56+09:00 / Unresolved: 0</p></header><span class="metric-label">controller label</span>'+body+'<textarea id="acl-comments-data">{"comment-guest":"","missing-rule":"keep unmatched"}</textarea><textarea id="role-descriptions-data">{"guest":"설명 \\"quoted\\"","missing-role":"orphan role"}</textarea><script id="access-check-data" type="application/json">{"roles":[]}</script></body></html>';}
function minimalProject(){return {format:'aruba-policy-annotations',schemaVersion:1,projectId:'project',revision:1,createdAt:'2026-11-16T00:00:00Z',updatedAt:'2026-11-16T00:00:00Z',snapshot:{id:'snapshot',collectedAt:'2026-11-16T00:00:00Z',controllers:[],roles:[],rules:[],aliases:[],localNetworks:[],issues:[]},annotations:{roles:{},rules:{}},unresolvedAnnotations:[],changes:[],importHistory:[]};}
// Historical report.py _acl_rows_html rendered defaults for an empty policy:
// action became an UNKNOWN badge and an empty service became an ANY badge.
function emptyRolePanel(comment='') {return `<section class="acl-section role-panel" id="role-panel-1" data-role="empty-role"><div class="acl-section-header"><h3>empty-role</h3><span>1 rules / 0 observed users</span></div><div class="role-report-description"><textarea class="role-description-input" data-role="empty-role">규칙 수집 여부 확인</textarea></div><div class="acl-table-scroll"><table><thead><tr><th>ACL</th><th>#</th><th>Action</th><th>Source</th><th>Destination</th><th>Service</th><th class="raw-column">Raw</th><th>Comment</th></tr></thead><tbody><tr class="acl-rule-row other-acl-rule" data-other-acl="true" hidden data-rule-id="access-rule-empty-role-1"><td>empty-acl, fallback-acl</td><td></td><td><span class="rule-badge action-unknown">unknown</span></td><td></td><td></td><td><span class="rule-badge service-badge">any</span></td><td class="raw raw-column"></td><td class="comment-cell"><textarea class="comment-input" data-comment-id="acl-comment-empty-role-1">${comment}</textarea><div class="comment-status">입력 시 자동 저장</div><div class="comment-print"></div></td></tr></tbody></table></div></section>`;}
test('historical no-rule placeholder imports the Role and binding names without creating a fake rule',()=>{
  const p=Import.parse(emptyRolePanel(),document(),Core);
  assert.equal(p.snapshot.roles.length,1);assert.equal(p.snapshot.rules.length,0);
  assert.deepEqual(p.snapshot.roles[0].aclOrder,['empty-acl','fallback-acl']);
  assert.equal(p.annotations.roles[p.snapshot.roles[0].id].text,'규칙 수집 여부 확인');
  assert.equal(p.snapshot.roles[0].contextComplete,false);assert.equal(p.unresolvedAnnotations.length,0);
  const blank=emptyRolePanel().replace('<span class="rule-badge action-unknown">unknown</span>','').replace('<span class="rule-badge service-badge">any</span>','');
  assert.equal(Import.parse(blank,document(),Core).snapshot.rules.length,0);
});
test('placeholder comments stay unresolved with context and embedded empty text suppresses fallback',()=>{
  const p=Import.parse(emptyRolePanel('안내 행에 남긴 메모'),document(),Core);
  assert.equal(p.snapshot.rules.length,0);assert.equal(p.unresolvedAnnotations.length,1);
  const u=p.unresolvedAnnotations[0];
  assert.equal(u.annotation.text,'안내 행에 남긴 메모');assert.equal(u.roleName,'empty-role');assert.equal(u.acl,'empty-acl, fallback-acl');
  assert.equal(u.controllerId,p.snapshot.controllers[0].id);assert.deepEqual(u.candidateIds,[]);
  const cleared=Import.parse(emptyRolePanel('stale textarea')+'<textarea id="acl-comments-data">{"acl-comment-empty-role-1":""}</textarea>',document(),Core);
  assert.equal(cleared.unresolvedAnnotations.length,1);assert.equal(cleared.unresolvedAnnotations[0].annotation.text,'');
  assert.equal(cleared.unresolvedAnnotations[0].annotation.status,'needs_review');
});
test('a missing raw rule with actual policy fields still rejects the whole legacy import',()=>{
  for(const html of [panel().replace('alias &quot;office A&quot; any svc-https permit log',''),emptyRolePanel().replace('<td></td><td></td>','<td>any</td><td></td>'),emptyRolePanel().replace('>unknown</span>','>permit</span>'),emptyRolePanel().replace('>any</span>','>svc-https</span>')]) assert.throws(()=>Import.parse(html,document(),Core),/원문 규칙/);
});
test('legacy imports hidden full raw rows and aliases, retaining empty and unmatched embedded notes',()=>{
  assert.equal(typeof Import.parse,'function');
  const doc=document(), before=doc.documentElement.outerHTML;
  const p=Import.parse(legacy(),doc,Core);
  assert.equal(doc.documentElement.outerHTML,before);
  assert.equal(p.snapshot.rules.length,1);
  const rule=p.snapshot.rules[0], role=p.snapshot.roles[0];
  assert.equal(rule.raw,'alias "office A" any svc-https permit log');
  assert.equal(rule.source,'alias office "A"');assert.equal(rule.sourceInterpretation,'interpreted endpoint');
  assert.equal(rule.acl,'other-acl');assert.equal(rule.sequence,'9');
  assert.equal(p.annotations.rules[rule.id].text,'');
  assert.equal(p.annotations.roles[role.id].text,'설명 "quoted"');
  assert.equal(p.annotations.rules[rule.id].status,'needs_review');assert.equal(role.contextComplete,false);
  assert.deepEqual(role.aclOrder,['other-acl']);
  assert.equal(p.snapshot.collectedAt,'2026-11-16T12:34:56+09:00');
  assert.equal(p.snapshot.controllers[0].identityKnown,false);assert.equal(p.snapshot.controllers[0].host,'');
  assert.equal(p.snapshot.controllers[0].coverage,'unknown');
  assert.equal(p.snapshot.aliases[0].name,'office "A"');
  assert.deepEqual(p.snapshot.aliases[0].entries,[{type:'network',value:'192.0.2.0 255.255.255.0',raw:'network 192.0.2.0 255.255.255.0'}]);
  assert.deepEqual(p.unresolvedAnnotations.map(x=>x.annotation.text).sort(),['keep unmatched','orphan role']);
});
test('legacy textarea fallback and unknown source timestamps remain reviewable',()=>{
  assert.equal(typeof Import.parse,'function');
  const p=Import.parse(panel(),document(),Core);
  assert.equal(p.snapshot.controllers[0].name,'장비 미확인');
  assert.equal(p.annotations.rules[p.snapshot.rules[0].id].text,'textarea rule fallback');
  assert.equal(p.annotations.roles[p.snapshot.roles[0].id].text,'textarea role fallback');
  assert.ok(p.snapshot.issues.some(x=>/시각|time/i.test(x.message)));
  assert.ok(p.snapshot.collectedAt.endsWith('Z'));
});
test('legacy textarea notes without saved keys or matching policy rows are retained',()=>{
  assert.equal(typeof Import.parse,'function');
  const html=panel().replace('data-comment-id="comment-guest"','')+'<textarea class="comment-input" data-comment-id="orphan-input">standalone rule note</textarea><textarea class="role-description-input" data-role="missing-role">standalone role description</textarea>';
  const p=Import.parse(html,document(),Core);
  assert.equal(p.annotations.rules[p.snapshot.rules[0].id].text,'textarea rule fallback');
  assert.deepEqual(p.unresolvedAnnotations.map(x=>x.annotation.text).sort(),['standalone role description','standalone rule note']);
});
test('legacy imports every policy row even when an older hidden row lacks the common class',()=>{
  assert.equal(typeof Import.parse,'function');
  const extra='<tr class="other-acl-rule" hidden><td>second-acl</td><td>10</td><td>deny</td><td>any</td><td>any</td><td>any</td><td>any any any deny log</td><td></td></tr>';
  const p=Import.parse(panel().replace('</tbody>',extra+'</tbody>'),document(),Core);
  assert.equal(p.snapshot.rules.length,2);assert.equal(p.snapshot.rules[1].raw,'any any any deny log');
  assert.deepEqual(p.snapshot.roles[0].aclOrder,['other-acl','second-acl']);
});
test('controller source groups remain distinct and ambiguous global legacy notes become unresolved',()=>{
  assert.equal(typeof Import.parse,'function');
  const p=Import.parse(legacy(panel('guest','A')+panel('guest','B')),document(),Core);
  assert.equal(p.snapshot.controllers.length,2);
  assert.notEqual(p.snapshot.roles[0].controllerId,p.snapshot.roles[1].controllerId);
  assert.ok(p.snapshot.controllers.every(c=>!c.identityKnown&&c.host===''&&c.port===0));
  assert.equal(Object.keys(p.annotations.roles).length,0);assert.equal(Object.keys(p.annotations.rules).length,0);
  assert.ok(p.unresolvedAnnotations.some(x=>x.annotation.text==='설명 "quoted"'&&x.candidateIds.length===2));
  assert.ok(p.unresolvedAnnotations.some(x=>x.annotation.text===''&&x.candidateIds.length===2));
});
test('modern JSON and embedded modern HTML use the core validator',()=>{
  assert.equal(typeof Import.parse,'function');
  const p=minimalProject();
  assert.deepEqual(Import.parse(JSON.stringify(p),document(),Core),p);
  assert.deepEqual(Import.parse('<script id="annotation-project-data" type="application/json">'+JSON.stringify(p)+'</script>',document(),Core),p);
  p.schemaVersion=99;
  assert.throws(()=>Import.parse(JSON.stringify(p),document(),Core),/schema/i);
  assert.throws(()=>Import.parse('<script id="annotation-project-data" type="application/json">bad json</script>'+panel(),document(),Core),/JSON/i);
});
test('import parsing never executes scripts, event handlers or loads resource URLs',()=>{
  assert.equal(typeof Import.parse,'function');
  let requests=0;
  class Loader extends ResourceLoader {fetch(){requests++;return null;}}
  const dom=new JSDOM('<!doctype html><p>active editor</p>',{runScripts:'dangerously',resources:new Loader(),url:'https://example.invalid/'});
  dom.window.hacked=0;
  const malicious='<script>window.hacked++</script><img src="https://attack.invalid/image" onerror="window.hacked++"><iframe src="https://attack.invalid/frame"></iframe><link rel="stylesheet" href="https://attack.invalid/css">';
  const p=Import.parse(legacy(malicious+panel()),dom.window.document,Core);
  assert.equal(p.snapshot.rules.length,1);assert.equal(dom.window.hacked,0);assert.equal(requests,0);
  assert.equal(dom.window.document.querySelectorAll('img,iframe,script').length,0);
});
test('rejects unrecognized or malformed legacy documents and oversized imports',()=>{
  assert.equal(typeof Import.parse,'function');
  for(const value of ['<h1>unrelated</h1>','<section class="role-panel" data-role="guest"><table><tr class="acl-rule-row"><td>broken</td></tr></table></section>',legacy().replace('{"comment-guest":"","missing-rule":"keep unmatched"}','not json')]) assert.throws(()=>Import.parse(value,document(),Core));
  assert.throws(()=>Import.parse('x'.repeat(50*1024*1024+1),document(),Core),/size|크기|50/);
  assert.throws(()=>Import.parse(legacy().replace('{"comment-guest":"","missing-rule":"keep unmatched"}','{"__proto__":"unsafe"}'),document(),Core),/unsafe|안전/);
});
