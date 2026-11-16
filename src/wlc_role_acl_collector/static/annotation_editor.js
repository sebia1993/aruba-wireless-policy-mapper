/* Offline annotation workspace. Project files are authoritative; storage is recovery only. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.AnnotationEditor = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const STATUS = {unreviewed:'미확인', reviewed:'확인 완료', reused:'이전 설명 재사용', needs_review:'재확인 필요'};
  const COVERAGE = {completed:'수집 완료', partial:'일부 수집', failed:'수집 실패', unknown:'수집 범위 미확인'};
  const SCRIPT_IDS = ['annotation-core-script','annotation-export-script','annotation-exceljs-script','annotation-import-script','annotation-editor-script'];
  const MAX_FILE_BYTES = 50 * 1024 * 1024;
  const clone = value => JSON.parse(JSON.stringify(value));
  const escapeHtml = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const encodedJson = value => JSON.stringify(value).replace(/[<>&\u2028\u2029]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4,'0'));

  function recoveryKey(base) {
    return 'aruba-annotation-recovery:v1:' + [base.projectId,base.snapshot.id,base.revision,base.updatedAt].map(x=>encodeURIComponent(String(x))).join(':');
  }

  function saveRecovery(storage, base, project) {
    try {
      if (!storage) throw new Error('storage unavailable');
      storage.setItem(recoveryKey(base), JSON.stringify({baseUpdatedAt:base.updatedAt, project}));
      return {ok:true};
    } catch (error) { return {ok:false,error:String(error.message || error)}; }
  }

  function readRecovery(storage, base, core) {
    try {
      if (!storage) return null;
      const text = storage.getItem(recoveryKey(base));
      if (!text || text.length > 25000000) return null;
      const envelope = JSON.parse(text);
      if (envelope.baseUpdatedAt !== base.updatedAt) return null;
      const p = core.validateProject(envelope.project);
      if (JSON.stringify(p.snapshot)!==JSON.stringify(base.snapshot)) return null;
      return p.projectId === base.projectId && p.snapshot.id === base.snapshot.id && p.revision > base.revision ? p : null;
    } catch (_error) { return null; }
  }

  function standaloneHtml(project, document) {
    // Rebuild from trusted application assets. Do not clone the original report:
    // after opening another project its old source/Access Check data is stale.
    const style = document.getElementById('annotation-editor-style')?.textContent || '';
    const license = document.getElementById('annotation-license-data')?.textContent || '';
    const scripts = SCRIPT_IDS.map(id => '<script id="'+id+'">'+(document.getElementById(id)?.textContent || '').replace(/<\/script/gi,'<\\/script')+'</script>').join('\n');
    return '<!doctype html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer"><title>무선 정책 주석 작업</title><style id="annotation-editor-style">'+style.replace(/<\/style/gi,'<\\/style')+'</style></head><body><div id="annotation-workspace"></div><script id="annotation-project-data" type="application/json">'+encodedJson(project)+'</script><script id="annotation-license-data" type="text/plain">'+license.replace(/<\/script/gi,'<\\/script')+'</script>\n'+scripts+'\n<script>AnnotationEditor.init();</script></body></html>\n';
  }

  function init(options) {
    options = options || {};
    const win = options.window || window;
    const doc = options.document || win.document;
    const core = options.core || win.AnnotationCore;
    const exporter = options.exporter || win.AnnotationExport;
    const importer = options.importer || win.AnnotationImport;
    const root = doc.getElementById('annotation-workspace');
    if (!root || !core) throw new Error('주석 작업 화면을 초기화할 수 없습니다.');
    let project;
    try { project = core.parseProject(doc.getElementById('annotation-project-data').textContent); }
    catch (error) {
      root.innerHTML = '<div class="ann-fatal"><h1>작업 데이터를 열 수 없습니다</h1><p>'+escapeHtml(error.message)+'</p><p>원본 작업 파일을 확인해 주세요.</p></div>';
      const source=doc.getElementById('source-report');if(source)source.hidden=false;
      return null;
    }
    let base = clone(project), lastDownloadRevision = project.revision;
    const originalSnapshotText=JSON.stringify(project.snapshot);
    let sourceMatches=true;
    let activeRole = project.snapshot.roles[0]?.id || '';
    let selectedRoles = new Set(activeRole ? [activeRole] : []);
    let search = '', reviewOnly = false, view = 'editor', pendingImport = null;
    let storage;
    try { storage = win.localStorage; } catch (_error) { storage = null; }
    let pendingDraft = readRecovery(storage, base, core);
    let fileMode = 'open', reviewRevision = -1, reviewRoleIds = new Set();
    const $ = id => doc.getElementById(id);
    const controller = id => project.snapshot.controllers.find(c=>c.id===id);
    const role = id => project.snapshot.roles.find(r=>r.id===id);
    const rulesOf = id => project.snapshot.rules.filter(r=>r.roleId===id);
    const emptyRecord = () => ({text:'',status:'unreviewed',updatedAt:project.updatedAt,confirmedAt:'',reasons:[],source:null});
    const record = (kind,id) => project.annotations[kind][id] || emptyRecord();
    const pending = a => a.status==='needs_review' || a.status==='reused' || (a.status==='unreviewed' && a.text!=='');
    const sourceAvailable = () => sourceMatches && $('source-report')?.dataset.sourceSnapshotId === project.snapshot.id;

    function status(message, state) {
      const el = $('ann-status');
      if (el) { el.textContent=message; el.dataset.state=state || ''; }
    }

    function metadata() {
      const target = $('ann-metadata');
      if (target) target.textContent = '수집본 생성 '+project.snapshot.collectedAt+' · 수정 '+project.updatedAt+' · 버전 '+project.revision;
      const ids = $('ann-identifiers');
      if (ids) ids.textContent='작업 '+project.projectId+' · 수집본 '+project.snapshot.id;
    }

    function syncSource() {
      if (sourceAvailable() && typeof win.syncSourceAnnotations === 'function') win.syncSourceAnnotations(project);
      if (!sourceAvailable() && $('source-report')) $('source-report').hidden=true;
    }

    function changed() {
      project.revision++;
      project.updatedAt=new Date().toISOString();
      metadata();
      syncSource();
      updateCounts();
      renderRoleList();
      if (pendingDraft) {
        status('내용을 수정했습니다. 이전 임시작업을 복구하거나 버린 뒤 브라우저 임시저장을 사용할 수 있습니다. 작업 파일 저장은 가능합니다.','pending');
      } else {
        const result=saveRecovery(storage,base,project);
        status(result.ok ? '브라우저 임시저장됨 · 파일로 보관하려면 작업 저장을 눌러 주세요.' : '브라우저 임시저장 불가 · 내용은 화면에 유지됩니다. 작업 저장으로 파일을 내려받으세요.',result.ok?'draft':'warning');
      }
    }

    function summaryCounts() {
      const notes=Object.values(project.annotations.rules);
      return {notes:notes.filter(n=>n.text!=='').length,review:notes.filter(pending).length+Object.values(project.annotations.roles).filter(pending).length,unresolved:project.unresolvedAnnotations.length};
    }

    function updateCounts() {
      const c=summaryCounts();
      if ($('ann-counts')) $('ann-counts').textContent='장비 '+project.snapshot.controllers.length+' · Role '+project.snapshot.roles.length+' · 규칙 '+project.snapshot.rules.length+' · 주석 '+c.notes+' · 주석 확인 필요 '+c.review+' · 미연결 주석 '+c.unresolved;
      if ($('ann-review-button')) $('ann-review-button').textContent=(reviewOnly?'전체 Role 보기':'변경·확인 필요 항목 보기')+' ('+reviewRoles().size+' Role)';
    }

    function noticeHtml() {
      const incomplete=project.snapshot.controllers.filter(c=>c.coverage!=='completed');
      return (incomplete.length?'<p class="ann-warning">'+escapeHtml(incomplete.map(c=>c.name+': '+COVERAGE[c.coverage]).join(' / '))+' — 보이지 않는 규칙을 삭제된 정책으로 단정하지 않습니다.</p>':'')+
        (project.snapshot.localNetworks.length?'<p class="ann-warning">내부망 대역 정보가 포함된 작업입니다. 현재 내보내기에도 포함됩니다.</p>':'');
    }

    function shell() {
      root.className='annotation-workspace';
      root.innerHTML=`
        <div class="ann-top"><div><div class="ann-kicker">WIRELESS POLICY REVIEW</div><h1>무선 정책 주석 작업</h1><p>수집한 정책에 설명을 달고, 작업 파일로 이어서 관리하세요.</p></div><div class="ann-mode"><button type="button" id="ann-editor-mode" aria-pressed="true">주석·보고서</button><button type="button" id="ann-source-mode" ${sourceAvailable()?'':'hidden'}>수집 결과·통신 확인</button></div></div>
        <div class="ann-toolbar"><div class="ann-file-actions"><button type="button" id="ann-open">작업 열기</button><button type="button" id="ann-save" class="ann-primary">작업 저장</button><button type="button" id="ann-reuse">이전 주석 가져오기</button><button type="button" id="ann-save-html">주석 포함 HTML 저장</button></div><div class="ann-export-actions"><label for="ann-export-scope">보고 범위</label><select id="ann-export-scope"><option value="all">전체 정책</option><option value="selected">선택한 Role</option><option value="review">변경·확인 필요 항목</option></select><button type="button" id="ann-pdf">PDF 저장</button><button type="button" id="ann-xlsx">Excel 저장</button></div></div>
        <input type="file" id="ann-file" accept=".json,.html,.htm,application/json,text/html" hidden>
        <div class="ann-status" id="ann-status" role="status" aria-live="polite"></div>
        <div id="ann-recovery" class="ann-recovery" ${pendingDraft?'':'hidden'}><div><strong>이 파일에서 이어서 작성한 임시작업이 있습니다.</strong><p>현재는 파일의 내용을 표시하고 있습니다. 복구하면 임시작업의 전체 주석 상태를 적용합니다.</p></div><button type="button" id="ann-restore">임시작업 복구</button><button type="button" id="ann-discard-draft">임시작업 버리기</button></div>
        <div id="ann-import-map" class="ann-import-map" hidden></div>
        <div id="ann-content"><div class="ann-overview"><div id="ann-counts" class="ann-counts"></div><div id="ann-metadata" class="ann-meta"></div><div id="ann-identifiers" class="ann-identifiers"></div></div>${noticeHtml()}
        <div class="ann-layout"><aside class="ann-sidebar" aria-label="정책 Role 선택"><label for="ann-search">Role / 장비 / SSID 검색</label><input type="search" id="ann-search" placeholder="이름으로 찾기"><button type="button" id="ann-review-button" class="ann-wide">변경·확인 필요 항목 보기</button><div class="ann-selection"><button type="button" id="ann-select-visible">목록 전체 선택</button><button type="button" id="ann-clear-selection">선택 해제</button></div><p class="ann-help">체크한 Role은 ‘선택한 Role’ 보고 범위에 포함됩니다.</p><div id="ann-role-list"></div></aside><section id="ann-role-detail" class="ann-role-detail" aria-label="정책 주석 편집"></section></div>
        <section class="ann-audit"><div class="ann-section-title"><h2>변경·확인 사항</h2><span>수집본 비교 결과와 연결되지 않은 설명</span></div><div id="ann-changes"></div><div id="ann-unresolved"></div></section></div>`;
      // Replacing innerHTML keeps root listeners; remove/re-add ensures one handler.
      root.removeEventListener('click',onClick);root.addEventListener('click',onClick);
      root.removeEventListener('input',onInput);root.addEventListener('input',onInput);
      root.removeEventListener('change',onChange);root.addEventListener('change',onChange);
      root.removeEventListener('focusin',onFocus);root.addEventListener('focusin',onFocus);
      $('ann-search').value=search;
      metadata();updateCounts();renderRoleList();renderRole();renderChanges();syncSource();
      setView(view);
      status('작업 파일의 내용을 표시하고 있습니다. 수정 후 작업 저장으로 파일을 보관하세요.','ready');
    }

    function roleNeedsReview(r) {
      return reviewRoles().has(r.id);
    }

    function reviewRoles() {
      if (reviewRevision!==project.revision) {
        reviewRoleIds=new Set(core.buildExportModel(project,{type:'review'}).roles.map(r=>r.id));
        reviewRevision=project.revision;
      }
      return reviewRoleIds;
    }

    function visibleRoles() {
      const term=search.toLocaleLowerCase();
      return project.snapshot.roles.filter(r=>(!reviewOnly || roleNeedsReview(r)) && (!term || [r.name,controller(r.controllerId)?.name,...r.ssids].join(' ').toLocaleLowerCase().includes(term)));
    }

    function renderRoleList() {
      const roles=visibleRoles();
      $('ann-role-list').innerHTML=roles.map(r=>`<div class="ann-role-item ${r.id===activeRole?'active':''}"><input type="checkbox" data-select-role="${escapeHtml(r.id)}" aria-label="${escapeHtml((controller(r.controllerId)?.name||'')+' / '+r.name)} 보고에 포함" ${selectedRoles.has(r.id)?'checked':''}><button type="button" data-open-role="${escapeHtml(r.id)}" aria-pressed="${r.id===activeRole}"><strong>${escapeHtml(r.name)}</strong><span>${escapeHtml(controller(r.controllerId)?.name||'')} · ${rulesOf(r.id).length} 규칙${roleNeedsReview(r)?' · 확인 필요':''}</span></button></div>`).join('') || '<p class="ann-empty">조건에 맞는 Role이 없습니다.</p>';
    }

    function noteEditor(kind,id,label) {
      const a=record(kind,id);
      return `<div class="ann-note"><label class="ann-sr-only" for="ann-note-${escapeHtml(id)}">${escapeHtml(label)}</label><textarea id="ann-note-${escapeHtml(id)}" data-note-kind="${kind}" data-note-id="${escapeHtml(id)}" maxlength="1000000" placeholder="정책 목적, 허용·차단 근거, 예외 또는 확인할 내용을 적으세요.">${escapeHtml(a.text)}</textarea><div class="ann-note-controls"><label>확인 상태 <select data-status-kind="${kind}" data-status-id="${escapeHtml(id)}" aria-label="${escapeHtml(label)} 확인 상태">${Object.entries(STATUS).map(([v,t])=>`<option value="${v}" ${a.status===v?'selected':''}>${t}</option>`).join('')}</select></label><button type="button" data-template-kind="${kind}" data-template-id="${escapeHtml(id)}">설명 틀 넣기</button></div><div class="ann-note-reasons">${a.reasons.map(escapeHtml).join('<br>')}${a.source?'<br>이전 작업: '+escapeHtml(a.source.projectId)+' · 이전 확인: '+escapeHtml(a.source.confirmedAt||'기록 없음'):''}</div></div>`;
    }

    function renderRole() {
      const r=role(activeRole), target=$('ann-role-detail');
      if (!r) {target.innerHTML='<div class="ann-empty"><h2>수집된 Role이 없습니다</h2><p>작업 파일을 열거나 수집 상태를 확인해 주세요. 미연결 주석은 아래에 보관됩니다.</p></div>';return;}
      const c=controller(r.controllerId), rows=rulesOf(r.id);
      const networks=project.snapshot.localNetworks.filter(n=>n.roleId===r.id);
      const aliases=project.snapshot.aliases.filter(a=>a.controllerId===r.controllerId);
      target.innerHTML=`<div class="ann-role-header"><div><div class="ann-kicker">${escapeHtml(c?.name||'')} · ${escapeHtml(c?.host||'장비 주소 미확인')}</div><h2>${escapeHtml(r.name)}</h2><p>SSID: ${escapeHtml(r.ssids.join(', ')||'연결 정보 없음')} · 관측 사용자 ${r.observedUsers}명 · ${rows.length} 규칙</p></div><span class="ann-coverage ${c?.coverage==='completed'?'':'incomplete'}">${COVERAGE[c?.coverage]||'미확인'}</span></div>
        <div class="ann-role-note"><h3>보고용 Role 설명</h3><p class="ann-help">업무 목적 · 대상 사용자 · 주요 접근 범위 · 예외 및 확인 사항을 정리하세요.</p>${noteEditor('roles',r.id,r.name+' Role 설명')}</div>
        ${networks.length?'<div class="ann-local"><strong>포함된 내부망 대역</strong><p>'+networks.map(n=>escapeHtml(n.network+' / '+n.subnetMask+' · '+n.status)).join('<br>')+'</p></div>':''}
        <div class="ann-section-title"><h3>ACL 행별 주석</h3><span>다른 ACL과 사용자 0명 Role도 작업 파일에 보관됩니다.</span></div>
        <div class="ann-table-scroll" tabindex="0" role="region" aria-label="${escapeHtml(r.name)} ACL 주석 표"><table class="ann-rules"><thead><tr><th>ACL / 순서</th><th>정책 내용</th><th>주석 · 확인 상태</th></tr></thead><tbody>${rows.map(rule=>`<tr><td><strong>${escapeHtml(rule.acl)}</strong><span class="ann-sequence">#${escapeHtml(rule.sequence)} · Role 내 ${rule.ordinal}번째</span><span class="ann-action ${rule.action==='deny'?'deny':''}">${escapeHtml(rule.action||'미확인')}</span></td><td><dl class="ann-rule-fields"><dt>출발지</dt><dd>${escapeHtml(rule.source)}</dd><dt>목적지</dt><dd>${escapeHtml(rule.destination)}</dd><dt>서비스</dt><dd>${escapeHtml(rule.service)}</dd></dl><div class="ann-raw"><strong>원문</strong><code>${escapeHtml(rule.raw)}</code></div></td><td>${noteEditor('rules',rule.id,rule.acl+' '+rule.sequence+' 주석')}</td></tr>`).join('')||'<tr><td colspan="3">이 Role에 수집된 ACL 규칙이 없습니다.</td></tr>'}</tbody></table></div>
        <details class="ann-context"><summary>Alias · ACL 연결 순서 · 수집 확인 사항</summary><h3>ACL 연결 순서</h3><p>${escapeHtml(r.aclOrder.join(' → ')||'연결 정보 없음')}</p><pre>${escapeHtml(r.bindingRaw.join('\n'))}</pre><h3>이 장비의 Alias</h3>${aliases.map(a=>'<div class="ann-alias"><strong>'+escapeHtml(a.name)+'</strong><ul>'+a.entries.map(e=>'<li>'+escapeHtml(e.type+' '+e.value)+'</li>').join('')+'</ul></div>').join('')||'<p>수집된 Alias가 없습니다.</p>'}<h3>확인 사항</h3><ul>${project.snapshot.issues.filter(i=>i.controllerId===r.controllerId&&(!i.roleId||i.roleId===r.id)).map(i=>'<li>'+escapeHtml(i.message)+'</li>').join('')||'<li>추가 수집 확인 사항이 없습니다.</li>'}</ul></details>`;
      // HTML parsing consumes an initial LF in textarea markup. The project is
      // authoritative, so assign DOM values explicitly after every render.
      for (const input of target.querySelectorAll('[data-note-id]')) input.value=record(input.dataset.noteKind,input.dataset.noteId).text;
    }

    function renderChanges() {
      $('ann-changes').innerHTML=project.changes.length?'<ul class="ann-change-list">'+project.changes.map(c=>'<li><strong>'+escapeHtml([controller(c.controllerId)?.name,role(c.roleId)?.name].filter(Boolean).join(' / '))+'</strong> '+escapeHtml(c.message)+(c.previousRaw?'<pre>'+escapeHtml(c.previousRaw)+'</pre>':'')+'</li>').join('')+'</ul>':'<p class="ann-empty">이전 작업을 가져오면 규칙과 수집 문맥의 변경 사항을 여기에 표시합니다.</p>';
      $('ann-unresolved').innerHTML=project.unresolvedAnnotations.length?'<h3>미연결 주석 '+project.unresolvedAnnotations.length+'개</h3><p class="ann-help">동일 규칙 중복, 장비 미확인 또는 변경된 규칙의 설명입니다. 대상 행을 직접 선택해 연결할 수 있습니다. 기존 주석이 있으면 이 목록에 보관합니다.</p>'+project.unresolvedAnnotations.map(u=>{
        return '<article class="ann-orphan"><h4>'+escapeHtml(u.controllerName+' / '+u.roleName+(u.acl?' / '+u.acl:''))+'</h4><p>'+escapeHtml(u.reason)+'</p><pre>'+escapeHtml(u.raw)+'</pre><blockquote>'+escapeHtml(u.annotation.text||'(빈 주석)')+'</blockquote><label>연결할 '+(u.kind==='role'?'Role':'규칙')+' <select data-link-target="'+escapeHtml(u.id)+'"><option value="">대상을 선택하세요</option></select></label><button type="button" data-link-orphan="'+escapeHtml(u.id)+'">선택한 행에 주석 연결</button><small>출처 '+escapeHtml(u.sourceProjectId)+' · '+escapeHtml(u.sourceSnapshotId)+'</small></article>';
      }).join(''):'';
    }

    function editNote(kind,id,text) {
      const old=record(kind,id);
      project.annotations[kind][id]={...old,text,status:'unreviewed',updatedAt:new Date().toISOString(),confirmedAt:''};
      changed();
      const select=Array.from(root.querySelectorAll('[data-status-id]')).find(el=>el.dataset.statusId===id);
      if (select) select.value='unreviewed';
    }

    function setView(next) {
      view=next==='source'&&sourceAvailable()?'source':'editor';
      if ($('source-report')) $('source-report').hidden=view!=='source';
      $('ann-content').hidden=view==='source';
      $('ann-editor-mode').setAttribute('aria-pressed',String(view==='editor'));
      $('ann-source-mode').setAttribute('aria-pressed',String(view==='source'));
      if (view==='source') status('현재 수집본의 원본 보고서입니다. 주석은 ‘주석·보고서’에서 편집하며 이 화면에도 반영됩니다.','ready');
    }

    function parseImport(text) {
      if (typeof text!=='string' || text.length>MAX_FILE_BYTES) throw new Error('가져올 파일이 너무 큽니다. 최대 50 MB입니다.');
      if (text.trimStart().startsWith('{')) return core.parseProject(text);
      if (!importer) throw new Error('HTML 가져오기 모듈을 찾을 수 없습니다.');
      return importer.parse(text,doc,core);
    }

    function replaceProject(next) {
      project=next;base=clone(next);lastDownloadRevision=next.revision;
      sourceMatches=JSON.stringify(next.snapshot)===originalSnapshotText;
      reviewRevision=-1;
      activeRole=next.snapshot.roles[0]?.id||'';selectedRoles=new Set(activeRole?[activeRole]:[]);
      pendingDraft=readRecovery(storage,base,core);pendingImport=null;view='editor';search='';reviewOnly=false;
      shell();
    }

    function openText(text) {
      try {
        const next=parseImport(text); // Validate completely before confirmation or mutation.
        if (project.revision!==lastDownloadRevision && !win.confirm('현재 수정한 내용은 작업 저장으로 보관할 수 있습니다. 이 작업 파일로 바꾸시겠습니까?')) return false;
        replaceProject(next);status('작업 파일을 열었습니다. 수집 데이터와 주석을 함께 복원했습니다.','ready');return true;
      } catch (error) {status('작업 열기 실패: '+error.message,'error');return false;}
    }

    function applyReuse(previous, controllerMap) {
      const result=core.reconcileProjects(project,previous,{controllerMap:controllerMap||{}});
      project=result.project;pendingImport=null;
      $('ann-import-map').hidden=true;
      syncSource();metadata();updateCounts();renderRoleList();renderRole();renderChanges();
      const recovery=pendingDraft?{ok:false}:saveRecovery(storage,base,project);
      status('이전 주석을 가져왔습니다: 재사용 '+result.summary.reused+'개, 재확인 '+result.summary.needsReview+'개, 미연결 '+result.summary.unresolved+'개. '+(recovery.ok?'브라우저 임시저장됨.':'브라우저 임시저장 불가 또는 복구 대기 중. ')+'작업 저장으로 보관하세요.','ready');
      return true;
    }

    function reuseText(text) {
      try {
        const previous=parseImport(text);
        if (previous.snapshot.controllers.some(c=>!c.identityKnown)) {
          pendingImport=previous;
          const target=$('ann-import-map');target.hidden=false;
          target.innerHTML='<h2>이전 파일의 장비를 확인해 주세요</h2><p>장비 주소가 없는 이전 HTML은 이름만으로 자동 연결하지 않습니다. 직접 선택한 장비 안에서만 주석을 찾고, 재확인 상태로 가져옵니다. 주소가 확인된 장비는 주소·포트·설정 범위가 일치하면 자동 연결합니다.</p>'+previous.snapshot.controllers.filter(c=>!c.identityKnown).map(c=>'<label>'+escapeHtml(c.name)+' → <select data-map-controller="'+escapeHtml(c.id)+'"><option value="">연결하지 않고 미연결 주석으로 보관</option>'+project.snapshot.controllers.map(t=>'<option value="'+escapeHtml(t.id)+'">'+escapeHtml(t.name+' / '+(t.host||'주소 미확인'))+'</option>').join('')+'</select></label>').join('')+'<button type="button" id="ann-confirm-import">선택한 연결로 가져오기</button><button type="button" id="ann-cancel-import">취소</button>';
          status('이전 파일의 장비 연결을 선택해 주세요. 현재 작업은 아직 변경하지 않았습니다.','pending');return true;
        }
        return applyReuse(previous);
      } catch (error) {status('주석 가져오기 실패: '+error.message,'error');return false;}
    }

    function restoreDraft() {
      if (!pendingDraft) return false;
      project=pendingDraft;pendingDraft=null;reviewRevision=-1;metadata();updateCounts();renderRoleList();renderRole();renderChanges();syncSource();
      $('ann-recovery').hidden=true;status('임시작업을 복구했습니다. 빈 주석과 확인 상태까지 복원했습니다. 작업 저장으로 파일을 보관하세요.','draft');return true;
    }

    function download(blob, name) {
      const link=doc.createElement('a'), url=win.URL.createObjectURL(blob);
      link.href=url;link.download=name;doc.body.appendChild(link);
      try {link.click();} finally {link.remove();win.setTimeout(()=>win.URL.revokeObjectURL(url),1500);}
    }

    function filename(suffix) {return 'wireless_policy_'+new Date().toISOString().replace(/[:.]/g,'-')+suffix;}

    function saveProject() {
      try {
        const validated=core.validateProject(project);
        const text=JSON.stringify(validated)+'\n';
        const blob=new win.Blob([text],{type:'application/json;charset=utf-8'});
        if(blob.size>MAX_FILE_BYTES) throw new Error('다시 열 수 있는 작업 파일 크기(50 MiB)를 초과합니다. 주석 크기를 줄여 주세요.');
        core.parseProject(text);
        download(blob,filename('.aruba-project.json'));
        lastDownloadRevision=project.revision;
        status('작업 파일 다운로드를 요청했습니다. 내려받은 파일이 다음 작업의 기준입니다.','download');return true;
      } catch (error) {status('작업 저장 실패: '+error.message+' · 현재 내용은 화면에 유지됩니다.','error');return false;}
    }

    function saveHtml() {
      try {
        const blob=new win.Blob([standaloneHtml(core.validateProject(project),doc)],{type:'text/html;charset=utf-8'});
        if(blob.size>MAX_FILE_BYTES) throw new Error('다시 열 수 있는 HTML 크기(50 MiB)를 초과합니다. 작업 JSON으로 저장하거나 주석 크기를 줄여 주세요.');
        download(blob,filename('_commented.html'));
        lastDownloadRevision=project.revision;
        status('주석 포함 HTML 다운로드를 요청했습니다. 현재 작업의 수집본과 주석을 포함합니다.','download');return true;
      } catch (error) {status('HTML 저장 실패: '+error.message,'error');return false;}
    }

    function exportModel() {
      const type=$('ann-export-scope').value;
      if (type==='selected' && selectedRoles.size===0) throw new Error('보고에 포함할 Role을 왼쪽 체크박스에서 선택해 주세요.');
      return core.buildExportModel(project,{type,roleIds:Array.from(selectedRoles)});
    }

    async function exportXlsx() {
      const button=$('ann-xlsx');
      try {
        if (!exporter || !win.ExcelJS) throw new Error('Excel 출력 모듈을 찾을 수 없습니다.');
        const model=exportModel();button.disabled=true;
        status('Excel 파일을 만드는 중입니다. 보고 범위: '+model.scopeLabel,'pending');
        const bytes=await exporter.workbookBytes(model,win.ExcelJS);
        download(new win.Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}),filename('_annotated.xlsx'));
        status('Excel 다운로드를 요청했습니다. '+model.scopeLabel+' · Role '+model.roles.length+'개 · 규칙 '+model.rules.length+'개 · 작업 버전 '+model.revision,'download');return true;
      } catch (error) {status('Excel 저장 실패: '+error.message,'error');return false;}
      finally {button.disabled=false;}
    }

    function printPdf() {
      try {
        if (!exporter) throw new Error('PDF 출력 모듈을 찾을 수 없습니다.');
        const model=exportModel(), html=exporter.printHtml(model);
        const target=win.open('','_blank');
        if (!target) throw new Error('인쇄 창이 차단되었습니다. 이 파일의 팝업을 허용하고 다시 눌러 주세요.');
        target.opener=null;
        target.document.open();target.document.write(html);target.document.close();
        const print=()=>{if (!target.closed) {target.focus();target.print();}};
        const ready=target.document.fonts?.ready || Promise.resolve();
        ready.then(()=>target.setTimeout(print,100));
        target.addEventListener('afterprint',()=>{status('인쇄 창에서 PDF 저장 또는 취소를 마쳤습니다. 저장 여부는 브라우저에서 확인해 주세요.','ready');},{once:true});
        status('인쇄 창을 열었습니다. 대상을 PDF로 저장으로 선택하세요. 보고 범위: '+model.scopeLabel,'ready');return true;
      } catch (error) {status('PDF 출력 실패: '+error.message,'error');return false;}
    }

    function linkOrphan(id) {
      const u=project.unresolvedAnnotations.find(x=>x.id===id);
      const select=Array.from(root.querySelectorAll('[data-link-target]')).find(x=>x.dataset.linkTarget===id);
      if (!u || !select?.value) {status('주석을 연결할 대상을 먼저 선택해 주세요.','warning');return;}
      const kind=u.kind==='role'?'roles':'rules';
      const target=(kind==='roles'?project.snapshot.roles:project.snapshot.rules).find(x=>x.id===select.value);
      if (!target) return;
      const old=project.annotations[kind][target.id];
      if (old) {
        const r=kind==='roles'?target:role(target.roleId);
        project.unresolvedAnnotations.push({id:'manual-conflict:'+project.revision+':'+target.id,kind:u.kind,controllerId:target.controllerId,controllerName:controller(target.controllerId)?.name||'',roleName:r.name,acl:target.acl||'',raw:target.raw||'',annotation:clone(old),reason:'다른 주석을 연결하면서 기존 설명을 보관했습니다.',candidateIds:[target.id],sourceProjectId:project.projectId,sourceSnapshotId:project.snapshot.id});
      }
      project.annotations[kind][target.id]={...clone(u.annotation),status:'needs_review',updatedAt:new Date().toISOString(),confirmedAt:'',reasons:[...u.annotation.reasons,'사용자가 연결한 설명입니다. 현재 정책의 적용 여부를 확인해 주세요.'],source:u.annotation.source||{projectId:u.sourceProjectId,snapshotId:u.sourceSnapshotId,recordId:u.id,confirmedAt:u.annotation.confirmedAt}};
      project.unresolvedAnnotations=project.unresolvedAnnotations.filter(x=>x.id!==id);
      project.changes.push({type:'manual_link',controllerId:target.controllerId,roleId:kind==='roles'?target.id:target.roleId,ruleId:kind==='rules'?target.id:'',message:'이전 설명을 사용자가 직접 연결했습니다. 현재 정책과 비교가 필요합니다.',previousRaw:u.raw});
      changed();renderRoleList();renderRole();renderChanges();
    }

    function insertTemplate(kind,id) {
      const current=record(kind,id);
      if (current.text) {status('이미 작성한 주석이 있습니다. 기존 내용을 유지했습니다.','warning');return;}
      const text=kind==='roles'?'업무 목적: \n대상 사용자: \n주요 접근 범위: \n예외 / 확인 사항: ':'정책 목적: \n허용·차단 근거: \n예외 / 확인 사항: ';
      editNote(kind,id,text);renderRole();
      const input=Array.from(root.querySelectorAll('[data-note-id]')).find(x=>x.dataset.noteId===id);input?.focus();
    }

    function onInput(event) {
      const el=event.target;
      if (el.id==='ann-search') {search=el.value;renderRoleList();return;}
      if (el.dataset.noteId) editNote(el.dataset.noteKind,el.dataset.noteId,el.value);
    }

    function onFocus(event) {
      const select=event.target;
      if (!select.dataset.linkTarget || select.dataset.choicesLoaded) return;
      const u=project.unresolvedAnnotations.find(x=>x.id===select.dataset.linkTarget);
      if (!u) return;
      // One live target list instead of unresolved-count × rule-count options.
      for (const other of root.querySelectorAll('[data-link-target]')) {
        if (other===select || !other.dataset.choicesLoaded) continue;
        const chosen=other.selectedOptions[0], value=other.value;
        other.innerHTML='<option value="">대상을 선택하세요</option>'+(value?'<option selected value="'+escapeHtml(value)+'">'+escapeHtml(chosen.textContent)+'</option>':'');
        delete other.dataset.choicesLoaded;
      }
      const value=select.value;
      const candidates=u.kind==='role'?project.snapshot.roles:project.snapshot.rules;
      select.innerHTML='<option value="">대상을 선택하세요</option>'+candidates.map(item=>{
        const r=u.kind==='role'?item:role(item.roleId);
        return '<option value="'+escapeHtml(item.id)+'">'+escapeHtml((controller(item.controllerId)?.name||'')+' / '+r.name+(u.kind==='rule'?' / '+item.acl+' #'+item.sequence+' '+item.raw:''))+'</option>';
      }).join('');
      select.value=value;select.dataset.choicesLoaded='true';
    }

    function onChange(event) {
      const el=event.target;
      if (el.dataset.selectRole) {if(el.checked)selectedRoles.add(el.dataset.selectRole);else selectedRoles.delete(el.dataset.selectRole);return;}
      if (el.dataset.statusId) {
        const kind=el.dataset.statusKind,id=el.dataset.statusId,old=record(kind,id),now=new Date().toISOString();
        project.annotations[kind][id]={...old,status:el.value,updatedAt:now,confirmedAt:el.value==='reviewed'?now:''};
        changed();renderRoleList();return;
      }
      if (el.id==='ann-file') {
        const file=el.files?.[0];
        if (!file) return;
        if (file.size>MAX_FILE_BYTES) {status('파일을 열 수 없습니다. 최대 50 MB까지 가져올 수 있습니다.','error');el.value='';return;}
        const mode=fileMode;
        file.text().then(text=>mode==='open'?openText(text):reuseText(text)).catch(error=>status('파일 읽기 실패: '+error.message,'error')).finally(()=>{el.value='';});
      }
    }

    function onClick(event) {
      const el=event.target.closest('button');
      if (!el || !root.contains(el)) return;
      if (el.dataset.openRole) {activeRole=el.dataset.openRole;renderRoleList();renderRole();return;}
      if (el.dataset.templateId) {insertTemplate(el.dataset.templateKind,el.dataset.templateId);return;}
      if (el.dataset.linkOrphan) {linkOrphan(el.dataset.linkOrphan);return;}
      switch(el.id) {
        case 'ann-open':fileMode='open';$('ann-file').click();break;
        case 'ann-reuse':fileMode='reuse';$('ann-file').click();break;
        case 'ann-save':saveProject();break;
        case 'ann-save-html':saveHtml();break;
        case 'ann-pdf':printPdf();break;
        case 'ann-xlsx':exportXlsx();break;
        case 'ann-editor-mode':setView('editor');break;
        case 'ann-source-mode':setView('source');break;
        case 'ann-select-visible':visibleRoles().forEach(r=>selectedRoles.add(r.id));renderRoleList();break;
        case 'ann-clear-selection':selectedRoles.clear();renderRoleList();break;
        case 'ann-review-button':reviewOnly=!reviewOnly;updateCounts();renderRoleList();renderChanges();break;
        case 'ann-restore':restoreDraft();break;
        case 'ann-discard-draft':
          pendingDraft=null;try {storage?.removeItem(recoveryKey(base));}catch(_error){}
          $('ann-recovery').hidden=true;status('이전 임시작업을 버렸습니다. 현재 화면의 내용은 유지됩니다.','ready');break;
        case 'ann-confirm-import':
          try {const map={};for(const select of root.querySelectorAll('[data-map-controller]'))if(select.value)map[select.dataset.mapController]=select.value;if(pendingImport)applyReuse(pendingImport,map);}catch(error){status('주석 가져오기 실패: '+error.message,'error');}break;
        case 'ann-cancel-import':pendingImport=null;$('ann-import-map').hidden=true;status('주석 가져오기를 취소했습니다.','ready');break;
      }
    }

    shell();
    win.addEventListener('beforeunload',event=>{
      if(project.revision!==lastDownloadRevision){event.preventDefault();event.returnValue='';}
    });
    const api={getProject:()=>clone(project),openText,reuseText,restoreDraft,saveProject,saveHtml,printPdf,exportXlsx,exportModel};
    win.AnnotationEditorApp=api;
    return api;
  }

  return {init,recoveryKey,saveRecovery,readRecovery,standaloneHtml,escapeHtml};
}));
