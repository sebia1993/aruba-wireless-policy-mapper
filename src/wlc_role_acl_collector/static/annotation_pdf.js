/* Browser-only PDF export: searchable Korean text, offline fonts, no print dialog. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AnnotationPdf = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  // Use the same common-ACL classifier as the interactive Role editor.
  const aclCore = (typeof module==='object' && module.exports)
    ? require('./annotation_core.js') : globalThis.AnnotationCore;
  const COLORS = {navy:'#183959', muted:'#587086', rule:'#D7E2EC', fill:'#EAF1F8', alert:'#A15C10'};
  const STATUS = {reviewed:'확인 완료',unreviewed:'미확인',reused:'이전 주석 재사용',needs_review:'재확인 필요'};
  const COVERAGE = {completed:'수집 완료',partial:'일부 수집',failed:'수집 실패',unknown:'수집 범위 미확인'};
  const MAX_JSON_CHARS = 8 * 1024 * 1024;
  const MAX_RULES = 10000;

  const str = value => value == null ? '' : String(value);
  const nonempty = (value, fallback='미입력') => str(value).trim() || fallback;
  const title = text => ({text:str(text),style:'sectionHeading',margin:[0,13,0,6]});
  const para = (text,opts) => ({text:str(text),style:'smallText',margin:[0,2,0,6],...(opts||{})});
  const label = code => STATUS[str(code)] || nonempty(code,'미확인');
  const common = acl => aclCore.isCommonAclName(acl);
  const device = v => ({windows_pc:'윈도우 PC',macbook:'맥북',PC:'PC (기존 분류)'}[str(v)] || nonempty(v,'미지정'));
  const roleKey = role => JSON.stringify([role.controllerId,role.id]);
  const roleTarget = role => nonempty(role.controllerName,'컨트롤러 미확인')+' / '+nonempty(role.name,'Role 미확인');
  const action = rule => nonempty(rule.action,'미확인');
  const note = record => str(record?.annotation?.text);
  const aclNote = rule => {
    const text=note(rule);
    return text.trim() ? text : '';
  };
  const checked = record => label(record?.annotation?.status);
  const related = (rule,role) => rule.roleId===role.id && rule.controllerId===role.controllerId;
  const bodyCell = (value,opts) => ({text:Array.isArray(value)?value:str(value),style:'tableBody',...(opts||{})});
  const headerCell = value => ({text:str(value),style:'tableHead',fillColor:COLORS.fill});
  const rowsTable = (headers,rows,widths) => ({
    // Repeat the header alone so a first-row annotation can span several pages.
    table:{headerRows:1,widths:widths||headers.map(()=>'*'),
      body:[headers.map(headerCell),...(rows.length?rows:[[headers.length===1?'해당 항목 없음':'대상 항목 없음',...headers.slice(1).map(()=>'')]].map(row=>row.map(value=>typeof value==='object'&&value!==null&&Object.hasOwn(value,'text')?value:bodyCell(value))))]},
    layout:{hLineColor:()=>COLORS.rule,vLineColor:()=>COLORS.rule,paddingTop:()=>5,paddingBottom:()=>5,paddingLeft:()=>6,paddingRight:()=>6},
    margin:[0,0,0,10]
  });

  function validateModel(model) {
    if(!model || typeof model!=='object' || !Array.isArray(model.roles) || !Array.isArray(model.rules) || !Array.isArray(model.controllers)) {
      throw new Error('PDF 출력 모델의 Role, ACL 또는 컨트롤러 정보가 올바르지 않습니다.');
    }
    if(model.rules.length>MAX_RULES)throw new Error('PDF 규칙이 10,000개를 초과합니다. 선택 Role로 범위를 줄이거나 Excel로 저장하세요.');
    const content=JSON.stringify(model);
    if(content.length>MAX_JSON_CHARS)throw new Error('PDF 원문·주석의 전체 크기가 큽니다. 보고 범위를 줄이거나 Excel로 저장하세요.');
  }

  function ruleTarget(rule) {
    return nonempty(rule.controllerName,'WLC 미확인')+' / '+nonempty(rule.roleName,'Role 미확인')+
      '\n컨트롤러 ID: '+nonempty(rule.controllerId,'미확인')+' / Role ID: '+nonempty(rule.roleId,'미확인')+
      '\n규칙 ID: '+nonempty(rule.id,'미확인');
  }

  function shortAliasText(found,detailed){
    const memberText=entry=>[entry.type,entry.value].filter(Boolean).join(' ');
    const lines=found.members.length ? found.members.map(memberText) : [found.summary];
    if(detailed){
      const members=new Set(found.members);
      for(const entry of found.alias.entries){
        const collected=nonempty(entry.raw,memberText(entry));
        if(collected && (!members.has(entry) || collected!==memberText(entry)))lines.push('Alias 원문: '+collected);
      }
    }
    return lines.join('\n');
  }

  function reportAliases(model,detailed=false) {
    const lookup=aclCore.createAliasLookup(model.aliases||[]);
    const definitions=new Map();
    const appendix=[];
    let expandedChars=0;
    // Number by first use in the scoped rule order, before a profile groups rows.
    for(const rule of model.rules){
      for(const field of [rule.source,rule.destination]){
        const found=lookup(rule.controllerId,field);
        if(!found?.alias || definitions.has(found.alias.id))continue;
        const code=found.members.length>3?'A'+String(appendix.length+1).padStart(2,'0'):'';
        const display=code?found.summary:shortAliasText(found,detailed);
        definitions.set(found.alias.id,{display,code});
        if(code)appendix.push({found,code,controllerId:rule.controllerId,controllerName:rule.controllerName});
      }
    }
    function operand(rule,field){
      const value=nonempty(field,'미확인');
      const found=lookup(rule.controllerId,field);
      if(!found)return [value];
      if(!found.alias)return [value+'\n'+found.summary];
      const {display,code}=definitions.get(found.alias.id);
      expandedChars+=display.length;
      if(expandedChars>MAX_JSON_CHARS)throw new Error('PDF에 표시할 Alias 정보가 큽니다. 보고 범위를 줄이거나 Excel로 저장하세요.');
      if(!code)return [value+'\n'+display];
      return [value+'\n'+display+' ',{text:'['+code+']',linkToDestination:'alias-'+code,
        color:'#205894',decoration:'underline'}];
    }
    return {operand,appendix};
  }

  function appendAliasTables(content,definitions,detailed,controllerLabel){
    for(const {found,code,controllerId,controllerName} of definitions){
      const alias=found.alias;
      const heading={id:'alias-'+code,text:'['+code+']  '+controllerLabel({controllerId,controllerName})+' / '+alias.name,
        style:detailed?'roleHeading':'groupHeading',margin:[0,10,0,4]};
      content.push(heading);
      if(detailed){
        content.push(para('컨트롤러 ID: '+controllerId+'   |   Alias ID: '+alias.id));
        const rows=alias.entries.map(entry=>[entry.type,entry.value,entry.raw]);
        content.push(rowsTable(['유형','값','수집 원문'],rows,[72,145,'*']));
      }else{
        content.push(rowsTable(['유형','구성원'],found.members.map(entry=>[entry.type,entry.value]),[105,'*']));
      }
    }
  }

  function policyText(rule,aliases){
    return ['동작: '+action(rule)+'\n출발지: ',...aliases.operand(rule,rule.source),
      '\n목적지: ',...aliases.operand(rule,rule.destination),'\n서비스: '+nonempty(rule.service,'미확인')+
      '\n원문: '+nonempty(rule.raw,'수집 원문 없음')];
  }

  function aclAppendixTable(headers,rules,policyCells,widths,includeNotes) {
    const rows=rules.map(rule=>{
      const [identity,policy]=policyCells(rule);
      const text=aclNote(rule);
      const status=rule.annotation?.status;
      const explicitStatus=status && status!=='unreviewed' ? checked(rule) : '';
      if(includeNotes)return [bodyCell(identity),bodyCell(policy),bodyCell(text ? checked(rule)+'\n'+text : explicitStatus)];
      return [bodyCell(explicitStatus ? identity+'\n확인 상태: '+explicitStatus : identity),bodyCell(policy)];
    });
    return rowsTable(includeNotes ? [...headers,'주석 및 확인'] : headers,rows,
      includeNotes ? widths : [widths[0],'*']);
  }

  // Compact mode deliberately limits report content without modifying the
  // immutable export model. Repeat groups only when consecutive occurrences
  // share the exact WLC/Role/ACL identity: ACL evaluation order is not sorted.
  function compactDocumentDefinition(model) {
    validateModel(model);
    const rules=model.rules||[], controllers=model.controllers||[];
    const aliases=reportAliases(model);
    const includeNotes=rules.some(aclNote);
    const headers=['순서','출발지','목적지','서비스','동작'];
    if(includeNotes)headers.push('행별 주석');
    const widths=includeNotes ? [42,124,124,112,55,'*'] : [42,'*','*',150,72];
    const incomplete=controllers.some(c=>!c.identityKnown||c.coverage!=='completed'||(c.failedCommands||[]).length>0);
    const byId=new Map(controllers.map(c=>[c.id,c]));
    const duplicateNames=new Map();
    controllers.forEach(c=>{const n=str(c.name);duplicateNames.set(n,(duplicateNames.get(n)||0)+1);});
    const controllerLabel=rule=>{
      const c=byId.get(rule.controllerId),name=str(rule.controllerName||c?.name);
      if((duplicateNames.get(name)||0)<2)return nonempty(name,'미확인');
      return nonempty(name,'미확인')+' ('+(c?.host?c.host+(c.port?':'+c.port:''):'ID '+str(rule.controllerId))+')';
    };
    const content=[
      {text:'ACL 규칙 간단 보고서',style:'reportTitle',margin:[0,0,0,7]},
      para('보고 범위: '+nonempty(model.scopeLabel,'전체 정책')+'   |   수집: '+nonempty(model.collectedAt,'미확인')+
        '   |   출력: '+nonempty(model.exportedAt,'미확인'))
    ];
    if(incomplete)content.push(para('주의: 수집 미완료 또는 확인되지 않은 컨트롤러가 포함되어 누락된 규칙이 있을 수 있습니다.',
      {color:COLORS.alert,bold:true}));
    content.push(para(model.showCommonAcl===false?'공통 ACL은 이 보고서에서 제외했습니다.':'공통 ACL도 보고 범위에 포함됩니다.'));
    const groups=[];
    for(const rule of rules){
      const key=JSON.stringify([rule.controllerId,rule.roleId,rule.acl]);
      let last=groups[groups.length-1];
      if(!last || last.key!==key){last={key,rules:[]};groups.push(last);}
      last.rules.push(rule);
    }
    if(!groups.length)content.push(para('선택한 보고 범위에서 표시할 ACL 규칙이 없습니다.'));
    for(const group of groups){
      const first=group.rules[0];
      content.push({text:'컨트롤러: '+controllerLabel(first)+
        '   |   Role: '+nonempty(first.roleName,'미확인')+
        '   |   ACL: '+nonempty(first.acl,'미확인'),
        style:'groupHeading',margin:[0,11,0,4]});
      const rows=group.rules.map(rule=>{
        const cells=[nonempty(rule.sequence,nonempty(rule.ordinal,'?')),aliases.operand(rule,rule.source),
          aliases.operand(rule,rule.destination),nonempty(rule.service,'미확인'),nonempty(rule.action,'미확인')];
        if(includeNotes)cells.push(aclNote(rule));
        return cells.map(value=>bodyCell(value));
      });
      content.push(rowsTable(headers,rows,[...widths]));
    }
    if(aliases.appendix.length){
      content.push({text:'Alias 상세',style:'reportTitle',pageBreak:'before',margin:[0,0,0,7]});
      appendAliasTables(content,aliases.appendix,false,controllerLabel);
    }
    return {
      pageSize:'A4',pageOrientation:'landscape',pageMargins:[26,42,26,39],
      info:{title:'ACL 규칙 간단 보고서',subject:str(model.scopeLabel),creator:'Aruba Wireless Policy Mapper'},
      defaultStyle:{font:'NanumGothic',fontSize:8.5,color:COLORS.navy,lineHeight:1.2},
      styles:{
        reportTitle:{fontSize:18,bold:true,color:COLORS.navy},
        groupHeading:{fontSize:10.5,bold:true,color:COLORS.navy},
        smallText:{fontSize:8,color:COLORS.muted},
        tableHead:{fontSize:8,bold:true,color:COLORS.navy},
        tableBody:{fontSize:8,lineHeight:1.22}
      },
      header:()=>({text:'ARUBA ACL POLICY  |  '+nonempty(model.scopeLabel,'전체 정책'),
        font:'NanumGothic',fontSize:7,color:COLORS.muted,alignment:'right',margin:[26,17,26,0]}),
      footer:(page,total)=>({text:page+' / '+total,font:'NanumGothic',fontSize:7,
        color:COLORS.muted,alignment:'center',margin:[26,0,26,18]}),
      content
    };
  }
  function documentDefinition(model, options) {
    if (options && options.profile === 'simple') return compactDocumentDefinition(model);
    validateModel(model);
    const controllers=model.controllers||[], roles=model.roles||[], rules=model.rules||[];
    const aliases=reportAliases(model,true);
    const showCommonAcl=model.showCommonAcl!==false;
    const includeNotes=rules.some(aclNote);
    const byController=new Map(controllers.map(c=>[c.id,c]));
    const shared=rules.filter(r=>common(r.acl)),exclusive=rules.filter(r=>!common(r.acl));
    const incomplete=controllers.filter(c=>!c.identityKnown||c.coverage!=='completed'||(c.failedCommands||[]).length);
    const changeItems=model.changes||[], unresolved=model.unresolvedAnnotations||[], issues=model.issues||[];
    const content=[];
    content.push({text:'WIRELESS POLICY REVIEW',style:'kicker',margin:[0,0,0,6]});
    content.push({text:'무선랜 Role 및 ACL 정책 점검 보고서',style:'reportTitle',margin:[0,0,0,9]});
    content.push(para('보고 범위: '+nonempty(model.scopeLabel,'전체 정책')+'\n수집 시각: '+nonempty(model.collectedAt,'미확인')+
      '   |   보고서 생성: '+nonempty(model.exportedAt,'미확인')+
      '\n프로젝트: '+nonempty(model.projectId)+' / 스냅샷: '+nonempty(model.snapshotId)+' / 버전: '+str(model.revision)));
    content.push({text:'본 보고서는 WLC에서 수집된 정책과 운영자가 작성한 주석을 정리한 문서입니다. 정책 적합성 및 실제 통신 성공을 자동으로 보증하지 않습니다.',
      style:'disclaimer',margin:[0,3,0,10]});

    content.push(title('1. 점검 현황 및 핵심 지표'));
    const stats=[
      ['WLC',''+controllers.length],['Role',''+roles.length],
      ['ACL 규칙',''+rules.length]
    ];
    if(showCommonAcl)stats.push(['Role 전용 규칙',''+exclusive.length],['공통 정책 규칙',''+shared.length]);
    stats.push(['검토 필요 주석',''+(model.summary?.needsReviewCount??'미확인')]);
    content.push(rowsTable(['집계 항목','수량'],stats,[160,'*']));
    if(incomplete.length){
      content.push(para('수집 신뢰도 주의: 수집 미완료/식별 미확인/명령 실패 장비 '+incomplete.length+'대가 포함됩니다. 누락된 규칙을 삭제된 정책으로 판단하지 마세요.',
        {color:COLORS.alert,bold:true}));
    }else{
      content.push(para('수집 상태: 제공된 컨트롤러 범위에서 수집 누락 또는 실패 명령이 기록되지 않았습니다. 별도 정책 적합성 검증은 필요합니다.'));
    }
    content.push(title('2. 컨트롤러 및 수집 신뢰도'));
    content.push(rowsTable(['컨트롤러 / 식별 정보','수집 상태','주의 / 실패 명령'],controllers.map(c=>[
      bodyCell(nonempty(c.name)+'\n'+nonempty(c.host,'주소 미확인')+':'+nonempty(c.port,'?')+
        '\nID: '+nonempty(c.id)+'\n범위: '+nonempty(c.scope,'미확인')),
      bodyCell(COVERAGE[c.coverage]||'미확인'),
      bodyCell((!c.identityKnown?'장비 식별 불명확\n':'')+((c.failedCommands||[]).length?
        '실패 명령: '+(c.failedCommands||[]).map(str).join(', '):'특이 사항 없음'))
    ]),[185,80,'*']));

    content.push(title('3. Role별 정책 현황'));
    content.push(para(showCommonAcl?'전용 규칙과 공통 ACL 규칙은 구분해 집계합니다. 공통 ACL은 뒤쪽 부록에 컨트롤러·Role 적용 관계와 함께 표시합니다.':'HTML에서 공통 ACL을 숨겨 Role별 전용 규칙만 집계했습니다.'));
    const roleRows=roles.map(r=>{
      const current=rules.filter(rule=>related(rule,r));
      const own=current.filter(rule=>!common(rule.acl)), sharedRole=current.filter(rule=>common(rule.acl));
      const a=r.annotation||{};
      return [
        bodyCell(nonempty(r.controllerName)+'\n'+nonempty(r.name)+'\nRole ID: '+nonempty(r.id)),
        bodyCell(((r.ssids||[]).map(str).join(', ')||'연결 정보 없음')+'\n수기 SSID: '+nonempty(a.manualSsid,'미입력')),
        bodyCell(device(a.deviceType)),
        bodyCell('전용 '+own.length+'건'+(showCommonAcl?'\n공통 '+sharedRole.length+'건':'')),
        bodyCell(label(a.status)+'\n'+nonempty(a.text,'(설명 미작성)'))
      ];
    });
    content.push(rowsTable(['컨트롤러 / Role','SSID','단말 구분','ACL 구분','Role 설명 / 확인'],roleRows,[112,78,63,65,'*']));

    content.push(title('4. 추가 확인·변경 및 조치 대상'));
    const followups=[];
    for(const item of issues)followups.push(['수집 이슈',str(item.controllerId)+' / '+str(item.roleId),str(item.message)]);
    for(const item of changeItems)followups.push(['변경',str(item.controllerId)+' / '+str(item.roleId||item.ruleId),str(item.message)+(item.previousRaw?'\n이전 원문: '+str(item.previousRaw):'')]);
    for(const item of unresolved)followups.push(['미연결 주석',str(item.controllerName)+' / '+str(item.roleName)+' / '+str(item.acl),str(item.reason)+
      '\n메모: '+nonempty(item.annotation?.text,'(주석 없음)')+'\n출처: '+str(item.sourceProjectId)+' / '+str(item.sourceSnapshotId)]);
    for(const r of roles){
      if(['needs_review','reused'].includes(r.annotation?.status) || (r.annotation?.status==='unreviewed'&&(note(r)||r.annotation?.deviceType||r.annotation?.manualSsid))){
        followups.push(['Role 확인',roleTarget(r),label(r.annotation?.status)+' / '+nonempty(note(r),'(설명 미작성)')]);
      }
    }
    for(const r of rules){
      const text=aclNote(r);
      if(['needs_review','reused'].includes(r.annotation?.status) || (r.annotation?.status==='unreviewed'&&text)){
        followups.push(['ACL 확인',ruleTarget(r),checked(r)+(text ? ' / '+text : '')]);
      }
    }
    content.push(rowsTable(['유형','대상','근거 및 운영 메모'],followups,[67,149,'*']));

    content.push(title('5. Role별 ACL 상세 — 기술 부록'));
    content.push(para('Role별 전용 ACL의 수집 원문과 주석입니다.'));
    for(const r of roles){
      const own=exclusive.filter(rule=>related(rule,r));
      content.push({text:roleTarget(r),style:'roleHeading',margin:[0,12,0,4]});
      content.push(para('ACL 적용 순서: '+((r.aclOrder||[]).map(str).join(' → ')||'정보 없음')+
        '\nRole 원문 바인딩: '+((r.bindingRaw||[]).map(str).join('\n')||'정보 없음')));
      if(!own.length)content.push(para('이 보고 범위에서 표시할 전용 ACL 규칙이 없습니다.'));
      else content.push(aclAppendixTable(['ACL / 순서','수집 규칙 원문'],own,rule=>[
        nonempty(rule.acl,'ACL 미확인')+' #'+nonempty(rule.sequence,'?')+
          '\n발생 순번: '+nonempty(rule.ordinal,'?')+'\n규칙 ID: '+nonempty(rule.id),
        policyText(rule,aliases)
      ],[120,215,'*'],includeNotes));
    }

    if(showCommonAcl){
      content.push(title('6. 공통 ACL — 컨트롤러별 기술 부록'));
      content.push(para('공통 정책명: global-sacl / ra-guard / re-guard / logon-control. 각 발생 규칙의 컨트롤러·Role·식별자와 주석을 보존합니다. 같은 이름이라도 실제 규칙 내용이 다르면 별도 항목으로 표시합니다.'));
      const groups=new Map();
      for(const r of shared){
        const k=JSON.stringify([r.controllerId,str(r.acl).trim().toLowerCase()]);
        if(!groups.has(k))groups.set(k,[]);
        groups.get(k).push(r);
      }
      if(!groups.size)content.push(para('이 보고 범위에서 표시할 공통 ACL 규칙이 없습니다.'));
      for(const entries of groups.values()){
        const r=entries[0],c=byController.get(r.controllerId);
        content.push({text:nonempty(c?.name,r.controllerName)+' / '+nonempty(r.acl)+
          ' (발생 '+entries.length+'건)',style:'roleHeading',margin:[0,10,0,4]});
        content.push(aclAppendixTable(['Role / 적용 정보','원문 정책'],entries,rule=>[
          nonempty(rule.roleName)+'\nRole ID: '+nonempty(rule.roleId)+'\n규칙 ID: '+nonempty(rule.id),
          ['Seq '+nonempty(rule.sequence,'?')+'\n',...policyText(rule,aliases)]
        ],[112,223,'*'],includeNotes));
      }
    }
    content.push(title((showCommonAcl?'7. ':'6. ')+(aliases.appendix.length?'Alias 상세 및 자료 범위':'자료 범위')));
    appendAliasTables(content,aliases.appendix,true,
      ref=>nonempty(byController.get(ref.controllerId)?.name,ref.controllerName));
    content.push(para('관련 기록: 실제 수집본 ID '+nonempty(model.snapshotId)+
      ', 프로젝트 ID '+nonempty(model.projectId)+
      '. Excel·JSON에 저장된 원본은 PDF 작성으로 변경되지 않습니다.'));

    return {
      pageSize:'A4',pageOrientation:'portrait',pageMargins:[34,45,34,43],
      info:{title:'무선랜 Role 및 ACL 정책 점검 보고서',subject:str(model.scopeLabel),creator:'Aruba Wireless Policy Mapper'},
      defaultStyle:{font:'NanumGothic',fontSize:8.1,color:COLORS.navy,lineHeight:1.25},
      styles:{
        kicker:{fontSize:9,bold:true,color:COLORS.muted,charSpacing:1.4},
        reportTitle:{fontSize:21,bold:true,color:COLORS.navy},
        sectionHeading:{fontSize:12.5,bold:true,color:COLORS.navy},
        roleHeading:{fontSize:10,bold:true,color:COLORS.navy},
        smallText:{fontSize:8.2,color:COLORS.muted,lineHeight:1.3},
        disclaimer:{fontSize:9,bold:true,color:COLORS.alert,fillColor:'#FFF9E8',margin:[0,0,0,8]},
        tableHead:{fontSize:7.8,bold:true,color:COLORS.navy},
        tableBody:{fontSize:7.5,lineHeight:1.2}
      },
      header:(currentPage)=>({text:'ARUBA WIRELESS POLICY REVIEW  |  '+str(model.scopeLabel),
        font:'NanumGothic',fontSize:7,color:COLORS.muted,alignment:'right',margin:[34,19,34,0]}),
      footer:(currentPage,pageCount)=>({text:'프로젝트 '+nonempty(model.projectId)+'   |   '+currentPage+' / '+pageCount,
        font:'NanumGothic',fontSize:7,color:COLORS.muted,alignment:'center',margin:[34,0,34,20]}),
      content
    };
  }

  async function createPdfBytes(model,pdfMake,options) {
    if(!pdfMake || typeof pdfMake.createPdf!=='function')throw new Error('오프라인 PDF 생성 라이브러리가 없습니다. 프로그램 설치 파일을 확인해 주세요.');
    if(!pdfMake.vfs || typeof pdfMake.vfs['NanumGothic-Regular.ttf']!=='string') {
      throw new Error('PDF 한글 글꼴 데이터가 없습니다. 배포 파일을 다시 확인해 주세요.');
    }
    const family={NanumGothic:{
      normal:'NanumGothic-Regular.ttf',bold:'NanumGothic-Regular.ttf',
      italics:'NanumGothic-Regular.ttf',bolditalics:'NanumGothic-Regular.ttf'
    }};
    if(typeof pdfMake.addFonts==='function')pdfMake.addFonts(family);
    else pdfMake.fonts=Object.assign({},pdfMake.fonts||{},family);
    const doc=documentDefinition(model,options);
    return new Promise((resolve,reject)=>{
      try {
        pdfMake.createPdf(doc).getBuffer(buffer=>{
          try {
            const bytes=buffer instanceof Uint8Array?buffer:new Uint8Array(buffer);
            if(bytes.length<8 || String.fromCharCode(...bytes.slice(0,5))!=='%PDF-')throw new Error('생성된 데이터가 올바른 PDF 파일이 아닙니다.');
            resolve(bytes);
          } catch (error){reject(error);}
        });
      } catch(error){reject(error);}
    });
  }

  return Object.freeze({documentDefinition,createPdfBytes});
}));
