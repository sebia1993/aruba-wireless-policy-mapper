/* Offline policy reporting. Receives AnnotationCore's explicit, DOM-independent export model. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./annotation_core.js'));
  else root.AnnotationExport = factory(root.AnnotationCore);
}(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  var LIMIT = 32767;
  function str(value) { return value === null || value === undefined ? '' : String(value); }
  function hasNoteText(value) { return str(value).trim().length > 0; }
  function list(values) { return (values || []).map(str).join('\n'); }
  function record(value) { return value || {}; }
  // Preserve legacy PC unchanged and expand the two new codes for human reports.
  function deviceLabel(value) {
    var labels = {windows_pc:'윈도우 PC', macbook:'맥북'};
    return Object.prototype.hasOwnProperty.call(labels, value) ? labels[value] : str(value);
  }
  function json(value) { return value === null || value === undefined ? '' : JSON.stringify(value); }
  function annotationColumns(annotation) {
    var a = record(annotation), s = record(a.source);
    return [a.text, a.status, a.updatedAt, a.confirmedAt, list(a.reasons), s.projectId, s.snapshotId, s.recordId, s.confirmedAt];
  }
  var annotationHeaders = ['주석', '확인 상태', '주석 수정 시각', '확인 시각', '검토 사유', '원본 프로젝트 ID', '원본 스냅샷 ID', '원본 주석 ID', '원본 확인 시각'];
  const addressColumns = [
    {header:'출발지', read:rule => rule.source},
    {header:'목적지', read:rule => rule.destination}
  ];
  function excelAddressColumns(model) {
    const lookup = core.createAliasLookup(model.aliases || []);
    return addressColumns.flatMap(column => {
      const aliasFor = rule => lookup(rule.controllerId, column.read(rule));
      if (!(model.rules || []).some(aliasFor)) return [column];
      return [column, {
        header:column.header + ' Alias 요약',
        read:rule => aliasFor(rule)?.summary || ''
      }];
    });
  }
  function datasets(m, addresses = addressColumns) {
    var c = m.controllers || [], roles = m.roles || [], rules = m.rules || [], aliases = m.aliases || [];
    var summary = [
      ['보고서', '프로젝트 ID', m.projectId], ['보고서', '스냅샷 ID', m.snapshotId], ['보고서', '리비전', m.revision],
      ['보고서', '수집본 생성 시각', m.collectedAt], ['보고서', '프로젝트 수정 시각', m.updatedAt], ['보고서', '내보내기 시각', m.exportedAt],
      ['보고서', '내보내기 범위', m.scopeLabel], ['안내', '확인 상태', 'reviewed=확인됨; unreviewed=미확인; reused=이전 주석 재사용; needs_review=재검토 필요'],
      ['안내', '수집 완전성', 'completed=완료; partial=일부 수집; failed=실패; unknown=알 수 없음. 불완전한 수집에서 항목 부재는 삭제 증거가 아닙니다.'],
      ['안내', '연속 행', 'Excel 셀 한도(UTF-16 32767자)를 넘으면 같은 레코드 번호의 조각 순서대로 각 열을 이어 붙이세요. 빈 셀은 빈 문자열입니다.'],
      ['안내', '보고서 수치', m.showCommonAcl === false ? '선택한 보고 범위에서 공통 ACL을 제외하고 집계했습니다.' : '선택한 보고 범위에서 공통 ACL을 포함해 집계했습니다.'],
      ['안내', 'Alias 범위', '보고서에 표시한 규칙의 출발지 또는 목적지가 참조하는 장비별 Alias 정의를 포함합니다.']
    ];
    var labels = {controllerCount:'컨트롤러 수',roleCount:'Role 수',ruleCount:'규칙 수',annotatedRuleCount:'주석 있는 규칙 수',needsReviewCount:'재검토 필요 주석 수 (미연결 포함)'};
    Object.keys(labels).forEach(function (key) { summary.push(['범위 집계', labels[key], record(m.summary)[key]]); });
    c.forEach(function (x) {
      summary.push(['컨트롤러', x.id, '이름: ' + str(x.name) + '\n호스트: ' + str(x.host) + '\n포트: ' + str(x.port) + '\n구성 범위: ' + str(x.scope) + '\n식별 확인: ' + str(x.identityKnown) + '\n수집 상태: ' + str(x.coverage) + '\n실패 명령:\n' + list(x.failedCommands)]);
    });
    (m.issues || []).forEach(function (x) { summary.push(['수집 이슈', str(x.controllerId) + ' / ' + str(x.roleId), x.message]); });
    (m.localNetworks || []).forEach(function (x) { summary.push(['포함된 로컬 네트워크', str(x.controllerId) + ' / ' + str(x.roleId), '네트워크: ' + str(x.network) + '\n서브넷 마스크: ' + str(x.subnetMask) + '\n상태: ' + str(x.status) + '\n메모: ' + str(x.notes)]); });
    var changes = (m.changes || []).map(function (x) {
      var controller=c.find(function(item){return item.id===x.controllerId;}), role=roles.find(function(item){return item.id===x.roleId;}), rule=rules.find(function(item){return item.id===x.ruleId;});
      return ['변경', '', x.type, x.controllerId, controller?controller.name:'', x.roleId, role?role.name:'', x.ruleId, rule?rule.acl:'', rule?rule.raw:'', x.message, x.previousRaw, '', '', '', '', '', '', '', '', '', '', '', ''];
    });
    (m.unresolvedAnnotations || []).forEach(function (x) {
      changes.push(['미연결 주석', x.id, x.kind, x.controllerId, x.controllerName, '', x.roleName, '', x.acl, x.raw, x.reason+(x.kind==='role'&&x.annotation.manualSsid?'\n직접 입력 SSID: '+x.annotation.manualSsid:'')+(x.kind==='role'&&x.annotation.deviceType?'\n단말: '+deviceLabel(x.annotation.deviceType):''), '', list(x.candidateIds), x.sourceProjectId, x.sourceSnapshotId].concat(annotationColumns(x.annotation)));
    });
    // Review rows retain the exact occurrence IDs alongside changes and unmatched notes.
    roles.concat(rules).forEach(function (x) {
      var a = record(x.annotation);
      if (a.status === 'needs_review' || a.status === 'reused' || (a.status === 'unreviewed' && (hasNoteText(a.text)||str(a.manualSsid)||str(a.deviceType)))) {
        var isRule = Object.prototype.hasOwnProperty.call(x, 'roleId');
        changes.push(['확인 필요', x.id, isRule ? 'rule' : 'role', x.controllerId, x.controllerName, isRule ? x.roleId : x.id, isRule ? x.roleName : x.name, isRule ? x.id : '', x.acl, x.raw, list(a.reasons), '', '', '', ''].concat(annotationColumns(a)));
      }
    });
    return [
      {name:'보고 요약', headers:['분류', '항목 / 식별자', '내용'], rows:summary},
      {name:'Role 설명', headers:['Role ID','컨트롤러 ID','컨트롤러','Role','수집 SSID','Role 유형','ACL 바인딩 순서','원문 바인딩','문맥 수집 완료','관측 사용자 수','SSID 명 (직접 입력)','단말 구분'].concat(annotationHeaders), rows:roles.map(function (x) { return [x.id,x.controllerId,x.controllerName,x.name,list(x.ssids),list(x.roleTypes),list(x.aclOrder),list(x.bindingRaw),x.contextComplete,x.observedUsers,str(record(x.annotation).manualSsid),deviceLabel(record(x.annotation).deviceType)].concat(annotationColumns(x.annotation)); })},
      {name:'ACL 상세',
        headers:['규칙 ID','컨트롤러 ID','컨트롤러','Role ID','Role','ACL','시퀀스','발생 순번','원문 규칙']
          .concat(addresses.map(column => column.header), ['서비스','동작','출발지 해석','목적지 해석'], annotationHeaders),
        rows:rules.map(x => [x.id,x.controllerId,x.controllerName,x.roleId,x.roleName,x.acl,x.sequence,x.ordinal,x.raw]
          .concat(addresses.map(column => column.read(x)), [x.service,x.action,json(x.sourceInterpretation),json(x.destinationInterpretation)], annotationColumns(x.annotation)))},
      {name:'변경·확인 사항', headers:['구분','레코드 ID','유형','컨트롤러 ID','컨트롤러','Role ID','Role','규칙 ID','ACL','원문 규칙','사유 / 변경 내용','이전 규칙','후보 ID','가져온 프로젝트 ID','가져온 스냅샷 ID'].concat(annotationHeaders), rows:changes},
      {name:'Alias 상세', headers:['Alias ID','컨트롤러 ID','컨트롤러','Alias','항목 순번','유형','값','원문'], rows:aliases.flatMap(function (x) {
        var controller = c.find(function (item) { return item.id === x.controllerId; });
        var entries = x.entries && x.entries.length ? x.entries : [{}];
        return entries.map(function (entry, i) { return [x.id,x.controllerId,controller ? controller.name : '',x.name,x.entries && x.entries.length ? i + 1 : '',entry.type,entry.value,entry.raw]; });
      })}
    ];
  }
  function chunks(value) {
    var text = str(value), result = [], start = 0;
    do {
      var end = Math.min(start + LIMIT, text.length);
      if (end < text.length && /[\uD800-\uDBFF]/.test(text.charAt(end - 1)) && /[\uDC00-\uDFFF]/.test(text.charAt(end))) end--;
      result.push(text.slice(start, end)); start = end;
    } while (start < text.length);
    return result;
  }


  function compactControllerLabel(rule, byId, counts) {
    var controller=byId.get(rule.controllerId);
    var name=str(rule.controllerName || (controller && controller.name));
    if((counts.get(name)||0)<2) return name;
    var endpoint=controller && controller.host
      ? controller.host+(controller.port?':'+controller.port:'')
      : 'ID '+str(rule.controllerId);
    return name+' ('+endpoint+')';
  }

  // Compact is a presentation-only projection: source snapshots, rule IDs,
  // duplicate occurrences and annotation records remain untouched.
  function createCompactWorkbook(model, ExcelJS) {
    if (!ExcelJS || typeof ExcelJS.Workbook !== 'function') throw new Error('로컬 ExcelJS 번들이 필요합니다.');
    var book = new ExcelJS.Workbook();
    book.creator = 'Aruba Wireless Policy Mapper';
    book.subject = 'Compact ACL annotation report';
    book.title = 'ACL 규칙 간단 보고서';
    var byId=new Map((model.controllers||[]).map(function(c){return [c.id,c];}));
    var counts=new Map();
    (model.controllers||[]).forEach(function(c){var n=str(c.name);counts.set(n,(counts.get(n)||0)+1);});
    var sheet = book.addWorksheet('ACL 간단 보고', {
      views:[{state:'frozen',ySplit:1}],
      pageSetup:{paperSize:9,orientation:'landscape',fitToPage:true,fitToWidth:1,fitToHeight:0}
    });
    var rules = model.rules || [];
    var includeNotes = rules.some(function(rule){return hasNoteText(record(rule.annotation).text);});
    const addresses = excelAddressColumns(model);
    var headers = ['컨트롤러','Role','ACL','순서'].concat(addresses.map(column => column.header), ['서비스','동작']);
    var widths = [24,26,26,12].concat(addresses.map(() => 30), [24,14]);
    var noteIndex = headers.length;
    if (includeNotes) {
      headers.push('행별 주석');
      widths.push(65);
    }
    // Keep the continuation fields immediately after the visible report columns.
    sheet.columns = widths.map(function(width){return {width:width};})
      .concat([{width:12,hidden:true},{width:14,hidden:true}]);
    sheet.addRow(headers.concat(['_레코드 번호','_조각 / 전체']));
    rules.forEach(function(rule,index){
      var values=[compactControllerLabel(rule,byId,counts),rule.roleName,rule.acl,rule.sequence || rule.ordinal]
        .concat(addresses.map(column => column.read(rule)), [rule.service,rule.action]);
      if (includeNotes) values.push(record(rule.annotation).text);
      var parts=values.map(chunks), count=Math.max.apply(null,parts.map(function(p){return p.length;}));
      for(var i=0;i<count;i++){
        var visible=parts.map(function(p,j){
          return p[i] || (i>0 && j!==noteIndex && p.length===1 ? p[0] : '');
        });
        var row=sheet.addRow(visible.concat([str(index+1),str(i+1)+'/'+str(count)]));
        row.eachCell({includeEmpty:true},function(cell){
          // Never turn operator-entered notes into Excel formulas or hyperlinks.
          cell.numFmt='@';
          cell.alignment={vertical:'top',wrapText:true};
          cell.font={name:'맑은 고딕',size:10,color:{argb:'FF172B4D'}};
          cell.fill={type:'pattern',pattern:'solid',fgColor:{argb:index%2?'FFF0F5FA':'FFFFFFFF'}};
          cell.border={bottom:{style:'hair',color:{argb:'FFD7E0EA'}}};
        });
        row.height=Math.min(175,Math.max(28,15*Math.max.apply(null,visible.map(function(v){
          return Math.ceil(str(v).length/50)+str(v).split('\n').length;
        }))));
      }
    });
    var header=sheet.getRow(1);
    header.height=32;
    header.font={name:'맑은 고딕',size:11,bold:true,color:{argb:'FFFFFFFF'}};
    header.alignment={vertical:'middle',wrapText:true};
    header.eachCell(function(cell){cell.fill={type:'pattern',pattern:'solid',fgColor:{argb:'FF173D64'}};});
    sheet.autoFilter={from:{row:1,column:1},to:{row:Math.max(1,sheet.rowCount),column:headers.length}};
    sheet.pageSetup.printTitlesRow='1:1';
    sheet.headerFooter.oddFooter='&LACL 간단 보고&R&P / &N';
    return book;
  }
  function createWorkbook(model, ExcelJS, options) {
    if (options && options.profile === 'simple') return createCompactWorkbook(model, ExcelJS);
    if (!ExcelJS || typeof ExcelJS.Workbook !== 'function') throw new Error('로컬 ExcelJS 번들이 필요합니다.');
    var book = new ExcelJS.Workbook();
    book.creator = 'Aruba Wireless Policy Mapper';
    book.subject = 'Offline annotation report';
    book.title = '무선 정책 주석 보고서';
    datasets(model, excelAddressColumns(model)).forEach(function (data) {
      // These freshly built rows are private to this workbook. The print layout uses the full dataset.
      var noteIndex = data.headers.indexOf('주석');
      if (noteIndex >= 0 && !data.rows.some(function(row){return hasNoteText(row[noteIndex]);})) {
        data.headers.splice(noteIndex, 1);
        data.rows.forEach(function(row){row.splice(noteIndex, 1);});
      }
      var sheet = book.addWorksheet(data.name, {views:[{state:'frozen',ySplit:1}],pageSetup:{paperSize:9,orientation:'landscape',fitToPage:true,fitToWidth:1,fitToHeight:0}});
      sheet.columns = [{width:12},{width:12}].concat(data.headers.map(function (h) { return {width:/주석$|내용|원문|규칙$|사유/.test(h) ? 54 : /시각|ID/.test(h) ? 28 : 24}; }));
      sheet.addRow(['레코드 번호','조각 / 전체'].concat(data.headers));
      data.rows.forEach(function (values, index) {
        var parts = values.map(chunks), count = Math.max.apply(null, parts.map(function (p) { return p.length; }));
        for (var i = 0; i < count; i++) {
          var row = sheet.addRow([str(index + 1), str(i + 1) + '/' + str(count)].concat(parts.map(function (p) { return p[i] || ''; })));
          row.eachCell({includeEmpty:true}, function (cell) {
            // Strings, including '=...', remain literal string cells (no formulas or hyperlinks).
            cell.numFmt = '@'; cell.alignment = {vertical:'top',wrapText:true};
            cell.font = {name:'맑은 고딕',size:10,color:{argb:'FF172B4D'}};
            cell.fill = {type:'pattern',pattern:'solid',fgColor:{argb:index % 2 ? 'FFF0F5FA' : 'FFFFFFFF'}};
            cell.border = {bottom:{style:'hair',color:{argb:'FFD7E0EA'}}};
          });
          row.height = Math.min(180, Math.max(32, 15 * Math.max.apply(null, values.map(function (v) { return Math.ceil(str(v).length / 45) + str(v).split('\n').length; }))));
        }
      });
      var header = sheet.getRow(1);
      header.height = 32; header.font = {name:'맑은 고딕',size:11,bold:true,color:{argb:'FFFFFFFF'}};
      header.alignment = {vertical:'middle',wrapText:true};
      header.eachCell(function (cell) { cell.fill = {type:'pattern',pattern:'solid',fgColor:{argb:'FF173D64'}}; });
      sheet.autoFilter = {from:{row:1,column:1},to:{row:Math.max(1,sheet.rowCount),column:data.headers.length + 2}};
      sheet.pageSetup.printTitlesRow = '1:1';
      sheet.headerFooter.oddFooter = '&L' + data.name + '&R&P / &N';
    });
    return book;
  }
  async function workbookBytes(model, ExcelJS, options) {
    var bytes = await createWorkbook(model, ExcelJS, options).xlsx.writeBuffer();
    return bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  }
  function escape(value) { return str(value).replace(/[&<>"']/g, function (char) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]; }); }
  function printHtml(model) {
    var tables = datasets(model);
    var controllers = new Map((model.controllers || []).map(function (c) { return [c.id, c]; }));
    function table(headers, rows) {
      return '<table><thead><tr>' + headers.map(function (v) { return '<th scope="col">' + escape(v) + '</th>'; }).join('') + '</tr></thead><tbody>' + (rows.length ? rows.map(function (row) { return '<tr>' + row.map(function (v) { return '<td>' + escape(v) + '</td>'; }).join('') + '</tr>'; }).join('') : '<tr><td colspan="' + headers.length + '">이 범위에 해당 항목이 없습니다.</td></tr>') + '</tbody></table>';
    }
    function controllerContext(id) {
      var controller = controllers.get(id);
      var lines = ['컨트롤러 ID: ' + (str(id) || '미확인')];
      if (controller) {
        lines.push('장비 주소: ' + (str(controller.host) || '미확인'));
        lines.push('접속 포트: ' + (controller.port ? str(controller.port) : '미확인'));
        lines.push('설정 범위: ' + (str(controller.scope) || '미확인'));
      }
      return lines.join('\n');
    }
    function grouped(data, groups, controllerColumn) {
      return table(groups.map(function (g) { return g[0]; }),data.rows.map(function (row) {
        return groups.map(function (g, index) {
          var content = g.slice(1).map(function (i) { return data.headers[i] + ': ' + str(row[i]); }).join('\n');
          // Display names can repeat. Keep the endpoint and stable identities
          // beside each note, including when a detail table spans PDF pages.
          return index === 0 ? content + '\n' + controllerContext(row[controllerColumn]) : content;
        });
      }));
    }
    var sections = '<section><h2>보고 요약</h2>' + table(tables[0].headers,tables[0].rows) + '</section>';
    sections += '<section><h2>Role 설명</h2>' + grouped(tables[1],[['장비 / Role',2,3,0],['직접 입력 SSID / 단말',10,11],['수집 연결 정보',4,5,6,7,8,9],['보고용 설명',12],['확인 / 이력',13,14,15,16,20]],1) + '</section>';
    sections += '<section><h2>ACL 상세</h2>' + grouped(tables[2],[['장비 / Role / ACL',2,4,5,6,7,3,0],['규칙',8,9,10,11,12,13,14],['주석',15],['확인 / 이력',16,17,18,19,23]],1) + '</section>';
    sections += '<section><h2>변경·확인 사항</h2>' + grouped(tables[3],[['구분 / 대상',0,1,2,4,6,8,5,7],['변경 / 미연결 정보',9,10,11,13,14],['주석',15],['확인 / 이력',16,17,18,19,23]],3) + '</section>';
    sections += '<section><h2>Alias 상세</h2>' + grouped(tables[4],[['장비 / Alias',2,3,0],['항목',4,5,6,7]],1) + '</section>';
    return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>무선 정책 주석 보고서</title><style>' +
      '*{box-sizing:border-box}body{margin:24px;color:#172b4d;font:12px/1.55 "Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif}h1{font-size:25px;color:#173d64;margin-bottom:6px}h2{font-size:17px;margin:22px 0 8px}p{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;table-layout:fixed;margin-bottom:18px}th,td{border:1px solid #bdcddd;padding:7px;text-align:left;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}th{background:#e4edf5;font-weight:700}thead{display:table-header-group}tr{break-inside:auto}section{break-before:page}section:first-of-type{break-before:auto}h2{break-after:avoid}tbody tr:nth-child(even){background:#f5f8fb}@page{size:A4 landscape;margin:12mm}@media print{body{margin:0;font-size:11px}h1{font-size:20px}th,td{padding:5px}thead{display:table-header-group}h1,h2{break-after:avoid}table{break-inside:auto}p{orphans:3;widows:3}}' +
      '</style></head><body><h1>무선 정책 주석 보고서</h1><p>범위: ' + escape(model.scopeLabel) + '\n내보내기: ' + escape(model.exportedAt) + '\n프로젝트: ' + escape(model.projectId) + ' / 스냅샷: ' + escape(model.snapshotId) + ' / 리비전: ' + escape(model.revision) + '</p>' + sections + '</body></html>';
  }
  return {createWorkbook:createWorkbook,workbookBytes:workbookBytes,printHtml:printHtml};
}));
