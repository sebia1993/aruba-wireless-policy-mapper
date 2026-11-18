const test = require('node:test');
const assert = require('node:assert/strict');
const Core = require('../../src/wlc_role_acl_collector/static/annotation_core.js');
const fs = require('node:fs');
const vm = require('node:vm');

const time = '2026-11-16T12:00:00Z';
function note(text = '검토 메모') {
  return {text, status:'reviewed', updatedAt:time, confirmedAt:time, reasons:[], source:null};
}
function project(id = 'old') {
  return {format:'aruba-policy-annotations', schemaVersion:1, projectId:id, revision:1,
    createdAt:time, updatedAt:time, snapshot:{id:`snapshot-${id}`, collectedAt:time,
      controllers:[{id:'c',name:'Controller',host:'192.0.2.1',port:4343,scope:'effective',identityKnown:true,coverage:'completed',failedCommands:[]}],
      roles:[{id:'role',controllerId:'c',name:'Employee',ssids:['office'],roleTypes:['user'],aclOrder:['acl'],bindingRaw:['access-list session acl'],contextComplete:true,observedUsers:0}],
      rules:[{id:'rule',controllerId:'c',roleId:'role',acl:'acl',sequence:'1',ordinal:1,raw:'any any any permit log',source:'any',destination:'any',service:'any',action:'permit log',sourceInterpretation:'',destinationInterpretation:''}],
      aliases:[],localNetworks:[],issues:[]}, annotations:{roles:{},rules:{}},unresolvedAnnotations:[],changes:[],importHistory:[]};
}
const copy = x => JSON.parse(JSON.stringify(x));
function reuse(edit = () => {}) { const old=project();old.annotations.rules.rule=note();const cur=project('new');edit(cur,old);return Core.reconcileProjects(cur,old,{now:time}); }

test('validation makes an independent, whitespace-preserving safe copy', () => {
  const p=project();p.annotations.rules.rule=note('  "quotes"  \n한글  ');
  const safe=Core.parseProject(JSON.stringify(p));assert.deepEqual(safe,p);safe.snapshot.rules[0].raw='changed';assert.notEqual(safe.snapshot.rules[0].raw,p.snapshot.rules[0].raw);
});
test('rejects unsupported versions, references, types, unsafe keys, unknown fields and oversized notes', () => {
  for(const edit of [p=>p.schemaVersion=2,p=>p.snapshot.rules[0].roleId='missing',p=>p.snapshot.rules[0].ordinal='1',p=>p.annotations.rules.rule=note('x'.repeat(1000001)),p=>p.credentials='secret',p=>p.snapshot.controllers[0].coverage='maybe']) {
    const p=project();edit(p);assert.throws(()=>Core.validateProject(p));
  }
  assert.throws(()=>Core.parseProject(JSON.stringify(project()).replace('"format":','"__proto__":{},"format":')));
  const cyclic=project();cyclic.snapshot.extra=cyclic;assert.throws(()=>Core.validateProject(cyclic));
});
test('matching uses complete raw suffix and retains quotation whitespace', () => {
  assert.equal(reuse().project.annotations.rules.rule.status,'reused');
  for(const raw of ['any any any permit','any any any permit log time-range business','any "two  words" any permit log']) {
    const result=reuse(p=>p.snapshot.rules[0].raw=raw);assert.equal(Object.keys(result.project.annotations.rules).length,0);assert.equal(result.summary.unresolved,1);
  }
});
test('duplicate identical rules never match by ordinal or array position', () => {
  const result=reuse((cur,old)=>{cur.snapshot.rules.push({...cur.snapshot.rules[0],id:'dup',ordinal:2});old.snapshot.rules.push({...old.snapshot.rules[0],id:'old-dup',ordinal:2});});
  assert.deepEqual(result.project.unresolvedAnnotations[0].candidateIds,['rule','dup']);assert.equal(result.summary.reused,0);
});
test('alias membership, role binding, preceding rules, partial coverage and unknown services force review', () => {
  const edits=[
    (cur,old)=>{old.snapshot.aliases=[{id:'a',controllerId:'c',name:'office',entries:[{type:'host',value:'192.0.2.1',raw:'host 192.0.2.1'}]}];cur.snapshot.aliases=[{...old.snapshot.aliases[0],entries:[]}];},
    cur=>cur.snapshot.roles[0].bindingRaw.push('access-list session extra'),
    cur=>{cur.snapshot.rules.unshift({...cur.snapshot.rules[0],id:'first',ordinal:1,raw:'any any any deny'});cur.snapshot.rules[1].ordinal=2;},
    cur=>cur.snapshot.controllers[0].coverage='partial',
    (cur,old)=>{cur.snapshot.rules[0].service=old.snapshot.rules[0].service='custom-unknown';}
  ];
  for(const edit of edits){const result=reuse(edit);assert.equal(result.project.annotations.rules.rule.status,'needs_review');assert.equal(result.summary.needsReview,1);assert.ok(result.project.annotations.rules.rule.reasons.length);}
});
test('same names on another controller do not transfer notes', () => {
  const result=reuse(cur=>cur.snapshot.controllers[0].host='192.0.2.2');assert.equal(result.summary.reused,0);assert.equal(result.summary.unresolved,1);
});
test('unknown legacy controller requires explicit map and always needs review', () => {
  const old=project();old.snapshot.controllers[0].identityKnown=false;old.annotations.rules.rule=note();const cur=project('new');
  assert.equal(Core.reconcileProjects(cur,old,{now:time}).summary.reused,0);
  assert.equal(Core.reconcileProjects(cur,old,{now:time,controllerMap:{c:'c'}}).project.annotations.rules.rule.status,'needs_review');
});
test('current empty notes win; conflicts and inherited unresolved notes retain provenance', () => {
  const old=project();old.annotations.rules.rule=note('older');old.unresolvedAnnotations=[{id:'orphan',kind:'rule',controllerId:'gone',controllerName:'Old',roleName:'Old',acl:'acl',raw:'raw',annotation:note('unmatched'),reason:'missing',candidateIds:[],sourceProjectId:'ancestor',sourceSnapshotId:'ancestor-snapshot'}];
  const cur=project('new');cur.annotations.rules.rule=note('');const result=Core.reconcileProjects(cur,old,{now:time});
  assert.equal(result.project.annotations.rules.rule.text,'');assert.equal(result.project.unresolvedAnnotations.length,2);assert.equal(result.project.unresolvedAnnotations[0].sourceProjectId,'ancestor');assert.equal(result.project.unresolvedAnnotations[1].sourceProjectId,'old');
  assert.deepEqual(cur.annotations.rules.rule,note(''));assert.equal(old.unresolvedAnnotations.length,1);
});
test('missing from partial coverage is uncertainty, never deletion', () => {
  const result=reuse(cur=>{cur.snapshot.controllers[0].coverage='partial';cur.snapshot.rules=[];});
  assert.match(result.project.unresolvedAnnotations[0].reason,/불완전|수집|확인할 수 없/);assert.ok(result.project.changes.every(x=>!/삭제되었/.test(x.message)));
});
test('source confirmation is preserved but copied annotations are never reviewed', () => {
  const result=reuse();const n=result.project.annotations.rules.rule;assert.equal(n.confirmedAt,'');assert.equal(n.source.confirmedAt,time);assert.equal(n.source.projectId,'old');assert.notEqual(n.status,'reviewed');
});
test('all, selected and review scopes use records and include default empty notes', () => {
  const result=reuse();const p=result.project;
  p.snapshot.roles.push({...p.snapshot.roles[0],id:'other',name:'Other'});p.snapshot.rules.push({...p.snapshot.rules[0],id:'other-rule',roleId:'other'});
  const all=Core.buildExportModel(p,{type:'all'},time);assert.equal(all.rules.length,2);assert.equal(all.rules[1].annotation.text,'');assert.equal(all.rules[0].roleName,'Employee');
  const selected=Core.buildExportModel(p,{type:'selected',roleIds:['other']},time);assert.equal(selected.rules.length,1);assert.equal(selected.rules[0].id,'other-rule');
  const review=Core.buildExportModel(p,{type:'review'},time);assert.equal(review.rules.length,1);assert.equal(review.rules[0].id,'rule');assert.equal(review.exportedAt,time);
  assert.throws(()=>Core.buildExportModel(p,{type:'selected',roleIds:['missing']},time));
});
test('selected scope includes unresolved notes only for an unambiguous scoped role', () => {
  const p=project();p.unresolvedAnnotations=[{id:'orphan',kind:'rule',controllerId:'c',controllerName:'Controller',roleName:'Elsewhere',acl:'acl',raw:'raw',annotation:note(),reason:'missing',candidateIds:[],sourceProjectId:'old',sourceSnapshotId:'old-snapshot'}];
  assert.equal(Core.buildExportModel(p,{type:'all'},time).unresolvedAnnotations.length,1);assert.equal(Core.buildExportModel(p,{type:'selected',roleIds:['role']},time).unresolvedAnnotations.length,0);
});
test('previous duplicate remains ambiguous even if one occurrence survives', () => {
  const result=reuse((cur,old)=>old.snapshot.rules.push({...old.snapshot.rules[0],id:'former-duplicate',ordinal:2}));assert.equal(result.summary.reused,0);assert.deepEqual(result.project.unresolvedAnnotations[0].candidateIds,['rule']);
});
test('prior needs_review annotations stay flagged across repeated unchanged imports', () => {
  const result=reuse((cur,old)=>{old.annotations.rules.rule.status='needs_review';old.annotations.rules.rule.reasons=['사용자 서비스 정의 검토 필요'];});assert.equal(result.project.annotations.rules.rule.status,'needs_review');
});
test('unannotated order changes and newly observed roles appear in changes/review export', () => {
  const old=project();old.snapshot.rules.push({...old.snapshot.rules[0],id:'second',ordinal:2,raw:'any any any deny'});
  const cur=copy(old);cur.projectId='new';cur.snapshot.id='new';cur.snapshot.rules[0].ordinal=2;cur.snapshot.rules[1].ordinal=1;cur.snapshot.roles.push({...cur.snapshot.roles[0],id:'new-role',name:'New role'});cur.snapshot.rules.push({...cur.snapshot.rules[0],id:'new-rule',roleId:'new-role'});
  const result=Core.reconcileProjects(cur,old,{now:time});assert.ok(result.project.changes.some(c=>c.type==='role_context_changed'));assert.ok(result.project.changes.some(c=>c.type==='role_added'));const model=Core.buildExportModel(result.project,{type:'review'},time);assert.equal(model.rules.length,3);
});
test('invalid direct object accessors are rejected without execution', () => {
  const p=project();let executed=false;Object.defineProperty(p,'secret',{get(){executed=true;return 'secret';}});assert.throws(()=>Core.validateProject(p));assert.equal(executed,false);
});
test('controller scope and port participate in identity and never use names', () => {
  for(const edit of [cur=>cur.snapshot.controllers[0].scope='local',cur=>cur.snapshot.controllers[0].port=443])assert.equal(reuse(edit).summary.reused,0);
  assert.equal(reuse(cur=>cur.snapshot.controllers[0].name='Renamed').summary.reused,1);
});
test('importing an empty saved annotation keeps it empty', () => {
  const result=reuse((cur,old)=>old.annotations.rules.rule=note(''));assert.equal(result.project.annotations.rules.rule.text,'');assert.equal(result.summary.reused,1);
});
test('simultaneous same-name controllers and role names stay isolated after IDs change', () => {
  const old=project();old.snapshot.controllers.push({...old.snapshot.controllers[0],id:'c2',host:'192.0.2.2'});old.snapshot.roles.push({...old.snapshot.roles[0],id:'role2',controllerId:'c2'});old.snapshot.rules.push({...old.snapshot.rules[0],id:'rule2',roleId:'role2',controllerId:'c2'});old.annotations.rules.rule=note('first controller');old.annotations.rules.rule2=note('second controller');
  const cur=copy(old);cur.projectId='new';cur.annotations.rules={};cur.snapshot.controllers[0].id='new-c';cur.snapshot.roles[0].id='new-role';cur.snapshot.roles[0].controllerId='new-c';cur.snapshot.rules[0].id='new-rule';cur.snapshot.rules[0].roleId='new-role';cur.snapshot.rules[0].controllerId='new-c';
  const result=Core.reconcileProjects(cur,old,{now:time});assert.equal(result.project.annotations.rules['new-rule'].text,'first controller');assert.equal(result.project.annotations.rules.rule2.text,'second controller');
});
test('ambiguous old role names never choose a former role by occurrence', () => {
  const result=reuse((cur,old)=>old.snapshot.roles.push({...old.snapshot.roles[0],id:'duplicate-role'}));assert.equal(result.summary.reused,0);assert.equal(result.summary.unresolved,1);
});
test('raw outer padding is harmless but quoted interior whitespace is exact', () => {
  assert.equal(reuse(cur=>cur.snapshot.rules[0].raw='  any any any permit log  ').summary.reused,1);
  const result=reuse((cur,old)=>{old.snapshot.rules[0].raw='alias "two  words" any any permit';cur.snapshot.rules[0].raw='alias "two words" any any permit';});assert.equal(result.summary.reused,0);
  assert.equal(reuse(cur=>cur.snapshot.rules[0].acl='different-acl').summary.reused,0);
});
test('validation rejects cross-controller references and calendar rollover', () => {
  for(const edit of [p=>p.snapshot.rules[0].controllerId='other',p=>p.createdAt='2026-02-30T00:00:00Z',p=>p.annotations.rules.missing=note(),p=>p.snapshot.roles[0].observedUsers=-1]){const p=project();edit(p);assert.throws(()=>Core.validateProject(p));}
});
test('explicit reassociation of changed known endpoint requires review', () => {
  const old=project();old.annotations.rules.rule=note();const cur=project('new');cur.snapshot.controllers[0].host='192.0.2.2';const result=Core.reconcileProjects(cur,old,{now:time,controllerMap:{c:'c'}});assert.equal(result.project.annotations.rules.rule.status,'needs_review');
});
test('old duplicate controller identities do not silently merge onto one target', () => {
  const result=reuse((cur,old)=>old.snapshot.controllers.push({...old.snapshot.controllers[0],id:'duplicate-controller'}));assert.equal(result.summary.reused,0);assert.equal(result.summary.unresolved,1);
});
test('named service remains unknown even if imported contextComplete claims true', () => {
  const result=reuse((cur,old)=>{cur.snapshot.rules[0].service=old.snapshot.rules[0].service='svc-https';});assert.equal(result.project.annotations.rules.rule.status,'needs_review');assert.match(result.project.annotations.rules.rule.reasons.join(' '),/서비스/);
});
test('review export retains role disappearance changes when no role survives', () => {
  const old=project();const cur=project('new');cur.snapshot.roles=[];cur.snapshot.rules=[];const result=Core.reconcileProjects(cur,old,{now:time});const model=Core.buildExportModel(result.project,{type:'review'},time);assert.equal(model.roles.length,0);assert.equal(model.controllers.length,1);assert.ok(model.changes.some(c=>c.type==='role_not_observed'));
});
test('FQDN trailing dot and case normalize consistently with the Python producer', () => {
  const result=reuse((cur,old)=>{cur.snapshot.controllers[0].host='WLC.example.';old.snapshot.controllers[0].host='wlc.example';});assert.equal(result.summary.reused,1);
});
test('role annotations also require review for uncollected service definitions', () => {
  const old=project();old.annotations.roles.role=note('역할 메모');old.snapshot.rules[0].service='svc-https';const cur=copy(old);cur.projectId='new';cur.annotations.roles={};const result=Core.reconcileProjects(cur,old,{now:time});assert.equal(result.project.annotations.roles.role.status,'needs_review');
});
test('roles without rules remain valid and can retain role notes', () => {
  const old=project();old.snapshot.rules=[];old.annotations.roles.role=note('');const cur=copy(old);cur.projectId='new';cur.annotations.roles={};const result=Core.reconcileProjects(cur,old,{now:time});assert.equal(result.project.annotations.roles.role.text,'');assert.equal(result.summary.reused,1);assert.equal(Core.buildExportModel(result.project,{type:'all'},time).rules.length,0);
});
test('fresh incomplete collection and unresolved service issues are review items', () => {
  const p=project();p.snapshot.roles[0].contextComplete=false;p.snapshot.issues.push({controllerId:'c',roleId:'role',message:'서비스 정의 확인 필요'});const model=Core.buildExportModel(p,{type:'review'},time);assert.equal(model.roles.length,1);assert.equal(model.rules.length,1);assert.equal(model.issues.length,1);
  p.snapshot.roles=[];p.snapshot.rules=[];p.snapshot.issues=[];p.snapshot.controllers[0].coverage='partial';assert.equal(Core.buildExportModel(p,{type:'review'},time).controllers.length,1);
});
test('ambiguous old roles retain possible target rule IDs without auto reuse', () => {
  const result=reuse((cur,old)=>old.snapshot.roles.push({...old.snapshot.roles[0],id:'old-duplicate'}));assert.equal(result.summary.reused,0);assert.deepEqual(result.project.unresolvedAnnotations[0].candidateIds,['rule']);
});
test('browser UMD works offline without CommonJS or DOM globals', () => {
  const context={};vm.runInNewContext(fs.readFileSync(require.resolve('../../src/wlc_role_acl_collector/static/annotation_core.js'),'utf8'),context);assert.equal(typeof context.AnnotationCore.parseProject,'function');const p=context.AnnotationCore.parseProject(JSON.stringify(project()));assert.equal(p.projectId,'old');assert.equal(context.AnnotationCore.buildExportModel(p,undefined,time).rules.length,1);
});
test('serialized JSON overhead may exceed the aggregate text limit without blocking reopen', () => {
  const p=project();
  const row=p.snapshot.rules[0];
  p.snapshot.rules=Array.from({length:50000},(_,i)=>({...row,id:'bulk-'+i,ordinal:i+1}));
  const text=JSON.stringify(p,null,2);
  Core.validateProject(p);
  assert.ok(text.length>20000000);
  assert.equal(Core.parseProject(text).snapshot.rules.length,50000);
});
test('mapped unmatched notes retain current controller context in selected exports', () => {
  const old=project();old.annotations.rules.rule=note('이전 허용 근거');
  const current=project('new');current.snapshot.controllers[0].id='new-c';
  current.snapshot.roles[0].controllerId='new-c';current.snapshot.rules[0].controllerId='new-c';
  current.snapshot.rules[0].raw='any any any deny';
  const reused=Core.reconcileProjects(current,old,{now:time}).project;
  assert.equal(reused.unresolvedAnnotations[0].controllerId,'new-c');
  assert.equal(Core.buildExportModel(reused,{type:'selected',roleIds:['role']},time).unresolvedAnnotations.length,1);
});
test('unassociated legacy controller ID collisions never assign unresolved notes to selected roles', () => {
  const old=project();old.annotations.rules.rule=note('연결하지 않은 이전 설명');
  const current=project('new');
  for(const p of [old,current]){p.snapshot.controllers[0].identityKnown=false;p.snapshot.controllers[0].host='';p.snapshot.controllers[0].port=0;}
  const result=Core.reconcileProjects(current,old,{now:time,controllerMap:{}}).project;
  assert.equal(result.unresolvedAnnotations[0].controllerId,'');
  assert.equal(Core.buildExportModel(result,{type:'selected',roleIds:['role']},time).unresolvedAnnotations.length,0);
  assert.equal(Core.buildExportModel(result,{type:'all'},time).unresolvedAnnotations.length,1);
  old.annotations.rules={};old.unresolvedAnnotations=copy(result.unresolvedAnnotations);old.unresolvedAnnotations[0].controllerId='c';
  const inherited=Core.reconcileProjects(current,old,{now:time}).project;
  assert.equal(inherited.unresolvedAnnotations[0].controllerId,'');
});
test('validation failure never mutates current work or previous annotations', () => {
  const current=project('new');current.annotations.rules.rule=note('현재 작업');const before=copy(current);const previous=project();previous.snapshot.rules[0].roleId='nonexistent';assert.throws(()=>Core.reconcileProjects(current,previous,{now:time}));assert.deepEqual(current,before);
});
test('original note confirmation provenance survives another reuse generation', () => {
  const first=reuse().project;const current=project('third');const result=Core.reconcileProjects(current,first,{now:time});assert.equal(result.project.annotations.rules.rule.source.projectId,'old');assert.equal(result.project.annotations.rules.rule.source.snapshotId,'snapshot-old');assert.equal(result.project.annotations.rules.rule.source.confirmedAt,time);assert.equal(result.project.annotations.rules.rule.confirmedAt,'');assert.equal(result.project.annotations.rules.rule.status,'reused');
});

test('device category supports Windows PC and MacBook while retaining legacy PC without changing schema', () => {
  for(const value of ['', 'PC', 'windows_pc', 'macbook', 'mobile', 'ETC']) {
    const p=project();
    p.annotations.roles.role={...note('단말'),deviceType:value,manualSsid:'corp'};
    assert.equal(Core.parseProject(JSON.stringify(p)).annotations.roles.role.deviceType,value);
    const report=Core.buildExportModel(p,{type:'all'},time);
    assert.equal(report.roles[0].annotation.deviceType,value);
    assert.equal(p.schemaVersion,1);
  }
  for(const invalid of ['Windows PC','MacBook','win11','macOS','PC-mac']) {
    const p=project();p.annotations.roles.role={...note(),deviceType:invalid};
    assert.throws(()=>Core.validateProject(p),/deviceType/);
  }
});

test('reusing role annotations preserves a previous MacBook value as a pending review', () => {
  const older=project('old');
  older.annotations.roles.role={...note('업무 장비'),deviceType:'macbook',manualSsid:'corp'};
  const current=project('next');
  const result=Core.reconcileProjects(current,older,{now:time});
  assert.equal(result.project.annotations.roles.role.deviceType,'macbook');
  assert.equal(result.project.annotations.roles.role.status,'reused');
  assert.equal(result.project.annotations.roles.role.manualSsid,'corp');
});
