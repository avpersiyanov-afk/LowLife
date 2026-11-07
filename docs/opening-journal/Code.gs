/* LowLife opening journal. Bound Apps Script; V8 runtime.
 * Group tokens authorize a role across projects; project/model identity stays in every record. No admin HTTP endpoint.
 * Only the sheet owner/admin edits settings and issues/revokes credentials.
 */
const LL = {
  parts: 'Части объектов', ledger: 'Публикации', blobs: 'Снимки JSON',
  gip: 'ГИП', overview: 'Обзор', tasks: 'Задания', replies: 'Ответы КР АР', working: 'Контроль в Revit', history: 'История',
  maxPayload: 1500000, chunk: 40000
};

function fail_(code) { throw new Error(code); }
function props_() { return PropertiesService.getScriptProperties(); }
function sha_(s) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,s,Utilities.Charset.UTF_8)
    .map(b => ('0'+((b+256)%256).toString(16)).slice(-2)).join('');
}
function admin_() {
  const email=Session.getActiveUser().getEmail();
  if (!email || email!==props_().getProperty('ADMIN_EMAIL')) fail_('ADMIN_ONLY');
}
function setupJournal() {
  const email=Session.getActiveUser().getEmail();
  if (!email || email!==Session.getEffectiveUser().getEmail()) fail_('ADMIN_ONLY');
  if (props_().getProperty('ADMIN_EMAIL')) admin_();
  const ss=SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) fail_('USE_BOUND_SCRIPT');
  props_().setProperties({ADMIN_EMAIL:email,SPREADSHEET_ID:ss.getId()});
  const lock=LockService.getScriptLock();lock.waitLock(10000);
  try { init_(ss);rebuild_(ss); } finally { lock.releaseLock(); }
  onOpen();
}
function onOpen() {
  if (Session.getActiveUser().getEmail()!==props_().getProperty('ADMIN_EMAIL')) return;
  SpreadsheetApp.getUi().createMenu('LowLife')
    .addItem('Выдать токен отдела','issueDepartmentToken')
    .addItem('Отозвать токен','revokeModelToken')
    .addItem('Восстановить представления журнала','rebuildJournal').addToUi();
}
function prompt_(title) {
  const ui=SpreadsheetApp.getUi(),r=ui.prompt(title,ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton()!==ui.Button.OK) fail_('CANCELLED');
  const value=r.getResponseText().trim();
  if (!value || value.length>250) fail_('INVALID_INPUT');
  return value;
}
function disciplineCode_(value) {
  const code=String(value || '').trim().toUpperCase();
  return ['ОВИК','ОК'].includes(code) ? 'ОВиК' : code;
}
function departmentRole_(department) {
  return {'ОВиК':'VIS','ВК':'VIS','ЭОМ':'VIS','СС':'VIS','АК':'VIS','КР':'KR','АР':'AR'}[department];
}
function issueDepartmentToken() {
  admin_();
  const department=disciplineCode_(prompt_('Отдел: ОВиК, ВК, ЭОМ, СС, АК, КР или АР'));
  const role=departmentRole_(department);
  if (!role) fail_('INVALID_ROLE');
  const group=department,discipline=department;
  const token=Utilities.getUuid()+Utilities.getUuid();
  const id=sha_(token);
  props_().setProperty('TOKEN_'+id,JSON.stringify({department,group,role,discipline}));
  // The raw token is shown once; only its digest remains on the server.
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  SpreadsheetApp.getUi().showModalDialog(HtmlService.createHtmlOutput(
    '<p>Скопируйте токен и передайте сотрудникам отдела отдельно. Он показан один раз.</p>'+
    '<textarea readonly style="width:95%;height:70px">'+esc(token)+'</textarea>'+
    '<p>ID для отзыва: <code>'+id+'</code></p>'),'Токен отдела '+department);
}
function issueGroupToken() { return issueDepartmentToken(); }
function issueModelToken() { return issueDepartmentToken(); }
function revokeModelToken() {
  admin_();
  const id=prompt_('Полный ID токена (SHA-256)');
  if (!/^[a-f0-9]{64}$/.test(id)) fail_('INVALID_TOKEN_ID');
  props_().deleteProperty('TOKEN_'+id);
}
function book_() {
  const id=props_().getProperty('SPREADSHEET_ID');
  if (!id) fail_('NOT_INITIALIZED');
  return SpreadsheetApp.openById(id);
}
function sheet_(ss,name,headers) {
  let sh=ss.getSheetByName(name);
  if (!sh) sh=ss.insertSheet(name);
  if (!sh.getLastRow()) {
    sh.getRange(1,1,1,headers.length).setValues([headers]);
    sh.setFrozenRows(1);
  }
  return sh;
}
function init_(ss) {
  sheet_(ss,LL.parts,['Шифр объекта','Часть (НЧ/ПЧ)','Корпус/секция','Использовать']);
  const headers=['Время сервера UTC','Проект','Роль','ID модели','Версия публикации','SHA256','Снимок','Частей','Отдел','Пользователь Revit','Пользователь Windows'];
  const ledger=sheet_(ss,LL.ledger,headers);
  ledger.getRange(1,1,1,headers.length).setValues([headers]);
  sheet_(ss,LL.blobs,['Снимок','Часть','JSON']);
}
function ensureProjectParts_(ss,project) {
  const sh=ss.getSheetByName(LL.parts);
  if (!rows_(sh).some(r=>String(r[0]).trim()===project))
    append_(sh,[[project,'НЧ','',true],[project,'ПЧ','',true]]);
}
function catalog_(ss,project) {
  const values=[];
  rows_(ss.getSheetByName(LL.parts)).forEach(r=>{
    if (String(r[0]).trim()!==project) return;
    const enabled=r[3]==='' || r[3]===true || ['true','да','1'].includes(String(r[3]).trim().toLowerCase());
    const part=String(r[1]).trim(),number=String(r[2]).trim();
    if (!enabled || !['НЧ','ПЧ'].includes(part)) return;
    const label=part+(number ? '-'+number : '');
    if (label.length<=100 && !values.includes(label)) values.push(label);
  });
  return values.sort();
}
function rows_(sh) {
  return sh.getLastRow()>1 ? sh.getRange(2,1,sh.getLastRow()-1,sh.getLastColumn()).getValues() : [];
}
function safe_(v) {
  if (v===undefined || v===null) return '';
  if (typeof v==='string' && v.length>44000) v=v.slice(0,44000)+'… [полный JSON в снимке]';
  // User-controlled text must never execute as spreadsheet formulas.
  return typeof v==='string' && /^[=+\-@\t\r]/.test(v) ? "'"+v : v;
}
function grow_(sh,lastRow,lastColumn) {
  if (lastRow>sh.getMaxRows()) sh.insertRowsAfter(sh.getMaxRows(),lastRow-sh.getMaxRows());
  if (lastColumn>sh.getMaxColumns()) sh.insertColumnsAfter(sh.getMaxColumns(),lastColumn-sh.getMaxColumns());
}
function append_(sh,rows) {
  if (rows.length) grow_(sh,sh.getLastRow()+rows.length,rows[0].length);
  if (rows.length) sh.getRange(sh.getLastRow()+1,1,rows.length,rows[0].length)
    .setValues(rows.map(r=>r.map(safe_)));
}
function scope_(x) { return JSON.stringify([x.project,x.role,x.model]); }
function ledger_(ss) { return rows_(ss.getSheetByName(LL.ledger)); }
function latest_(rows,scope) {
  return rows.filter(r=>scope_({project:r[1],role:r[2],model:r[3]})===scope).slice(-1)[0];
}
function auth_(body) {
  if (typeof body.token!=='string' || body.token.length<32 || body.token.length>256) fail_('UNAUTHORIZED');
  const raw=props_().getProperty('TOKEN_'+sha_(body.token));
  if (!raw) fail_('UNAUTHORIZED');
  const grant=JSON.parse(raw);
  if (body.action==='connect') {
    const department=disciplineCode_(grant.department || grant.discipline || grant.group ||
      ({KR:'КР',AR:'АР'}[grant.role]) || '');
    if (!departmentRole_(department)) fail_('DEPARTMENT_REQUIRED');
    if (departmentRole_(department)!==grant.role) fail_('SCOPE_DENIED');
    return Object.assign({},grant,{department,discipline:department,
      credential_scope:grant.model ? 'model' : grant.project ? 'project_group' : 'group'});
  }
  if (body.role!==grant.role ||
      typeof body.project!=='string' || !body.project.trim() || body.project.length>250 ||
      typeof body.model!=='string' || !body.model || body.model.length>250) fail_('SCOPE_DENIED');
  if (grant.discipline && disciplineCode_(body.discipline)!==disciplineCode_(grant.discipline) &&
      !(body.action==='status' && !body.discipline)) fail_('SCOPE_DENIED');
  if (grant.project && body.project!==grant.project) fail_('SCOPE_DENIED');
  if (grant.model && body.model!==grant.model) fail_('SCOPE_DENIED');
  // Preserve legacy project/model restrictions while new group grants span projects.
  const credential_scope=grant.model ? 'model' : grant.project ? 'project_group' : 'group';
  return Object.assign({},grant,{project:body.project,model:body.model,credential_scope,
    discipline:disciplineCode_(grant.discipline)});
}
function decode_(ss,row) {
  if (!row) return null;
  const parts=rows_(ss.getSheetByName(LL.blobs)).filter(r=>r[0]===row[6]).sort((a,b)=>a[1]-b[1]);
  if (parts.length!==Number(row[7])) fail_('SNAPSHOT_INCOMPLETE');
  // Stored chunks have a JSON prefix, so Sheets never interprets them as formulas.
  const text=parts.map(r=>String(r[2]).slice(1)).join('');
  if (sha_(text)!==row[5]) fail_('SNAPSHOT_CORRUPT');
  return JSON.parse(text);
}
function validate_(s,g,previous) {
  if (s.schema!==1 || scope_(s)!==scope_(g) || typeof s.model_title!=='string') fail_('INVALID_SNAPSHOT');
  if (!s.tasks || !s.receipts || !Array.isArray(s.issues) || !Array.isArray(s.decisions) ||
      !Array.isArray(s.confirmations) || !Array.isArray(s.working)) fail_('INVALID_SNAPSHOT');
  const tasks=Object.values(s.tasks);
  if (g.role!=='VIS' && (tasks.length || s.issues.length || s.confirmations.length)) fail_('SCOPE_DENIED');
  if (g.role==='VIS' && (Object.keys(s.receipts).length || s.decisions.length)) fail_('SCOPE_DENIED');
  function task(t) {
    if (t.project!==g.project || t.source_model!==g.model || !t.task_id ||
        !['KR','AR'].includes(t.recipient || 'KR') || !['issued','withdrawn'].includes(t.status) ||
        !Number.isInteger(t.revision) || t.revision<1 || !t.geometry) fail_('INVALID_TASK');
  }
  tasks.forEach(task);
  Object.keys(s.tasks).forEach(k=>{if (k!==s.tasks[k].task_id) fail_('INVALID_TASK');});
  s.issues.forEach(i=>{if (!Array.isArray(i.tasks)) fail_('INVALID_ISSUE');i.tasks.forEach(task);});
  Object.values(s.receipts).concat(s.decisions).forEach(r=>{
    if (r.project!==g.project || (r.recipient || 'KR')!==g.role ||
        !['accepted','rejected','withdrawn'].includes(r.status) || !r.revisions) fail_('INVALID_RECEIPT');
    Object.values(r.revisions).forEach(v=>{if (!Number.isInteger(v) || v<1) fail_('INVALID_RECEIPT');});
    if (r.geometry && r.geometry.host_model!==g.model) fail_('SCOPE_DENIED');
  });
  // A stale/recovered Revit copy cannot silently erase or roll back released tasks.
  if (previous) {
    Object.keys(previous.tasks).forEach(k=>{
      if (!s.tasks[k] || s.tasks[k].revision<previous.tasks[k].revision) fail_('REVISION_ROLLBACK');
      const a=previous.tasks[k],b=s.tasks[k];
      const released=t=>{const c=Object.assign({},t);delete c.confirmation;return JSON.stringify(c);};
      if ((a.recipient || 'KR')!==(b.recipient || 'KR') ||
          (a.revision===b.revision && released(a)!==released(b))) fail_('REVISION_CONFLICT');
    });
    ['issues','decisions','confirmations'].forEach(k=>{
      if (s[k].length<previous[k].length ||
          JSON.stringify(s[k].slice(0,previous[k].length))!==JSON.stringify(previous[k])) fail_('REVISION_ROLLBACK');
    });
    Object.keys(previous.receipts).forEach(k=>{
      const a=previous.receipts[k],b=s.receipts[k];
      if (!b || !b.revisions[k] || b.revisions[k]<a.revisions[k]) fail_('REVISION_ROLLBACK');
    });
  }
}
function doPost(e) {
  let lock;
  try {
    if (!e || !e.postData || e.postData.contents.length>2*LL.maxPayload+10000) fail_('PAYLOAD_TOO_LARGE');
    const body=JSON.parse(e.postData.contents),grant=auth_(body);
    if (!['connect','status','publish','catalog'].includes(body.action)) fail_('INVALID_ACTION');
    lock=LockService.getScriptLock();
    if (!lock.tryLock(10000)) fail_('BUSY_RETRY');
    const ss=book_();init_(ss);
    if (body.action==='connect') return output_({ok:true,department:grant.department,
      group:grant.department,discipline:grant.department,role:grant.role,
      credential_scope:grant.credential_scope,project:grant.project || '',model:grant.model || '',
      sheet_url:ss.getUrl()});
    const rows=ledger_(ss),previous=latest_(rows,scope_(grant));
    if (body.action==='catalog') {
      ensureProjectParts_(ss,grant.project);
      return output_({ok:true,parts:catalog_(ss,grant.project)});
    }
    if (body.action==='status') return output_({ok:true,version:previous ? previous[4] : 0,sheet_url:ss.getUrl(),credential_scope:grant.credential_scope,group:grant.group || '',discipline:grant.discipline || ''});
    if (typeof body.payload!=='string' || body.payload.length>LL.maxPayload) fail_('PAYLOAD_TOO_LARGE');
    const hash=sha_(body.payload);
    const already=rows.find(r=>scope_({project:r[1],role:r[2],model:r[3]})===scope_(grant) && r[5]===hash);
    if (already) {
      rebuild_(ss);
      return output_({ok:true,version:already[4],unchanged:true,sheet_url:ss.getUrl()});
    }
    const version=previous ? Number(previous[4]) : 0;
    if (body.base_version!==version) fail_('PUBLICATION_CONFLICT');
    const data=JSON.parse(body.payload);
    ['revit_user','windows_user'].forEach(k=>{if (data[k]!==undefined && (typeof data[k]!=='string' || data[k].length>250)) fail_('INVALID_SNAPSHOT');});
    const priorData=decode_(ss,previous);
    validate_(data,grant,priorData);
    const allowedParts=catalog_(ss,grant.project);
    Object.values(data.tasks).forEach(t=>{
      const old=priorData && priorData.tasks[t.task_id];
      if (t.object_part && (!old || old.object_part!==t.object_part) && !allowedParts.includes(t.object_part)) fail_('INVALID_OBJECT_PART');
      if (old && old.object_part && old.object_part!==t.object_part) fail_('INVALID_OBJECT_PART');
    });
    const blob=Utilities.getUuid(),parts=[];
    for (let i=0;i<body.payload.length;) {
      let end=Math.min(i+LL.chunk,body.payload.length);
      const code=body.payload.charCodeAt(end-1);
      if (end<body.payload.length && code>=0xD800 && code<=0xDBFF) end--;
      parts.push([blob,parts.length,'J'+body.payload.slice(i,end)]);
      i=end;
    }
    append_(ss.getSheetByName(LL.blobs),parts);
    SpreadsheetApp.flush();
    // This ledger row commits the snapshot. Uncommitted chunks are never read.
    append_(ss.getSheetByName(LL.ledger),[[new Date().toISOString(),grant.project,grant.role,
      grant.model,version+1,hash,blob,parts.length,grant.department || grant.discipline || grant.group || grant.actor || '',
      data.revit_user || '',data.windows_user || '']]);
    SpreadsheetApp.flush();
    rebuild_(ss);
    return output_({ok:true,version:version+1,unchanged:false,sheet_url:ss.getUrl()});
  } catch (ex) {
    const code=String(ex.message || '');
    const allowed=['DEPARTMENT_REQUIRED','UNAUTHORIZED','SCOPE_DENIED','INVALID_ACTION','NOT_INITIALIZED','BUSY_RETRY',
      'PAYLOAD_TOO_LARGE','INVALID_SNAPSHOT','INVALID_TASK','INVALID_ISSUE','INVALID_RECEIPT',
      'INVALID_OBJECT_PART','REVISION_ROLLBACK','REVISION_CONFLICT','PUBLICATION_CONFLICT','SNAPSHOT_INCOMPLETE','SNAPSHOT_CORRUPT'];
    return output_({ok:false,error:allowed.includes(code) ? code : 'SERVER_ERROR_RETRY'});
  } finally { if (lock) lock.releaseLock(); }
}
function output_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}
function project_(ss,name,headers,rows) {
  const sh=sheet_(ss,name,headers);
  grow_(sh,rows.length+1,headers.length);
  sh.clearContents();
  sh.getRange(1,1,1,headers.length).setValues([headers]);
  if (rows.length) sh.getRange(2,1,rows.length,headers.length).setValues(rows.map(r=>r.map(safe_)));
  sh.setFrozenRows(1);
  const filter=sh.getFilter();if (filter) filter.remove();
  if (rows.length) sh.getRange(1,1,rows.length+1,headers.length).createFilter();
}
function rebuildJournal() {
  admin_();
  const lock=LockService.getScriptLock();lock.waitLock(10000);
  try { const ss=book_();init_(ss);rebuild_(ss); } finally { lock.releaseLock(); }
}
function objectTab_(project) {
  const clean=String(project).replace(/[\\/?:*\[\]]/g,'_').trim().slice(0,65) || 'Без имени';
  return 'Объект '+clean+' '+sha_(String(project)).slice(0,8);
}
function gipRows_(snapshots,answers) {
  const groups=Object.create(null);
  const key=t=>JSON.stringify([t.project,t.discipline || '',t.recipient || 'KR',t.object_part || '']);
  const max=(a,b)=>a && b ? (a>b ? a : b) : (a || b || '');
  const min=(a,b)=>a && b ? (a<b ? a : b) : (a || b || '');
  const activity=Object.create(null);
  function remember(g,d) {
    if (d.at && (!g.lastDecision || d.at>=g.lastDecision)) {
      g.lastDecision=d.at;g.lastDecisionAuthor=d.author || '';
    }
    if (d.status==='accepted') g.lastAccept=max(g.lastAccept,d.at);
    if (d.status==='rejected' && d.at && (!g.lastRemark || d.at>=g.lastRemark)) {
      g.lastRemark=d.at;g.lastRemarkAuthor=d.author || '';g.lastRemarkText=d.comment || '';
    }
  }
  snapshots.forEach(({s})=>s.decisions.forEach(d=>Object.keys(d.revisions).forEach(k=>{
    const id=JSON.stringify([s.project,s.role,s.model,k]);
    if (!activity[id]) activity[id]={};
    remember(activity[id],d);
  })));
  function group(t) {
    const k=key(t);
    if (!groups[k]) groups[k]={project:t.project,discipline:t.discipline || '',role:t.recipient || 'KR',
      part:t.object_part || '',active:0,accepted:0,remarks:0,review:0,withdrawPending:0,first:'',last:'',
      lastAccept:'',lastRemark:'',lastDecision:'',completeAt:'',visPublished:'',replyPublished:''};
    return groups[k];
  }
  snapshots.forEach(({row,s})=>{
    Object.values(s.tasks).forEach(t=>{
      const g=group(t),taskKey=t.source_model+'/'+t.task_id;
      const lookup=JSON.stringify([t.project,t.recipient || 'KR',t.geometry.host_model,taskKey]);
      const a=answers[lookup];
      const r=a ? a.receipt : null,current=!!r && r.revisions[taskKey]===t.revision;
      g.visPublished=max(g.visPublished,row[0]);
      if (a) {
        g.replyPublished=max(g.replyPublished,a.at);
        remember(g,r);
      }
      if (t.status==='withdrawn') {
        if (!(current && r.status==='withdrawn')) g.withdrawPending++;
      } else {
        g.active++;
        const verified=current && r.status==='accepted' && a.observed && a.observed.exists && a.observed.matches;
        if (verified) {
          g.accepted++;
          g.completeAt=max(g.completeAt,r.at);
        } else if (current && r.status==='rejected') {
          g.remarks++;
        }
        if (current && r.status==='accepted' && !verified) g.review++;
        g.first=min(g.first,t.created_at || t.issued_at);
        g.last=max(g.last,t.issued_at);
      }
      // Preindexed activity avoids rescanning all receiver histories per task.
      const past=activity[lookup];
      if (past) {
        if (past.lastDecision && past.lastDecision>=g.lastDecision) {
          g.lastDecision=past.lastDecision;g.lastDecisionAuthor=past.lastDecisionAuthor;
        }
        g.lastAccept=max(g.lastAccept,past.lastAccept);
        if (past.lastRemark && (!g.lastRemark || past.lastRemark>=g.lastRemark)) {
          g.lastRemark=past.lastRemark;g.lastRemarkAuthor=past.lastRemarkAuthor;g.lastRemarkText=past.lastRemarkText;
        }
      }
    });
    s.issues.forEach(i=>{
      if (i.action==='withdraw') return;
      i.tasks.forEach(t=>{
        const g=group(s.tasks[t.task_id] || t);
        g.first=min(g.first,i.at || t.issued_at);
        g.last=max(g.last,i.at || t.issued_at);
      });
    });
  });
  return Object.keys(groups).sort().map(k=>{
    const g=groups[k];
    const complete=g.active>0 && g.accepted===g.active && !g.withdrawPending;
    const state=complete ? 'Все отверстия приняты' :
      g.remarks ? 'Есть замечания' : g.review ? 'Требуется проверка проёмов' :
      g.withdrawPending ? 'Есть неотработанные отзывы' :
      !g.active ? 'Нет действующих заданий' : 'На рассмотрении';
    return [g.project,g.discipline,g.role,state,g.active,g.accepted,
      g.active-g.accepted-g.remarks,g.remarks,g.review,g.withdrawPending,
      g.first,g.last,g.lastAccept,g.lastRemark,g.lastDecision,complete ? g.completeAt : '',
      g.visPublished,g.replyPublished,g.lastDecisionAuthor || '',g.lastRemarkAuthor || '',
      String(g.lastRemarkText || '').slice(0,250),g.part];
  });
}
function rebuild_(ss) {
  const all=ledger_(ss),latest={};
  all.forEach(r=>{latest[scope_({project:r[1],role:r[2],model:r[3]})]=r;});
  const tasks=[],replies=[],working=[],history=[];
  const snapshots=Object.values(latest).map(row=>({row,s:decode_(ss,row)}));
  const answers={};
  snapshots.forEach(({row,s})=>{
    Object.keys(s.receipts).forEach(k=>{
      answers[JSON.stringify([s.project,s.role,s.model,k])]={receipt:s.receipts[k],at:row[0],
        observed:(s.observations || {})[k]};
    });
  });
  project_(ss,LL.gip,['Объект','Дисциплина','Получатель','Состояние','Действующих заданий',
    'Принято актуальных','Требуют рассмотрения','Замечаний','Проёмы требуют проверки','Неотработанных отзывов',
    'Первая выдача','Последняя выдача','Последнее принятие','Последнее замечание','Последнее решение',
    'Все отверстия приняты — дата','Публикация ВИС','Публикация КР/АР',
    'Автор последнего решения','Автор последнего замечания','Последнее замечание — кратко','Часть объекта'],gipRows_(snapshots,answers));
  const overview=[];
  snapshots.forEach(({row,s})=>{
    Object.values(s.tasks).forEach(t=>{
      const a=answers[JSON.stringify([s.project,t.recipient || 'KR',t.geometry.host_model,t.source_model+'/'+t.task_id])];
      const r=a ? a.receipt : null;
      const revision=r ? r.revisions[t.source_model+'/'+t.task_id] : '';
      let state='Ожидает рассмотрения',next='Получателю: обновить связь ВИС и рассмотреть';
      if (t.status==='withdrawn') {
        state=r && r.status==='withdrawn' && revision===t.revision ? 'Отзыв отработан' : 'Отзыв не отработан';
        next=state==='Отзыв отработан' ? 'Действий не требуется' : 'Получателю: отработать отзыв';
      } else if (r) {
        if (r.status==='accepted' && a.observed && !a.observed.exists) {
          state='Проём удалён';next='Получателю: проверить проём';
        } else if (r.status==='accepted' && a.observed && !a.observed.matches) {
          state='Проём изменён';next='Согласовать изменения';
        } else if (revision!==t.revision) {
          state='Ответ на старую ревизию';next='Получателю: принять новую ревизию';
        } else if (r.status==='rejected') {
          state='Замечание';next='ВИС: исправить бокс и перевыдать';
        } else if (r.status==='accepted') {
          state='Принято';next='ВИС: проверить и подтвердить';
          if (t.confirmation && t.confirmation.revision===t.revision && t.confirmation.opening_id===r.opening_id) {
            state='Подтверждено ВИС';next='Действий не требуется';
          }
        }
      }
      overview.push([s.project,t.discipline,t.recipient || 'KR',t.task_number,t.task_id,
        t.status,t.revision,revision,state,r ? r.comment || '' : '',next,
        t.issued_at,row[0],a ? a.at : '',t.geometry.host_model,t.geometry.host_uid,
        JSON.stringify(t.geometry.size_mm),s.model_title,t.object_part || '',t.revit_user || t.author || '',t.windows_user || '']);
    });
    Object.values(s.tasks).forEach(t=>{
      const g=t.geometry;
      tasks.push([s.project,t.discipline,t.recipient || 'KR',t.task_number,t.task_id,t.source_model,
        s.model_title,t.source_uid,t.owner_uid,t.status,t.revision,t.issue_number || '',t.issue_id,
        t.created_at,t.issued_at,t.author,g.host_model,g.host_uid,g.kind,
        JSON.stringify(g.center_mm),JSON.stringify(g.size_mm),JSON.stringify(g.x_dir),
        t.confirmation ? JSON.stringify(t.confirmation) : '',row[0],t.object_part || '',t.revit_user || t.author || '',t.windows_user || '']);
    });
    Object.keys(s.receipts).forEach(key=>{
      const r=s.receipts[key];
      replies.push([s.project,s.role,s.model,s.model_title,key,r.revisions[key],r.status,
        r.comment || '',r.opening_id || '',r.opening_uid || '',r.author || '',r.at || '',
        JSON.stringify(r.revisions),r.geometry ? JSON.stringify(r.geometry) : '',row[0],r.object_part || '',r.revit_user || r.author || '',r.windows_user || '']);
    });
    s.working.forEach(w=>working.push([s.project,s.role,s.model,w.number || '',w.task_id || '',
      w.recipient || '',w.level || '',w.kind || '',w.status || '',w.result || '',w.sizes || '',
      w.previous_sizes || '',w.displacement || '',w.comment || '',w.next_action || '',row[0],w.object_part || '']));
    s.issues.forEach(i=>i.tasks.forEach(t=>history.push([s.project,s.role,s.model,i.at || '',
      i.author || '',i.action || '',t.task_id,t.revision,t.status,t.issue_id || '',t.object_part || '',t.revit_user || t.author || i.author || '',t.windows_user || ''])));
    s.decisions.forEach(r=>Object.keys(r.revisions).forEach(k=>history.push([s.project,s.role,s.model,
      r.at || '',r.author || '',r.status,k,r.revisions[k],r.comment || '',r.opening_id || '',r.object_part || '',r.revit_user || r.author || '',r.windows_user || ''])));
    s.confirmations.forEach(c=>history.push([s.project,s.role,s.model,c.at || '',c.author || '',
      'confirmed',c.task_id,c.revision,'',c.opening_id || '',c.object_part || '',c.revit_user || c.author || '',c.windows_user || '']));
  });
  const objects=Object.create(null);
  function objectRow(project,row) {
    if (!objects[project]) objects[project]=[];
    objects[project].push(row);
  }
  overview.forEach(r=>objectRow(r[0],['Текущее состояние',r[12],''].concat(r)));
  snapshots.forEach(({row,s})=>{
    s.issues.forEach(i=>i.tasks.forEach(t=>{
      const g=t.geometry;
      objectRow(s.project,[t.status==='withdrawn' ? 'Отзыв' : t.revision>1 ? 'Перевыдача' : 'Выдача',
        i.at || '',i.author || '',s.project,t.discipline,t.recipient || 'KR',t.task_number,t.task_id,
        t.status,t.revision,'','','','',t.issued_at,row[0],'',g.host_model,g.host_uid,
        JSON.stringify(g.size_mm),s.model_title,t.object_part || '',t.revit_user || t.author || i.author || '',t.windows_user || '']);
    }));
    s.decisions.forEach(r=>Object.keys(r.revisions).forEach(k=>{
      const g=r.geometry || {};
      objectRow(s.project,['Решение '+s.role,r.at || '',r.author || '',s.project,'',s.role,'',k,
        r.status,'',r.revisions[k],r.status,r.comment || '','',r.at || '','',row[0],
        s.model,g.host_uid || '',g.size_mm ? JSON.stringify(g.size_mm) : '',s.model_title,r.object_part || '',r.revit_user || r.author || '',r.windows_user || '']);
    }));
    s.confirmations.forEach(c=>objectRow(s.project,['Подтверждение ВИС',c.at || '',c.author || '',
      s.project,'',c.recipient || 'KR','',c.task_id,'confirmed',c.revision,c.revision,
      'Подтверждено ВИС','','',c.at || '',row[0],'',c.kr_model || '','','',s.model_title,c.object_part || '',c.revit_user || c.author || '',c.windows_user || '']));
  });
  Object.keys(objects).sort().forEach(project=>project_(ss,objectTab_(project),
    ['Запись','Дата события','Автор','Проект','Дисциплина','Получатель','Номер','GUID задания','Статус выдачи',
     'Выданная ревизия','Ревизия ответа','Результат','Замечание','Что делать','Дата выдачи',
     'Публикация ВИС','Публикация получателя','Модель получателя ID','Конструкция UID','Размеры мм','Модель ВИС','Часть объекта','Пользователь Revit','Пользователь Windows'],
    objects[project]));
  project_(ss,LL.overview,['Проект','Дисциплина','Получатель','Номер','GUID задания','Статус выдачи',
    'Выданная ревизия','Ревизия ответа','Результат','Замечание','Что делать','Дата выдачи',
    'Публикация ВИС','Публикация получателя','Модель получателя ID','Конструкция UID','Размеры мм','Модель ВИС','Часть объекта','Пользователь Revit','Пользователь Windows'],overview);
  project_(ss,LL.tasks,['Проект','Дисциплина','Получатель','Номер','GUID задания','Модель ВИС ID','Модель ВИС',
    'Исходный элемент UID','Бокс UID','Статус выдачи','Ревизия','Номер выпуска','ID выпуска','Создано','Выдано',
    'Автор','Модель получателя ID','Конструкция UID','Тип','Центр XYZ мм','Размеры XYZ мм','Ось X','Подтверждение ВИС','Опубликовано','Часть объекта','Пользователь Revit','Пользователь Windows'],tasks);
  project_(ss,LL.replies,['Проект','Роль','Модель ID','Модель','Ключ задания','Ревизия ответа','Решение','Замечание',
    'Проём ID','Проём UID','Автор','Дата решения','Состав объединения','Геометрия','Опубликовано','Часть объекта','Пользователь Revit','Пользователь Windows'],replies);
  project_(ss,LL.working,['Проект','Роль','Модель ID','Задание','GUID','Получатель','Уровень','Конструкция',
    'Статус в модели','Ответ по связи','Размеры мм','Предыдущие размеры мм','Смещение мм','Замечание','Что делать','Опубликовано','Часть объекта'],working);
  project_(ss,LL.history,['Проект','Роль','Модель ID','Дата','Автор','Действие','Задание','Ревизия','Результат','Выпуск/проём ID','Часть объекта','Пользователь Revit','Пользователь Windows'],history);
}
