/* Inert file import. Imported HTML nodes remain inside detached template.content. */
(function(root,factory){
  'use strict';
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.AnnotationImport=factory();
}(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const MAX_FILE=50*1024*1024;
  const IMPORT_REASON='이전 HTML에서 가져왔습니다. 컨트롤러 식별 정보와 수집 완전성을 확인할 수 없어 주석을 직접 검토해야 합니다.';
  const unsafe=new Set(['__proto__','prototype','constructor']);
  const own=(object,key)=>Object.prototype.hasOwnProperty.call(object,key);
  function error(message){throw new Error('주석 파일 가져오기: '+message);}
  function checkSize(text){
    if(typeof text!=='string')error('파일 내용은 텍스트여야 합니다.');
    // Count UTF-8 bytes without allocating another potentially large document.
    if(text.length>MAX_FILE)error('50 MiB 파일 크기 제한을 초과했습니다.');
    let bytes=0;
    for(let i=0;i<text.length;i++){
      const code=text.charCodeAt(i);
      if(code<0x80)bytes++;
      else if(code<0x800)bytes+=2;
      else if(code>=0xd800&&code<=0xdbff&&i+1<text.length&&text.charCodeAt(i+1)>=0xdc00&&text.charCodeAt(i+1)<=0xdfff){bytes+=4;i++;}
      else bytes+=3;
      if(bytes>MAX_FILE)error('50 MiB 파일 크기 제한을 초과했습니다.');
    }
  }
  function content(node){return node?node.textContent||'':'';}
  function one(root,selector){
    const found=root.querySelectorAll(selector);
    if(found.length>1)error('중복된 데이터 요소: '+selector);
    return found[0]||null;
  }
  function embedded(root,selector){
    const node=one(root,selector);
    if(!node)return Object.create(null);
    let value;
    try{value=JSON.parse(content(node)||'{}');}catch(_){error('손상된 레거시 JSON 데이터: '+selector);}
    if(value===null||typeof value!=='object'||Array.isArray(value))error('레거시 주석 데이터는 객체여야 합니다.');
    for(const key of Object.keys(value)){
      if(unsafe.has(key))error('안전하지 않은 주석 키는 허용되지 않습니다.');
      if(typeof value[key]!=='string')error('레거시 주석은 문자열이어야 합니다.');
    }
    return value;
  }
  function plainText(node){
    if(!node)return '';
    let result='';
    for(const child of node.childNodes){
      if(child.nodeType===3)result+=child.textContent;
      else if(child.nodeType===1&&!child.matches('.notice,script,style,template'))result+=plainText(child);
    }
    return result;
  }
  function endpoint(node){
    const links=node.querySelectorAll('.alias-link');
    if(links.length===1){
      const prefix=node.querySelector('.alias-prefix');
      return (prefix?plainText(prefix).trim():'alias')+' '+plainText(links[0]).trim();
    }
    return plainText(node).trim();
  }
  function timestamp(root,now){
    const header=root.querySelector('header');
    const match=content(header).match(/\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)/);
    return match&&Number.isFinite(Date.parse(match[0]))?{value:match[0],known:true}:{value:now,known:false};
  }
  function parseLegacy(root,Core){
    const panels=Array.from(root.querySelectorAll('.role-panel'));
    if(!panels.length)error('지원하는 주석 프로젝트 또는 레거시 Role 보고서가 아닙니다.');
    const comments=embedded(root,'#acl-comments-data'),descriptions=embedded(root,'#role-descriptions-data');
    const now=new Date().toISOString(),time=timestamp(root,now);
    const token=now.replace(/[^0-9]/g,'')+'-'+Math.random().toString(36).slice(2);
    const p={format:'aruba-policy-annotations',schemaVersion:1,projectId:'legacy-project-'+token,revision:0,createdAt:time.value,updatedAt:now,snapshot:{id:'legacy-snapshot-'+token,collectedAt:time.value,controllers:[],roles:[],rules:[],aliases:[],localNetworks:[],issues:[]},annotations:{roles:{},rules:{}},unresolvedAnnotations:[],changes:[],importHistory:[]};
    const snapshot=p.snapshot,groups=new Map(),roleTargets=new Map(),ruleTargets=new Map(),aliasGroups=new Map(),usedInputs=new Set();
    const metrics=Array.from(root.querySelectorAll('.metric-label'));
    function note(text){return {text,status:'needs_review',updatedAt:now,confirmedAt:'',reasons:[IMPORT_REASON],source:null};}
    function issue(controllerId,roleId,message){snapshot.issues.push({controllerId,roleId,message});}
    function addTarget(map,key,entity,input){
      if(!key)return;
      if(input)usedInputs.add(input);
      const targets=map.get(key)||[];
      targets.push({entity,input});map.set(key,targets);
    }
    function controllerFor(panel,index){
      const source=panel.getAttribute('data-controller');
      const metric=metrics.length===1?content(metrics[0]).trim():'';
      const name=source&&source.trim()?source.trim():metric||'장비 미확인';
      // A source label groups panels only inside this imported file. It never
      // establishes an endpoint identity or an association to another snapshot.
      const key=source&&source.trim()?'source:'+source:metric?'single-metric:'+metric:'unknown-panel:'+index;
      if(!groups.has(key)){
        const c={id:'legacy-controller-'+(groups.size+1),name,host:'',port:0,scope:'effective',identityKnown:false,coverage:'unknown',failedCommands:[]};
        groups.set(key,c);snapshot.controllers.push(c);
        issue(c.id,'',IMPORT_REASON);
        if(!time.known)issue(c.id,'','원본 보고서에서 시간대가 포함된 생성 시각을 확인할 수 없어 가져온 시각을 사용했습니다.');
      }
      return groups.get(key);
    }
    panels.forEach(function(panel,panelIndex){
      const controller=controllerFor(panel,panelIndex);
      const descriptionInputs=Array.from(panel.querySelectorAll('.role-description-input'));
      const name=(panel.getAttribute('data-role')||content(panel.querySelector('h3'))||descriptionInputs[0]&&descriptionInputs[0].getAttribute('data-role')||'').trim();
      if(!name)error('Role 이름이 없는 레거시 패널입니다.');
      if(descriptionInputs.length>1)error('한 Role 패널의 설명 입력란이 중복되었습니다.');
      const table=panel.querySelector('table');
      if(!table)error('Role ACL 테이블이 없습니다.');
      // Older reports may omit acl-rule-row on some hidden rows. Read every
      // policy table body row; visibility and Access Check's subset are irrelevant.
      const rows=Array.from(panel.querySelectorAll('table tbody > tr')).filter(row=>!row.classList.contains('alias-detail-row')&&Array.from(row.children).some(child=>child.tagName.toLowerCase()==='td'));
      if(!rows.length&&table.querySelectorAll('thead th').length!==8)error('인식할 수 없는 Role ACL 테이블입니다.');
      const users=content(panel.querySelector('.acl-section-header')).match(/(\d+)\s+observed users/i);
      const role={id:'legacy-role-'+(snapshot.roles.length+1),controllerId:controller.id,name,ssids:[],roleTypes:[],aclOrder:[],bindingRaw:[],contextComplete:false,observedUsers:users?Number(users[1]):0};
      snapshot.roles.push(role);
      const input=descriptionInputs[0]||null;
      // A missing textarea can still have an authoritative embedded description.
      addTarget(roleTargets,input&&input.getAttribute('data-role')||name,role,input);
      rows.forEach(function(row,index){
        const cells=Array.from(row.children).filter(child=>child.tagName.toLowerCase()==='td');
        if(cells.length!==8)error('손상된 레거시 ACL 행: 8개 열이 필요합니다.');
        const raw=content(cells[6]);
        const acl=plainText(cells[0]).trim();
        const inputs=cells[7].querySelectorAll('.comment-input');
        if(inputs.length>1)error('한 ACL 행의 주석 입력란이 중복되었습니다.');
        if(!raw.trim()){
          const action=plainText(cells[2]).trim(),service=plainText(cells[5]).trim();
          // Old report renderers displayed UNKNOWN/ANY badges for a policy
          // whose underlying action/service fields were empty. Only this exact
          // presentation, or fully blank cells, is a no-rule placeholder.
          const blankPresentation=!action&&!service;
          const historicalDefaults=action==='unknown'&&!!cells[2].querySelector('.rule-badge.action-unknown')&&service==='any'&&!!cells[5].querySelector('.rule-badge.service-badge');
          const emptyFields=[cells[1],cells[3],cells[4]].every(cell=>content(cell).trim()==='');
          if((!blankPresentation&&!historicalDefaults)||!emptyFields)error('원문 규칙이 없는 레거시 ACL 행은 가져올 수 없습니다.');
          for(const name of acl.split(',').map(value=>value.trim()).filter(Boolean))if(!role.aclOrder.includes(name))role.aclOrder.push(name);
          if(inputs[0]){
            const input=inputs[0],key=input.getAttribute('data-comment-id');
            const target={entity:null,input,placeholder:{role,controller,acl}};
            usedInputs.add(input);
            if(key){
              const targets=ruleTargets.get(key)||[];targets.push(target);ruleTargets.set(key,targets);
            }else if(content(input)!=='')unresolved('rule','(이전 주석 키 없음)',content(input),[target]);
          }
          return;
        }
        const rule={id:'legacy-rule-'+(snapshot.rules.length+1),controllerId:controller.id,roleId:role.id,acl,sequence:plainText(cells[1]).trim(),ordinal:index+1,raw,source:endpoint(cells[3]),destination:endpoint(cells[4]),service:plainText(cells[5]).trim(),action:plainText(cells[2]).trim(),sourceInterpretation:Array.from(cells[3].querySelectorAll('.notice')).map(content).join('\n'),destinationInterpretation:Array.from(cells[4].querySelectorAll('.notice')).map(content).join('\n')};
        snapshot.rules.push(rule);
        if(!role.aclOrder.includes(acl))role.aclOrder.push(acl);
        if(inputs[0]){
          const key=inputs[0].getAttribute('data-comment-id');
          if(key)addTarget(ruleTargets,key,rule,inputs[0]);
          else{
            usedInputs.add(inputs[0]);
            if(content(inputs[0])!=='')p.annotations.rules[rule.id]=note(content(inputs[0]));
          }
        }
      });
      issue(controller.id,role.id,'Role의 ACL 연결 순서는 숨겨진 ACL을 포함한 이전 보고서의 행 순서에서 추정했습니다. 연결 정보의 수집 완전성과 규칙 평가 문맥은 확인되지 않았습니다.');
      for(const title of panel.querySelectorAll('.alias-detail-title')){
        const match=content(title).match(/^\s*(?:Source|Destination)\s+alias:\s*(.+?)\s*$/i);
        if(!match)continue;
        const aliasName=match[1],entries=[];
        const container=title.nextElementSibling;
        if(container){
          for(const chip of container.querySelectorAll('.alias-chip')){
            const typeNode=chip.querySelector('.alias-type'),spans=Array.from(chip.children).filter(child=>child.tagName.toLowerCase()==='span');
            if(!typeNode||spans.length<2)error('손상된 Alias 상세 항목입니다.');
            const type=content(typeNode).trim().toLowerCase(),value=content(spans[1]).trim();
            entries.push({type,value,raw:(type+' '+value).trim()});
          }
        }
        const key=JSON.stringify([controller.id,aliasName]),existing=aliasGroups.get(key);
        if(!existing){
          const alias={id:'legacy-alias-'+(snapshot.aliases.length+1),controllerId:controller.id,name:aliasName,entries};
          snapshot.aliases.push(alias);aliasGroups.set(key,alias);
        }else if(JSON.stringify(existing.entries)!==JSON.stringify(entries)){
          // Conflicting repeated detail is evidence of incomplete legacy data.
          for(const entry of entries)if(!existing.entries.some(item=>JSON.stringify(item)===JSON.stringify(entry)))existing.entries.push(entry);
          issue(controller.id,role.id,'이전 보고서의 Alias 상세 내용이 서로 다릅니다: '+aliasName+'. 관측된 항목을 보존했으며 직접 검토해야 합니다.');
        }
      }
    });
    function unresolved(kind,key,text,targets){
      const candidates=targets||[];
      const entity=candidates.length===1?candidates[0].entity:null;
      const placeholder=candidates.length===1?candidates[0].placeholder:null;
      const role=entity?(kind==='role'?entity:snapshot.roles.find(r=>r.id===entity.roleId)):placeholder?placeholder.role:null;
      const controller=entity?snapshot.controllers.find(c=>c.id===entity.controllerId):placeholder?placeholder.controller:null;
      const reason=placeholder?'규칙이 없는 안내 행의 주석을 보존했습니다. 연결할 실제 규칙을 직접 확인해야 합니다. 이전 주석 키: ':candidates.length?'이전 주석 키에 해당하는 항목이 여러 개입니다. 연결할 항목을 직접 선택해야 합니다. 이전 주석 키: ':'이전 주석 키에 해당하는 보고서 행이 없습니다. 이전 주석 키: ';
      p.unresolvedAnnotations.push({id:'legacy-unresolved-'+(p.unresolvedAnnotations.length+1),kind,controllerId:controller?controller.id:'',controllerName:controller?controller.name:'',roleName:role?role.name:kind==='role'?key:'',acl:kind==='rule'&&entity?entity.acl:placeholder?placeholder.acl:'',raw:kind==='rule'&&entity?entity.raw:'',annotation:note(text),reason:reason+JSON.stringify(key),candidateIds:candidates.filter(x=>x.entity).map(x=>x.entity.id),sourceProjectId:p.projectId,sourceSnapshotId:snapshot.id});
    }
    function applyNotes(kind,map,values){
      const bag=p.annotations[kind==='role'?'roles':'rules'];
      for(const [key,targets]of map){
        if(own(values,key)){
          // Presence, including an empty string, suppresses stale textarea fallback.
          if(targets.length===1&&targets[0].entity)bag[targets[0].entity.id]=note(values[key]);
          else unresolved(kind,key,values[key],targets);
        }else{
          for(const target of targets){
            const text=target.input?content(target.input):'';
            if(text!==''){
              if(target.entity)bag[target.entity.id]=note(text);
              else unresolved(kind,key,text,[target]);
            }
          }
        }
      }
      for(const key of Object.keys(values))if(!map.has(key))unresolved(kind,key,values[key],[]);
    }
    applyNotes('role',roleTargets,descriptions);applyNotes('rule',ruleTargets,comments);
    // Detached textareas outside a recognized policy record can still contain
    // work. Preserve their fallback text as unresolved rather than discarding it.
    for(const input of root.querySelectorAll('.role-description-input,.comment-input')){
      if(usedInputs.has(input))continue;
      const kind=input.classList.contains('role-description-input')?'role':'rule';
      const key=input.getAttribute(kind==='role'?'data-role':'data-comment-id')||'(이전 주석 키 없음)';
      const values=kind==='role'?descriptions:comments;
      if(!own(values,key)&&content(input)!=='')unresolved(kind,key,content(input),[]);
    }
    return Core.validateProject(p);
  }
  function parse(text,document,Core){
    checkSize(text);
    if(!Core||typeof Core.parseProject!=='function'||typeof Core.validateProject!=='function')error('프로젝트 검증기가 필요합니다.');
    const trimmed=text.trimStart();
    if(trimmed.startsWith('{')||trimmed.startsWith('['))return Core.parseProject(text);
    if(!trimmed.startsWith('<'))error('JSON 프로젝트 또는 HTML 보고서가 아닙니다.');
    if(!document||typeof document.createElement!=='function')error('안전한 HTML 파서가 필요합니다.');
    // Template parsing is inert. Never append its content to the active document,
    // use DOMParser resource loading, evaluate imported scripts, or fetch URLs.
    const template=document.createElement('template');
    template.innerHTML=text;
    const root=template.content;
    const modern=one(root,'script#annotation-project-data');
    if(modern)return Core.parseProject(content(modern));
    return parseLegacy(root,Core);
  }
  return {parse};
}));
