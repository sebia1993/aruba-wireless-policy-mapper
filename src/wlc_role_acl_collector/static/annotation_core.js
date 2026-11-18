/* Offline project validation, conservative annotation reuse, and report scopes. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.AnnotationCore = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const FORMAT = 'aruba-policy-annotations';
  const MAX_TEXT = 1000000;
  const MAX_ITEMS = 100000;
  const MAX_DOCUMENT = 20000000;
  const MAX_SERIALIZED_BYTES = 50 * 1024 * 1024;
  const UNSAFE = new Set(['__proto__', 'prototype', 'constructor']);
  const STATUSES = ['unreviewed', 'reviewed', 'reused', 'needs_review'];
  // No controller service-object definitions are collected in this schema.
  const KNOWN_SERVICES = new Set(['any', 'ip']);
  // Visual classification only: keep collected names, notes and ACL order unchanged.
  const COMMON_ACL_NAMES = new Set(['global-sacl', 'ra-guard', 're-guard', 'logon-control']);
  function normalizedAclName(value) {
    let name=String(value==null?'':value)
      .normalize('NFKC')
      .replace(/[\u200B-\u200D\uFEFF]/g,'')
      .replace(/[\u2010-\u2015\u2212\uFE63\uFF0D]/g,'-')
      .trim().toLowerCase();
    for(let i=0;i<3&&name.length>=2;i++){
      const first=name[0],last=name[name.length-1];
      if((first==='"'&&last==='"')||(first==="'"&&last==="'")||
         (first==='“'&&last==='”')||(first==='‘'&&last==='’')){
        name=name.slice(1,-1).trim();
      } else break;
    }
    return name;
  }
  function isCommonAclName(acl){return COMMON_ACL_NAMES.has(normalizedAclName(acl));}
  function fail(path, message) { throw new Error('Invalid annotation project at ' + path + ': ' + message); }
  function safeCopy(value) {
    const active = new Set();
    let size = 0, nodes = 0;
    function walk(v, path, depth) {
      if (++nodes > 1500000 || depth > 32) fail(path, 'structure limit exceeded');
      if (typeof v === 'string') { size += v.length; if (v.length > MAX_TEXT || size > MAX_DOCUMENT) fail(path, 'text size limit exceeded'); return v; }
      if (v === null || typeof v === 'boolean') return v;
      if (typeof v === 'number' && Number.isFinite(v)) return v;
      if (typeof v !== 'object') fail(path, 'must contain JSON values only');
      if (active.has(v)) fail(path, 'cyclic value');
      if (Object.getOwnPropertySymbols(v).length) fail(path, 'symbol keys are unsupported');
      const prototype = Object.getPrototypeOf(v);
      if (!Array.isArray(v) && prototype !== Object.prototype && prototype !== null) fail(path, 'must be a plain object');
      active.add(v);
      let result;
      if (Array.isArray(v)) {
        if (v.length > MAX_ITEMS) fail(path, 'array size limit exceeded');
        const names = Object.getOwnPropertyNames(v);
        if (names.length !== v.length + 1) fail(path, 'sparse arrays or extra array properties are unsupported');
        result = [];
        for (let i = 0; i < v.length; i++) {
          const d = Object.getOwnPropertyDescriptor(v, String(i));
          if (!d || !Object.hasOwn(d, 'value')) fail(path, 'accessors are unsupported');
          result.push(walk(d.value, path + '[' + i + ']', depth + 1));
        }
      } else {
        result = {};
        for (const key of Object.getOwnPropertyNames(v)) {
          if (UNSAFE.has(key)) fail(path, 'unsafe object key');
          size += key.length;
          if (key.length > 4096 || size > MAX_DOCUMENT) fail(path, 'key size limit exceeded');
          const d = Object.getOwnPropertyDescriptor(v, key);
          if (!Object.hasOwn(d, 'value')) fail(path, 'accessors are unsupported');
          Object.defineProperty(result, key, {value:walk(d.value, path + '.' + key, depth + 1), enumerable:true, writable:true, configurable:true});
        }
      }
      active.delete(v);
      return result;
    }
    return walk(value, '$', 0);
  }
  function obj(v, path, keys, optional = []) {
    if (v === null || typeof v !== 'object' || Array.isArray(v)) fail(path, 'expected object');
    if (keys) {
      const allowed=keys.concat(optional);
      for (const key of Object.keys(v)) if (!allowed.includes(key)) fail(path + '.' + key, 'unknown field');
      for (const key of keys) if (!Object.hasOwn(v, key)) fail(path + '.' + key, 'required field missing');
    }
  }
  function str(v, path, empty = true, max = MAX_TEXT) { if (typeof v !== 'string' || (!empty && !v.length) || v.length > max) fail(path, 'expected ' + (empty ? '' : 'nonempty ') + 'string'); }
  function id(v, path, empty = false) { str(v, path, empty, 4096); if (UNSAFE.has(v)) fail(path, 'unsafe identifier'); }
  function arr(v, path) { if (!Array.isArray(v) || v.length > MAX_ITEMS) fail(path, 'expected bounded array'); }
  function strings(v, path) { arr(v, path); v.forEach((x, i) => str(x, path + '[' + i + ']')); }
  function boolean(v, path) { if (typeof v !== 'boolean') fail(path, 'expected boolean'); }
  function integer(v, path, min, max = Number.MAX_SAFE_INTEGER) { if (!Number.isSafeInteger(v) || v < min || v > max) fail(path, 'expected integer in range'); }
  function timestamp(v, path, empty = false) {
    str(v, path, empty, 64);
    if (empty && v === '') return;
    if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)$/.test(v) || !Number.isFinite(Date.parse(v))) fail(path, 'expected timezone-aware ISO timestamp');
    const month=Number(v.slice(5,7)), day=Number(v.slice(8,10)), year=Number(v.slice(0,4));
    if (month<1 || month>12 || day<1 || day>new Date(Date.UTC(year,month,0)).getUTCDate() || Number(v.slice(11,13))>23 || Number(v.slice(14,16))>59 || Number(v.slice(17,19))>59) fail(path, 'invalid calendar date');
  }
  function choice(v, values, path) { if (!values.includes(v)) fail(path, 'unsupported value'); }
  function record(v, path, isRole = false) {
    // Manual SSID and device category belong to a Role's annotation, never to
    // the collected SSID mapping or to an individual ACL rule.
    const keys=['text','status','updatedAt','confirmedAt','reasons','source'];
    obj(v,path,keys,isRole?['manualSsid','deviceType']:[]);
    str(v.text,path+'.text');choice(v.status,STATUSES,path+'.status');timestamp(v.updatedAt,path+'.updatedAt');timestamp(v.confirmedAt,path+'.confirmedAt',true);strings(v.reasons,path+'.reasons');
    if(v.source!==null){obj(v.source,path+'.source',['projectId','snapshotId','recordId','confirmedAt']);id(v.source.projectId,path+'.source.projectId');id(v.source.snapshotId,path+'.source.snapshotId');id(v.source.recordId,path+'.source.recordId');timestamp(v.source.confirmedAt,path+'.source.confirmedAt',true);}
    if(isRole) {
      if(Object.hasOwn(v,'manualSsid'))str(v.manualSsid,path+'.manualSsid',true,512);
      if(Object.hasOwn(v,'deviceType'))choice(v.deviceType,['','PC','windows_pc','macbook','mobile','ETC'],path+'.deviceType');
    }
  }
  function indexed(rows, path) {
    arr(rows,path);const map=new Map();
    rows.forEach((v,i)=>{obj(v,path+'['+i+']');id(v.id,path+'['+i+'].id');if(map.has(v.id))fail(path,'duplicate identifier');map.set(v.id,v);});return map;
  }
  function ref(map, value, path, empty = false) { id(value,path,empty); if(value!=='' && !map.has(value))fail(path,'unknown reference'); }
  function validateProject(value) {
    const p=safeCopy(value);
    obj(p,'$',['format','schemaVersion','projectId','revision','createdAt','updatedAt','snapshot','annotations','unresolvedAnnotations','changes','importHistory']);
    if(p.format!==FORMAT)fail('$.format','unsupported format');if(p.schemaVersion!==1)fail('$.schemaVersion','unsupported schema version');
    id(p.projectId,'$.projectId');integer(p.revision,'$.revision',0);timestamp(p.createdAt,'$.createdAt');timestamp(p.updatedAt,'$.updatedAt');
    const s=p.snapshot;obj(s,'$.snapshot',['id','collectedAt','controllers','roles','rules','aliases','localNetworks','issues']);id(s.id,'$.snapshot.id');timestamp(s.collectedAt,'$.snapshot.collectedAt');
    const controllers=indexed(s.controllers,'$.snapshot.controllers'),roles=indexed(s.roles,'$.snapshot.roles'),rules=indexed(s.rules,'$.snapshot.rules');indexed(s.aliases,'$.snapshot.aliases');
    s.controllers.forEach((c,i)=>{const path='$.snapshot.controllers['+i+']';obj(c,path,['id','name','host','port','scope','identityKnown','coverage','failedCommands']);str(c.name,path+'.name');str(c.host,path+'.host',true,4096);integer(c.port,path+'.port',0,65535);str(c.scope,path+'.scope',false,4096);boolean(c.identityKnown,path+'.identityKnown');if(c.identityKnown && (!c.host.trim() || c.port===0))fail(path,'known identity requires host and port');choice(c.coverage,['completed','partial','failed','unknown'],path+'.coverage');strings(c.failedCommands,path+'.failedCommands');});
    s.roles.forEach((r,i)=>{const path='$.snapshot.roles['+i+']';obj(r,path,['id','controllerId','name','ssids','roleTypes','aclOrder','bindingRaw','contextComplete','observedUsers']);ref(controllers,r.controllerId,path+'.controllerId');str(r.name,path+'.name',false,4096);['ssids','roleTypes','aclOrder','bindingRaw'].forEach(k=>strings(r[k],path+'.'+k));boolean(r.contextComplete,path+'.contextComplete');integer(r.observedUsers,path+'.observedUsers',0);});
    s.rules.forEach((r,i)=>{const path='$.snapshot.rules['+i+']';obj(r,path,['id','controllerId','roleId','acl','sequence','ordinal','raw','source','destination','service','action','sourceInterpretation','destinationInterpretation']);ref(controllers,r.controllerId,path+'.controllerId');ref(roles,r.roleId,path+'.roleId');if(roles.get(r.roleId).controllerId!==r.controllerId)fail(path,'role/controller mismatch');integer(r.ordinal,path+'.ordinal',1);['acl','sequence','raw','source','destination','service','action','sourceInterpretation','destinationInterpretation'].forEach(k=>str(r[k],path+'.'+k));});
    s.aliases.forEach((a,i)=>{const path='$.snapshot.aliases['+i+']';obj(a,path,['id','controllerId','name','entries']);ref(controllers,a.controllerId,path+'.controllerId');str(a.name,path+'.name',false,4096);arr(a.entries,path+'.entries');a.entries.forEach((e,j)=>{obj(e,path+'.entries['+j+']',['type','value','raw']);['type','value','raw'].forEach(k=>str(e[k],path+'.entries['+j+'].'+k));});});
    arr(s.localNetworks,'$.snapshot.localNetworks');s.localNetworks.forEach((n,i)=>{const path='$.snapshot.localNetworks['+i+']';obj(n,path,['controllerId','roleId','network','subnetMask','status','notes']);ref(controllers,n.controllerId,path+'.controllerId');ref(roles,n.roleId,path+'.roleId');if(roles.get(n.roleId).controllerId!==n.controllerId)fail(path,'role/controller mismatch');['network','subnetMask','status','notes'].forEach(k=>str(n[k],path+'.'+k));});
    arr(s.issues,'$.snapshot.issues');s.issues.forEach((v,i)=>{const path='$.snapshot.issues['+i+']';obj(v,path,['controllerId','roleId','message']);ref(controllers,v.controllerId,path+'.controllerId');ref(roles,v.roleId,path+'.roleId',true);if(v.roleId && roles.get(v.roleId).controllerId!==v.controllerId)fail(path,'role/controller mismatch');str(v.message,path+'.message');});
    obj(p.annotations,'$.annotations',['roles','rules']);for(const kind of ['roles','rules']){const map=kind==='roles'?roles:rules;obj(p.annotations[kind],'$.annotations.'+kind);for(const [key,v]of Object.entries(p.annotations[kind])){ref(map,key,'$.annotations.'+kind+'.'+key);record(v,'$.annotations.'+kind+'.'+key,kind==='roles');}}
    const unresolvedIds=new Set();arr(p.unresolvedAnnotations,'$.unresolvedAnnotations');p.unresolvedAnnotations.forEach((u,i)=>{const path='$.unresolvedAnnotations['+i+']';obj(u,path,['id','kind','controllerId','controllerName','roleName','acl','raw','annotation','reason','candidateIds','sourceProjectId','sourceSnapshotId']);id(u.id,path+'.id');if(unresolvedIds.has(u.id))fail(path,'duplicate unresolved identifier');unresolvedIds.add(u.id);choice(u.kind,['role','rule'],path+'.kind');id(u.controllerId,path+'.controllerId',true);['controllerName','roleName','acl','raw','reason'].forEach(k=>str(u[k],path+'.'+k));record(u.annotation,path+'.annotation',u.kind==='role');strings(u.candidateIds,path+'.candidateIds');u.candidateIds.forEach(x=>id(x,path+'.candidateIds'));id(u.sourceProjectId,path+'.sourceProjectId');id(u.sourceSnapshotId,path+'.sourceSnapshotId');});
    arr(p.changes,'$.changes');p.changes.forEach((c,i)=>{const path='$.changes['+i+']';obj(c,path,['type','controllerId','roleId','ruleId','message','previousRaw']);str(c.type,path+'.type',false,4096);ref(controllers,c.controllerId,path+'.controllerId',true);ref(roles,c.roleId,path+'.roleId',true);ref(rules,c.ruleId,path+'.ruleId',true);if(c.roleId && c.controllerId && roles.get(c.roleId).controllerId!==c.controllerId)fail(path,'role/controller mismatch');if(c.ruleId && ((c.roleId && rules.get(c.ruleId).roleId!==c.roleId)||(c.controllerId&&rules.get(c.ruleId).controllerId!==c.controllerId)))fail(path,'rule context mismatch');str(c.message,path+'.message');str(c.previousRaw,path+'.previousRaw');});
    arr(p.importHistory,'$.importHistory');p.importHistory.forEach((h,i)=>{const path='$.importHistory['+i+']';obj(h,path,['projectId','snapshotId','importedAt','reused','needsReview','unresolved']);id(h.projectId,path+'.projectId');id(h.snapshotId,path+'.snapshotId');timestamp(h.importedAt,path+'.importedAt');['reused','needsReview','unresolved'].forEach(k=>integer(h[k],path+'.'+k,0));});
    return p;
  }
  function parseProject(text) {
    // Serialized JSON has punctuation, indentation and escapes in addition to
    // the bounded field contents. Its file limit is distinct from MAX_DOCUMENT.
    if(typeof text!=='string' || text.length>MAX_SERIALIZED_BYTES)fail('$','project text size/type limit exceeded');
    let bytes=0;
    for(let i=0;i<text.length;i++){
      const c=text.charCodeAt(i);
      if(c<0x80)bytes++;
      else if(c<0x800)bytes+=2;
      else if(c>=0xd800&&c<=0xdbff&&i+1<text.length&&text.charCodeAt(i+1)>=0xdc00&&text.charCodeAt(i+1)<=0xdfff){bytes+=4;i++;}
      else bytes+=3;
      if(bytes>MAX_SERIALIZED_BYTES)fail('$','project UTF-8 file size limit exceeded');
    }
    let value;try{value=JSON.parse(text);}catch(error){throw new Error('Invalid annotation project JSON: '+error.message);}return validateProject(value);
  }
  function nowValue(now) { const value=now===undefined?new Date().toISOString():now;timestamp(value,'options.now');return value; }
  function same(a,b) { return JSON.stringify(a)===JSON.stringify(b); }
  function endpoint(c) { return JSON.stringify([c.host.trim().toLowerCase().replace(/\.+$/, ''),c.port,c.scope]); }
  function raw(r) { return r.raw.trim(); }
  const projectIndexes=new WeakMap();
  function group(map,key,value){if(!map.has(key))map.set(key,[]);map.get(key).push(value);}
  function snapshotIndex(p){
    if(projectIndexes.has(p))return projectIndexes.get(p);
    const index={rulesByRole:new Map(),rulesByRaw:new Map(),rolesByName:new Map(),aliases:new Map(),ambiguousOrder:new Set(),unknownServices:new Set()};
    for(const role of p.snapshot.roles)group(index.rolesByName,JSON.stringify([role.controllerId,role.name]),role);
    for(const rule of p.snapshot.rules){group(index.rulesByRole,rule.roleId,rule);group(index.rulesByRaw,JSON.stringify([rule.roleId,rule.acl,raw(rule)]),rule);if(!KNOWN_SERVICES.has(rule.service.toLowerCase()))index.unknownServices.add(rule.roleId);}
    for(const [roleId,rules]of index.rulesByRole){rules.sort((a,b)=>a.ordinal-b.ordinal);if(new Set(rules.map(r=>r.ordinal)).size!==rules.length)index.ambiguousOrder.add(roleId);}
    for(const alias of p.snapshot.aliases)group(index.aliases,alias.controllerId,[alias.name,alias.entries]);
    for(const aliases of index.aliases.values())aliases.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
    projectIndexes.set(p,index);return index;
  }
  function roleRules(p,id) { return snapshotIndex(p).rulesByRole.get(id)||[]; }
  function aliasContext(p,controllerId) { return snapshotIndex(p).aliases.get(controllerId)||[]; }
  function roleContextReasons(current,previous,role,oldRole,controller,oldController) {
    const reasons=[];
    if(!controller.identityKnown || !oldController.identityKnown)reasons.push('컨트롤러 식별 정보가 불명확합니다. 직접 연결한 대상이 맞는지 확인해야 합니다.');
    if(endpoint(controller)!==endpoint(oldController))reasons.push('컨트롤러 주소, 포트 또는 설정 범위가 변경되었습니다. 직접 연결한 대상이 맞는지 확인해야 합니다.');
    if(controller.coverage!=='completed' || oldController.coverage!=='completed' || controller.failedCommands.length || oldController.failedCommands.length)reasons.push('수집이 완료되지 않았거나 수집 범위를 확인할 수 없습니다.');
    if(!role.contextComplete || !oldRole.contextComplete)reasons.push('역할 또는 서비스의 수집 정보가 불완전하거나 확인되지 않았습니다.');
    if(snapshotIndex(current).unknownServices.has(role.id)||snapshotIndex(previous).unknownServices.has(oldRole.id))reasons.push('서비스 정의를 확인할 수 없어 검토가 필요합니다.');
    if(!same(role.aclOrder,oldRole.aclOrder)||!same(role.bindingRaw,oldRole.bindingRaw))reasons.push('역할의 ACL 연결 또는 적용 순서가 변경되었습니다.');
    if(!same(role.ssids,oldRole.ssids)||!same(role.roleTypes,oldRole.roleTypes))reasons.push('역할의 SSID 또는 역할 유형 연결 정보가 변경되었습니다.');
    if(!same(aliasContext(current,controller.id),aliasContext(previous,oldController.id)))reasons.push('컨트롤러 별칭의 구성원 또는 해석 정보가 변경되었습니다.');
    if(snapshotIndex(current).ambiguousOrder.has(role.id)||snapshotIndex(previous).ambiguousOrder.has(oldRole.id))reasons.push('규칙 순번이 중복되어 평가 순서를 확정할 수 없습니다.');
    return reasons;
  }
  function reconcileProjects(currentValue,previousValue,options) {
    const current=validateProject(currentValue),previous=validateProject(previousValue);
    options=safeCopy(options||{});obj(options,'options');for(const key of Object.keys(options))if(!['now','controllerMap'].includes(key))fail('options.'+key,'unknown option');
    const now=nowValue(options.now), mapping=options.controllerMap===undefined?{}:safeCopy(options.controllerMap);obj(mapping,'options.controllerMap');
    const curControllers=new Map(current.snapshot.controllers.map(c=>[c.id,c])),oldControllers=new Map(previous.snapshot.controllers.map(c=>[c.id,c]));
    for(const [oldId,newId]of Object.entries(mapping)){if(!oldControllers.has(oldId)||!curControllers.has(newId))fail('options.controllerMap','unknown controller association');}
    const controllerMatches=new Map();
    for(const old of previous.snapshot.controllers){const candidates=Object.hasOwn(mapping,old.id)?[curControllers.get(mapping[old.id])]:old.identityKnown?current.snapshot.controllers.filter(c=>c.identityKnown&&endpoint(c)===endpoint(old)):[];controllerMatches.set(old.id,candidates);}
    // A map must not quietly merge two old controllers into one current identity.
    const reverse=new Map();for(const [oldId,matches]of controllerMatches){if(matches.length===1){const target=matches[0].id;if(!reverse.has(target))reverse.set(target,[]);reverse.get(target).push(oldId);}}
    for(const oldIds of reverse.values())if(oldIds.length>1)for(const oldId of oldIds)controllerMatches.set(oldId,[]);
    const summary={reused:0,needsReview:0,unresolved:0};
    const existingUnresolvedIds=new Set(current.unresolvedAnnotations.map(u=>u.id));
    function uniqueId(base){base=base.slice(0,4000);let value=base,n=1;while(existingUnresolvedIds.has(value))value=base+':'+n++;existingUnresolvedIds.add(value);return value;}
    // Orphans remain durable across repeated reuse. Candidate IDs belong to their
    // original snapshot; retaining them is provenance, not an asserted live match.
    for(const u of previous.unresolvedAnnotations){
      const inherited=safeCopy(u), matches=controllerMatches.get(u.controllerId)||[];
      if(matches.length===1){inherited.controllerId=matches[0].id;inherited.controllerName=matches[0].name;}
      else inherited.controllerId='';
      if(current.unresolvedAnnotations.some(x=>same(x,inherited)))continue;
      inherited.id=uniqueId(inherited.id);current.unresolvedAnnotations.push(inherited);summary.unresolved++;
    }
    function unresolved(kind,old,annotation,reason,candidates){
      const oldRole=kind==='role'?old:previous.snapshot.roles.find(r=>r.id===old.roleId), oldController=oldControllers.get(old.controllerId);
      const matches=controllerMatches.get(old.controllerId)||[], context=matches.length===1?matches[0]:oldController;
      current.unresolvedAnnotations.push({id:uniqueId('import:'+previous.projectId+':'+kind+':'+old.id),kind,controllerId:matches.length===1?context.id:'',controllerName:context.name,roleName:oldRole.name,acl:kind==='rule'?old.acl:'',raw:kind==='rule'?old.raw:'',annotation:safeCopy(annotation),reason,candidateIds:candidates.map(x=>x.id),sourceProjectId:previous.projectId,sourceSnapshotId:previous.snapshot.id});summary.unresolved++;
    }
    const roleMatches=new Map(),possibleRoles=new Map(),ambiguousOldRoles=new Set(),currentIndex=snapshotIndex(current),previousIndex=snapshotIndex(previous);
    for(const oldRole of previous.snapshot.roles){
      const controllers=controllerMatches.get(oldRole.controllerId),oldSameName=previousIndex.rolesByName.get(JSON.stringify([oldRole.controllerId,oldRole.name]));
      const candidates=controllers.length===1?(currentIndex.rolesByName.get(JSON.stringify([controllers[0].id,oldRole.name]))||[]):[];
      possibleRoles.set(oldRole.id,candidates);
      if(oldSameName.length>1)ambiguousOldRoles.add(oldRole.id);
      roleMatches.set(oldRole.id,oldSameName.length===1?candidates:[]);
    }
    // Prefix states are exact interned sequences rather than lossy hashes. This
    // compares preceding rules in linear time even for large annotated ACLs.
    const prefixes=new Map(),prefixIds=new Map();let nextPrefix=1;
    for(const p of [previous,current]){const ids=new Map();for(const rows of snapshotIndex(p).rulesByRole.values()){let state=0;for(const r of rows){ids.set(r.id,state);const key=JSON.stringify([state,r.acl,raw(r)]);if(!prefixes.has(key))prefixes.set(key,nextPrefix++);state=prefixes.get(key);}}prefixIds.set(p,ids);}
    function transfer(kind,old,annotation,candidates,reasons){
      if(candidates.length!==1){let reason=candidates.length>1?'동일한 정책이 여러 번 나타납니다. 연결할 항목을 직접 선택해야 합니다.':'컨트롤러, 역할, ACL 및 전체 원문 규칙이 일치하는 단일 항목을 찾지 못했습니다.';const cs=controllerMatches.get(old.controllerId);if(!cs.length || cs.some(c=>c.coverage!=='completed'))reason+=' 수집 정보나 컨트롤러 식별 정보가 불완전합니다. 항목이 보이지 않는다는 이유만으로 삭제를 판단할 수 없습니다.';unresolved(kind,old,annotation,reason,candidates);return;}
      const target=candidates[0],bag=current.annotations[kind==='role'?'roles':'rules'];
      if(Object.hasOwn(bag,target.id)){unresolved(kind,old,annotation,'현재 메모가 이미 존재합니다. 가져온 메모는 충돌 항목으로 보존했습니다.',candidates);return;}
      if(annotation.status==='needs_review')reasons.push('이전 메모의 검토 필요 사항이 아직 해결되지 않았습니다.');
      const copied=safeCopy(annotation);copied.status=reasons.length?'needs_review':'reused';copied.updatedAt=now;copied.confirmedAt='';copied.reasons=Array.from(new Set(copied.reasons.concat(reasons,['재사용한 메모는 현재 정책에 맞는지 확인해야 합니다.'])));copied.source=copied.source||{projectId:previous.projectId,snapshotId:previous.snapshot.id,recordId:old.id,confirmedAt:annotation.confirmedAt};bag[target.id]=copied;summary.reused++;if(reasons.length)summary.needsReview++;
      if(reasons.length)current.changes.push({type:'context_changed',controllerId:target.controllerId,roleId:kind==='role'?target.id:target.roleId,ruleId:kind==='rule'?target.id:'',message:reasons.join(' '),previousRaw:kind==='rule'?old.raw:''});
    }
    for(const oldRole of previous.snapshot.roles){const matches=roleMatches.get(oldRole.id),role=matches.length===1?matches[0]:null;const reasons=role?roleContextReasons(current,previous,role,oldRole,curControllers.get(role.controllerId),oldControllers.get(oldRole.controllerId)):[];if(role&&!same(roleRules(current,role.id).map(r=>[r.acl,raw(r)]),roleRules(previous,oldRole.id).map(r=>[r.acl,raw(r)])))reasons.push('역할의 규칙 내용 또는 평가 순서가 변경되었습니다.');if(Object.hasOwn(previous.annotations.roles,oldRole.id)){if(ambiguousOldRoles.has(oldRole.id))unresolved('role',oldRole,previous.annotations.roles[oldRole.id],'이전 수집본에 동일한 이름의 역할이 중복되어 어느 항목인지 확정할 수 없습니다.',possibleRoles.get(oldRole.id));else transfer('role',oldRole,previous.annotations.roles[oldRole.id],matches,reasons);}}
    for(const old of previous.snapshot.rules){if(!Object.hasOwn(previous.annotations.rules,old.id))continue;const roles=roleMatches.get(old.roleId),role=roles.length===1?roles[0]:null;let candidates=role?(currentIndex.rulesByRaw.get(JSON.stringify([role.id,old.acl,raw(old)]))||[]):[];const oldDuplicates=previousIndex.rulesByRaw.get(JSON.stringify([old.roleId,old.acl,raw(old)]));const reasons=[];
      if(ambiguousOldRoles.has(old.roleId)||roles.length>1){const possible=possibleRoles.get(old.roleId).flatMap(r=>currentIndex.rulesByRaw.get(JSON.stringify([r.id,old.acl,raw(old)]))||[]);unresolved('rule',old,previous.annotations.rules[old.id],'동일한 이름의 역할이 중복되어 규칙의 소속을 확정할 수 없습니다.',possible);continue;}
      // Even one remaining occurrence cannot identify which former duplicate it was.
      if(oldDuplicates.length>1){unresolved('rule',old,previous.annotations.rules[old.id],'이전 수집본에 동일한 원문 규칙이 중복되어 어느 항목인지 확정할 수 없습니다.',candidates);continue;}
      if(role&&candidates.length===1){const target=candidates[0],oldRole=previous.snapshot.roles.find(r=>r.id===old.roleId);reasons.push(...roleContextReasons(current,previous,role,oldRole,curControllers.get(role.controllerId),oldControllers.get(old.controllerId)));if(prefixIds.get(current).get(target.id)!==prefixIds.get(previous).get(old.id))reasons.push('앞선 규칙 또는 평가 순서가 변경되었습니다.');if(!KNOWN_SERVICES.has(old.service.toLowerCase())||!KNOWN_SERVICES.has(target.service.toLowerCase()))reasons.push('서비스 정의를 확인할 수 없어 검토가 필요합니다.');if(!same([old.source,old.destination,old.service,old.action,old.sourceInterpretation,old.destinationInterpretation],[target.source,target.destination,target.service,target.action,target.sourceInterpretation,target.destinationInterpretation]))reasons.push('규칙의 해석 정보가 변경되었습니다.');}
      transfer('rule',old,previous.annotations.rules[old.id],candidates,reasons);
    }
    // Snapshot differences are reported independently of which policies had notes.
    const matchedRoleIds=new Set();
    for(const oldRole of previous.snapshot.roles){
      const matches=roleMatches.get(oldRole.id);
      if(matches.length!==1){const controllers=controllerMatches.get(oldRole.controllerId);if(controllers.length===1)current.changes.push({type:'role_not_observed',controllerId:controllers[0].id,roleId:'',ruleId:'',message:'이전 역할 '+oldRole.name+' 항목을 단일하게 확인할 수 없습니다. 수집 정보를 검토해야 합니다.',previousRaw:''});continue;}
      const role=matches[0];matchedRoleIds.add(role.id);const oldRows=roleRules(previous,oldRole.id),newRows=roleRules(current,role.id);
      const context=roleContextReasons(current,previous,role,oldRole,curControllers.get(role.controllerId),oldControllers.get(oldRole.controllerId));
      if(!same(oldRows.map(r=>[r.acl,raw(r)]),newRows.map(r=>[r.acl,raw(r)])))context.push('역할의 규칙 내용 또는 평가 순서가 변경되었습니다.');
      if(context.length)current.changes.push({type:'role_context_changed',controllerId:role.controllerId,roleId:role.id,ruleId:'',message:context.join(' '),previousRaw:''});
      const oldRaw=new Set(oldRows.map(r=>JSON.stringify([r.acl,raw(r)]))),newRaw=new Set(newRows.map(r=>JSON.stringify([r.acl,raw(r)])));
      for(const r of newRows)if(!oldRaw.has(JSON.stringify([r.acl,raw(r)])))current.changes.push({type:'rule_added',controllerId:role.controllerId,roleId:role.id,ruleId:r.id,message:'이번 수집본에서 새롭게 확인된 원문 규칙입니다.',previousRaw:''});
      for(const r of oldRows)if(!newRaw.has(JSON.stringify([r.acl,raw(r)]))){const c=curControllers.get(role.controllerId);current.changes.push({type:'rule_not_observed',controllerId:role.controllerId,roleId:role.id,ruleId:'',message:c.coverage==='completed'&&role.contextComplete?'이전 원문 규칙이 이번 수집본에 보이지 않습니다. 제거 여부를 확인해야 합니다.':'수집이 불완전하거나 수집 범위가 불명확하여 이전 원문 규칙의 존재 여부를 확인할 수 없습니다.',previousRaw:r.raw});}
    }
    for(const role of current.snapshot.roles)if(!matchedRoleIds.has(role.id))current.changes.push({type:'role_added',controllerId:role.controllerId,roleId:role.id,ruleId:'',message:'새롭게 확인된 역할이거나 이전 컨트롤러 및 역할과 단일하게 연결할 수 없는 항목입니다.',previousRaw:''});
    current.importHistory.push({projectId:previous.projectId,snapshotId:previous.snapshot.id,importedAt:now,...summary});current.revision++;current.updatedAt=now;
    return {project:validateProject(current),summary};
  }
  function emptyRecord(updatedAt){return {text:'',status:'unreviewed',updatedAt,confirmedAt:'',reasons:[],source:null};}
  function pending(a){return !!a&&(a.status==='reused'||a.status==='needs_review'||(a.status==='unreviewed'&&(a.text!==''||!!a.manualSsid||!!a.deviceType)));}
  function buildExportModel(value,scope,now){
    const p=validateProject(value),exportedAt=nowValue(now);scope=safeCopy(scope||{type:'all'});obj(scope,'scope');for(const key of Object.keys(scope))if(!['type','roleIds'].includes(key))fail('scope.'+key,'unknown field');choice(scope.type,['all','selected','review'],'scope.type');const ids=scope.roleIds===undefined?[]:scope.roleIds;strings(ids,'scope.roleIds');const byId=new Map(p.snapshot.roles.map(r=>[r.id,r]));for(const id of ids)if(!byId.has(id))fail('scope.roleIds','unknown role ID');
    let roles=p.snapshot.roles,rules=p.snapshot.rules;
    if(scope.type==='selected'){const selected=new Set(ids);roles=roles.filter(r=>selected.has(r.id));rules=rules.filter(r=>selected.has(r.roleId));}
    if(scope.type==='review'){
      const changedRules=new Set(p.changes.map(c=>c.ruleId).filter(Boolean)),changedRoles=new Set(p.changes.map(c=>c.roleId).filter(Boolean)),wholeRoles=new Set(p.changes.filter(c=>c.roleId&&!c.ruleId).map(c=>c.roleId));
      const uncertainControllers=new Set(p.snapshot.controllers.filter(c=>!c.identityKnown||c.coverage!=='completed'||c.failedCommands.length).map(c=>c.id));
      for(const issue of p.snapshot.issues){if(issue.roleId)wholeRoles.add(issue.roleId);else uncertainControllers.add(issue.controllerId);}
      for(const role of roles)if(!role.contextComplete||uncertainControllers.has(role.controllerId)||snapshotIndex(p).unknownServices.has(role.id)||snapshotIndex(p).ambiguousOrder.has(role.id))wholeRoles.add(role.id);
      rules=rules.filter(r=>pending(p.annotations.rules[r.id])||changedRules.has(r.id)||wholeRoles.has(r.roleId));const reviewRoles=new Set(rules.map(r=>r.roleId));roles=roles.filter(r=>reviewRoles.has(r.id)||changedRoles.has(r.id)||wholeRoles.has(r.id)||pending(p.annotations.roles[r.id]));
    }
    const roleIds=new Set(roles.map(r=>r.id)),controllerIds=new Set(roles.map(r=>r.controllerId)),ruleIds=new Set(rules.map(r=>r.id));
    let unresolved=p.unresolvedAnnotations;
    if(scope.type==='selected')unresolved=unresolved.filter(u=>{const matches=p.snapshot.roles.filter(r=>r.controllerId===u.controllerId&&r.name===u.roleName);return matches.length===1&&roleIds.has(matches[0].id);});
    const controllerMap=new Map(p.snapshot.controllers.map(c=>[c.id,c]));
    if(scope.type==='all')p.snapshot.controllers.forEach(c=>controllerIds.add(c.id));
    if(scope.type==='review'){
      for(const u of unresolved)if(controllerMap.has(u.controllerId))controllerIds.add(u.controllerId);
      for(const change of p.changes)if(controllerMap.has(change.controllerId))controllerIds.add(change.controllerId);
      for(const controller of p.snapshot.controllers)if(!controller.identityKnown||controller.coverage!=='completed'||controller.failedCommands.length)controllerIds.add(controller.id);
      for(const issue of p.snapshot.issues)controllerIds.add(issue.controllerId);
    }
    const changes=p.changes.filter(c=>scope.type==='all'||scope.type==='review'||(c.ruleId?ruleIds.has(c.ruleId):c.roleId?roleIds.has(c.roleId):controllerIds.has(c.controllerId)));
    const exportedRoles=roles.map(r=>({...r,controllerName:controllerMap.get(r.controllerId).name,annotation:p.annotations.roles[r.id]||emptyRecord(p.updatedAt)}));
    const exportedRules=rules.map(r=>({...r,controllerName:controllerMap.get(r.controllerId).name,roleName:byId.get(r.roleId).name,annotation:p.annotations.rules[r.id]||emptyRecord(p.updatedAt)}));
    return {projectId:p.projectId,snapshotId:p.snapshot.id,revision:p.revision,collectedAt:p.snapshot.collectedAt,updatedAt:p.updatedAt,exportedAt,scopeLabel:scope.type==='all'?'전체 정책':scope.type==='review'?'변경 및 검토 항목':'선택한 역할 ('+roles.length+')',controllers:p.snapshot.controllers.filter(c=>controllerIds.has(c.id)),roles:exportedRoles,rules:exportedRules,aliases:p.snapshot.aliases.filter(a=>controllerIds.has(a.controllerId)),localNetworks:p.snapshot.localNetworks.filter(n=>roleIds.has(n.roleId)),changes,unresolvedAnnotations:unresolved,issues:p.snapshot.issues.filter(i=>roleIds.has(i.roleId)||(!i.roleId&&controllerIds.has(i.controllerId))),summary:{controllerCount:controllerIds.size,roleCount:roles.length,ruleCount:rules.length,annotatedRuleCount:exportedRules.filter(r=>r.annotation.text!=='').length,needsReviewCount:exportedRoles.filter(r=>pending(r.annotation)).length+exportedRules.filter(r=>pending(r.annotation)).length+unresolved.length}};
  }
  return Object.freeze({parseProject,validateProject,reconcileProjects,buildExportModel,isCommonAclName});
}));
