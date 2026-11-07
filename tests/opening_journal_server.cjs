// Apps Script protocol tests with in-memory spreadsheet/properties adapters.
const fs=require('fs'),vm=require('vm'),crypto=require('crypto'),assert=require('assert');
class Sheet {
  constructor(){this.rows=[];}
  getLastRow(){return this.rows.length;}
  getLastColumn(){return this.rows[0]?.length || 0;}
  getRange(r,c,n,m){return {
    setValues:v=>{assert.equal(v.length,n);v.forEach((row,i)=>{
      assert.equal(row.length,m);
      this.rows[r-1+i] ||= [];
      row.forEach((x,j)=>this.rows[r-1+i][c-1+j]=x);
    });},
    getValues:()=>this.rows.slice(r-1,r-1+n).map(row=>row.slice(c-1,c-1+m)),
    createFilter:()=>{}
  };}
  getMaxRows(){return 1000;}
  getMaxColumns(){return 26;}
  insertRowsAfter(){}
  insertColumnsAfter(){}
  setFrozenRows(){}
  getFilter(){return null;}
  clearContents(){this.rows=[];}
}
const sheets={},ss={
  getSheetByName:n=>sheets[n],
  insertSheet:n=>sheets[n]=new Sheet(),
  getUrl:()=> 'https://docs.google.com/spreadsheets/d/test'
};
const properties={SPREADSHEET_ID:'test',ADMIN_EMAIL:'admin@example.org'};
const sandbox={
  console,Date,JSON,
  PropertiesService:{getScriptProperties:()=>({
    getProperty:k=>properties[k] || null,
    setProperty:(k,v)=>properties[k]=v,
    setProperties:d=>Object.assign(properties,d),
    deleteProperty:k=>delete properties[k]
  })},
  Utilities:{
    DigestAlgorithm:{SHA_256:1},Charset:{UTF_8:1},
    computeDigest:(_,s)=>[...crypto.createHash('sha256').update(s).digest()],
    getUuid:()=>crypto.randomUUID()
  },
  SpreadsheetApp:{openById:()=>ss,flush:()=>{}},
  LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock:()=>{}})},
  ContentService:{MimeType:{JSON:1},createTextOutput:text=>({setMimeType:()=>JSON.parse(text)})},
  Session:{getActiveUser:()=>({getEmail:()=> 'engineer@example.org'})}
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),sandbox);
function grant(token,role='VIS',model='vis'){
  properties['TOKEN_'+sandbox.sha_(token)]=JSON.stringify({actor:'user',project:'P',role,model});
}
const token='s'.repeat(64),krToken='k'.repeat(64),arToken='a'.repeat(64);
grant(token);grant(krToken,'KR','kr');grant(arToken,'AR','ar');
const scope={token,project:'P',role:'VIS',model:'vis'};
const base=()=>({schema:1,project:'P',role:'VIS',model:'vis',model_title:'Model',
  tasks:{a:{project:'P',source_model:'vis',task_id:'a',recipient:'KR',status:'issued',revision:1,
    geometry:{host_model:'kr',host_uid:'wall',center_mm:[0,0,0],size_mm:[100,100,100],x_dir:[1,0,0]}}},
  issues:[],receipts:{},decisions:[],confirmations:[],working:[]});
function call(body){return sandbox.doPost({postData:{contents:JSON.stringify(body)}});}
function pub(data,version=0,credentials=scope){
  return call({...credentials,action:'publish',base_version:version,payload:JSON.stringify(data)});
}
assert.equal(call({...scope,action:'status'}).version,0);
assert.equal(call({...scope,token:'bad',action:'status'}).error,'UNAUTHORIZED');
assert.equal(call({...scope,model:'other',action:'status'}).error,'SCOPE_DENIED');
assert.equal(call({...scope,action:'issueModelToken'}).error,'INVALID_ACTION');
assert.throws(()=>sandbox.issueModelToken(),/ADMIN_ONLY/);
let data=base();
assert.equal(pub(data).version,1);
assert.equal(pub(data).unchanged,true);
assert.equal(sheets['Публикации'].rows.length,2);
data=base();data.tasks.a.revision=2;
assert.equal(pub(data,0).error,'PUBLICATION_CONFLICT');
assert.equal(pub(data,1).version,2);
assert.equal(pub(base(),2).unchanged,true); // A delayed acknowledgement of an older sent item.
assert.equal(sheets['Публикации'].rows.length,3);
const rollback=base();rollback.model_title='Recovered copy';
assert.equal(pub(rollback,2).error,'REVISION_ROLLBACK');
const changed=structuredClone(data);changed.tasks.a.geometry.size_mm=[300,100,100];
assert.equal(pub(changed,2).error,'REVISION_CONFLICT');
const missing=base();missing.tasks={};
assert.equal(pub(missing,2).error,'REVISION_ROLLBACK');
const foreign=structuredClone(data);foreign.tasks.a.source_model='someone';
assert.equal(pub(foreign,2).error,'INVALID_TASK');
// The entire raw record survives chunking; the projected table cannot run formulas.
data.working=[{task_id:'a',comment:'=IMPORTXML("bad")'}];
data.tasks.a.extra='x'.repeat(90000);data.tasks.a.revision=3;
assert.equal(pub(data,2).version,3);
assert.equal(sheets['Снимки JSON'].rows.filter(r=>r[0]===sheets['Публикации'].rows.at(-1)[6]).length,3);
const last=sheets['Публикации'].rows.at(-1);
assert.equal(sandbox.decode_(ss,last).tasks.a.extra.length,90000);
assert(sheets['Контроль в Revit'].rows[1].some(v=>String(v).startsWith("'=IMPORTXML")));
// Separate recipient snapshots cannot replace the VIS releases.
const kr={schema:1,project:'P',role:'KR',model:'kr',model_title:'KR',tasks:{},issues:[],
  confirmations:[],working:[],decisions:[],
  receipts:{'vis/a':{project:'P',recipient:'KR',status:'rejected',revisions:{'vis/a':2},comment:'Fix size'}}};
assert.equal(pub(kr,0,{token:krToken,project:'P',role:'KR',model:'kr'}).version,1);
assert.equal(sheets['Задания'].rows.length,2);
assert.equal(sheets['Ответы КР АР'].rows[1][7],'Fix size');
assert.equal(sheets['Обзор'].rows[1][8],'Ответ на старую ревизию');
const ar=structuredClone(kr);ar.role='AR';ar.model='ar';ar.receipts['vis/a'].recipient='KR';
assert.equal(pub(ar,0,{token:arToken,project:'P',role:'AR',model:'ar'}).error,'INVALID_RECEIPT');
// Revoking one grant leaves all others intact.
delete properties['TOKEN_'+sandbox.sha_(krToken)];
assert.equal(call({token:krToken,project:'P',role:'KR',model:'kr',action:'status'}).error,'UNAUTHORIZED');
assert.equal(call({...scope,action:'status'}).version,3);
console.log('Opening journal Apps Script protocol checks passed');

// Separate project tabs are stable, valid and do not merge similar names.
const projectData=base();projectData.project='Other/Object';
projectData.tasks.a.project='Other/Object';
properties['TOKEN_'+sandbox.sha_('p'.repeat(64))]=JSON.stringify({actor:'user',project:'Other/Object',role:'VIS',model:'vis'});
assert.equal(pub(projectData,0,{token:'p'.repeat(64),project:'Other/Object',role:'VIS',model:'vis'}).version,1);
const tab1=sandbox.objectTab_('P'),tab2=sandbox.objectTab_('Other/Object');
assert.notEqual(tab1,tab2);
assert.notEqual(sandbox.objectTab_('A/B'),sandbox.objectTab_('A:B'));
assert(!/[\/?:*\[\]]/.test(tab2));
assert(sheets[tab1].rows.slice(1).every(r=>r[3]==='P'));
assert(sheets[tab2].rows.slice(1).every(r=>r[3]==='Other/Object'));
// Both release revisions remain as separate object-history rows.
const event=structuredClone(data);
event.issues=[{at:'t1',author:'VIS',tasks:[base().tasks.a]},
              {at:'t3',author:'VIS',tasks:[structuredClone(data.tasks.a)]}];
assert.equal(pub(event,3).version,4);
const entries=sheets[tab1].rows.slice(1);
assert(entries.some(r=>r[0]==='Выдача' && r[9]===1));
assert(entries.some(r=>r[0]==='Перевыдача' && r[9]===3));
assert.equal(pub(data,0).unchanged,true); // Retry of a previously committed revision.
assert.equal(call({...scope,action:'status'}).version,4);

// GIP summary groups models by object, discipline and recipient; revisions reopen review.
function gipTask(id,role='KR',discipline='OV',project='GIP'){
  return {project,discipline,task_id:id,source_model:'vis',recipient:role,status:'issued',revision:1,
    created_at:'2026-01-01T09:00:00Z',issued_at:'2026-01-01T09:00:00Z',
    geometry:{host_model:role==='KR' ? 'kr' : 'ar'}};
}
function gipSnapshot(tasks){
  return {row:['2026-01-01T10:00:00Z'],s:{tasks:Object.fromEntries(tasks.map(t=>[t.task_id,t])),
    issues:[],decisions:[],project:'GIP',role:'VIS',model:'vis'}};
}
function answerFor(t,status='accepted',at='2026-01-02T10:00:00Z',revision=t.revision){
  return [JSON.stringify([t.project,t.recipient,t.geometry.host_model,'vis/'+t.task_id]),
    {receipt:{status,at,revisions:{['vis/'+t.task_id]:revision}},
      observed:{exists:true,matches:true},at:'2026-01-02T11:00:00Z'}];
}
const g1=gipTask('1'),g2=gipTask('2');
let gipAnswers=Object.fromEntries([answerFor(g1),answerFor(g2,'rejected','2026-01-02T12:00:00Z')]);
let gip=sandbox.gipRows_([gipSnapshot([g1,g2])],gipAnswers);
assert.equal(gip.length,1);
assert.equal(gip[0][3],'Есть замечания');
assert.equal(gip[0][4],2);assert.equal(gip[0][5],1);assert.equal(gip[0][7],1);
assert.equal(gip[0][13],'2026-01-02T12:00:00Z');assert.equal(gip[0][15],'');
gipAnswers=Object.fromEntries([answerFor(g1),answerFor(g2,'accepted','2026-01-03T10:00:00Z')]);
gip=sandbox.gipRows_([gipSnapshot([g1,g2])],gipAnswers);
assert.equal(gip[0][3],'Все отверстия приняты');
assert.equal(gip[0][15],'2026-01-03T10:00:00Z');
const reissued={...g2,revision:2,issued_at:'2026-01-04T09:00:00Z'};
gip=sandbox.gipRows_([gipSnapshot([g1,reissued])],gipAnswers);
assert.equal(gip[0][3],'На рассмотрении');assert.equal(gip[0][15],'');
assert.equal(gip[0][11],'2026-01-04T09:00:00Z');
// Neither a missing/changed opening nor an unverified receipt closes the group.
gipAnswers[answerFor(g1)[0]].observed.exists=false;
gip=sandbox.gipRows_([gipSnapshot([g1,g2])],gipAnswers);
assert.equal(gip[0][3],'Требуется проверка проёмов');assert.equal(gip[0][15],'');
const withdrawn={...g2,status:'withdrawn',revision:2};
gip=sandbox.gipRows_([gipSnapshot([withdrawn])],{});
assert.equal(gip[0][3],'Есть неотработанные отзывы');assert.equal(gip[0][15],'');
gip=sandbox.gipRows_([gipSnapshot([withdrawn])],Object.fromEntries([answerFor(withdrawn,'withdrawn')]));
assert.equal(gip[0][3],'Нет действующих заданий');assert.equal(gip[0][15],'');
// The AR recipient, another discipline and another object get independent rows.
gip=sandbox.gipRows_([gipSnapshot([g1,gipTask('3','AR'),gipTask('4','KR','VK'),gipTask('5','KR','OV','OTHER')])],{});
assert.equal(gip.length,4);
// Past comments remain visible as activity dates after acceptance.
const receiver={row:['2026-01-05T11:00:00Z'],s:{project:'GIP',role:'KR',model:'kr',tasks:{},issues:[],
  decisions:[{status:'rejected',at:'2026-01-01T13:00:00Z',revisions:{'vis/1':1}}]}};
gip=sandbox.gipRows_([gipSnapshot([g1]),receiver],Object.fromEntries([answerFor(g1)]));
assert.equal(gip[0][7],0);assert.equal(gip[0][13],'2026-01-01T13:00:00Z');
assert(sheets['ГИП'].rows.length>1);

// Object part catalog comes only from rows for the authorized project.
sandbox.append_(sheets['Части объектов'],[
  ['P','НЧ','01',true],['P','ПЧ','',true],['P','НЧ','2',false],
  ['OTHER','НЧ','9',true],['P','НЧ','01',true],['P','wrong','3',true]]);
assert.deepEqual(call({...scope,action:'catalog'}).parts,['НЧ-01','ПЧ']);
assert.equal(call({...scope,project:'OTHER',action:'catalog'}).error,'SCOPE_DENIED');
assert.equal(call({...scope,token:'bad',action:'catalog'}).error,'UNAUTHORIZED');
const withPart=structuredClone(event);withPart.tasks.a.revision=4;withPart.tasks.a.object_part='НЧ-01';
assert.equal(pub(withPart,4).version,5);
assert.equal(sheets['Задания'].rows.find(r=>r[0]==='P')[24],'НЧ-01');
assert.equal(sheets['ГИП'].rows.find(r=>r[0]==='P').at(-1),'НЧ-01');
const relabel=structuredClone(withPart);relabel.tasks.a.revision=5;relabel.tasks.a.object_part='ПЧ';
assert.equal(pub(relabel,5).error,'INVALID_OBJECT_PART');
const invalidPart=structuredClone(withPart);invalidPart.tasks.a.revision=5;invalidPart.tasks.a.object_part='НЧ-99';
assert.equal(pub(invalidPart,5).error,'INVALID_OBJECT_PART');
const separated=sandbox.gipRows_([gipSnapshot([{...g1,object_part:'НЧ-1'},{...g2,object_part:'ПЧ-1'}])],{});
assert.equal(separated.length,2);

// One group token works for multiple models; project and role remain restricted.
const sharedToken='g'.repeat(64);
properties['TOKEN_'+sandbox.sha_(sharedToken)]=JSON.stringify({group:'ОВ',project:'P',role:'VIS'});
const sharedScope={token:sharedToken,project:'P',role:'VIS',model:'vis'};
assert.equal(call({...sharedScope,action:'status'}).credential_scope,'project_group');
assert.equal(call({...sharedScope,role:'KR',action:'status'}).error,'SCOPE_DENIED');
assert.equal(call({...sharedScope,project:'Other',action:'status'}).error,'SCOPE_DENIED');
const firstGroup=structuredClone(withPart);
firstGroup.tasks.a.revision=5;
firstGroup.revit_user='Revit Ivanov';firstGroup.windows_user='BUREAU\\ivanov';
firstGroup.tasks.a.revit_user='Revit Ivanov';firstGroup.tasks.a.windows_user='BUREAU\\ivanov';
assert.equal(pub(firstGroup,5,sharedScope).version,6);
const secondGroup=base();secondGroup.model='vis-2';secondGroup.tasks.a.source_model='vis-2';
secondGroup.revit_user='Revit Petrov';secondGroup.windows_user='BUREAU\\petrov';
assert.equal(pub(secondGroup,0,{...sharedScope,model:'vis-2'}).version,1);
assert.equal(call({...sharedScope,action:'status'}).version,6);
assert.equal(call({...sharedScope,model:'vis-2',action:'status'}).version,1);
const ledgerRows=sheets['Публикации'].rows;
assert.equal(ledgerRows.at(-1)[3],'vis-2');
assert.equal(ledgerRows.at(-1)[8],'ОВ');
assert.equal(ledgerRows.at(-1)[9],'Revit Petrov');
assert.equal(ledgerRows.at(-1)[10],'BUREAU\\petrov');
assert.equal(sheets['Задания'].rows.find(r=>r[0]==='P' && r[5]==='vis')[26],'BUREAU\\ivanov');
const spoof=structuredClone(secondGroup);spoof.model='different';
assert.equal(pub(spoof,1,{...sharedScope,model:'vis-2'}).error,'INVALID_SNAPSHOT');

// Global group grants span objects while legacy grants keep their restrictions.
const globalToken='z'.repeat(64);
properties['TOKEN_'+sandbox.sha_(globalToken)]=JSON.stringify({group:'Инженеры ВИС',role:'VIS'});
const globalScope={token:globalToken,project:'NEW-1',role:'VIS',model:'new-model-1'};
assert.equal(call({...globalScope,action:'status'}).credential_scope,'group');
function globalData(project,model){
  const value=base();value.project=project;value.model=model;
  value.tasks.a.project=project;value.tasks.a.source_model=model;
  return value;
}
assert.equal(pub(globalData('NEW-1','new-model-1'),0,globalScope).version,1);
assert.equal(pub(globalData('NEW-2','new-model-2'),0,{...globalScope,project:'NEW-2',model:'new-model-2'}).version,1);
assert.equal(call({...globalScope,action:'status'}).version,1);
assert.equal(call({...globalScope,project:'NEW-2',model:'new-model-2',action:'status'}).version,1);
assert.equal(call({...globalScope,role:'KR',action:'status'}).error,'SCOPE_DENIED');
assert.equal(call({...globalScope,project:'',action:'status'}).error,'SCOPE_DENIED');
assert.equal(call({...sharedScope,project:'NEW-1',action:'status'}).error,'SCOPE_DENIED');
assert.equal(call({...scope,project:'NEW-1',action:'status'}).error,'SCOPE_DENIED');
assert(sheets[sandbox.objectTab_('NEW-1')].rows.slice(1).every(r=>r[3]==='NEW-1'));
assert(sheets[sandbox.objectTab_('NEW-2')].rows.slice(1).every(r=>r[3]==='NEW-2'));

// Public installer choices are disciplines, while existing internal interfaces remain compatible.
const vkToken='v'.repeat(64);
properties['TOKEN_'+sandbox.sha_(vkToken)]=JSON.stringify({group:'ВК',role:'VIS',discipline:'ВК'});
const vkScope={token:vkToken,project:'VK-P',model:'vk-model',role:'VIS',discipline:'ВК'};
assert.equal(call({...vkScope,action:'status'}).discipline,'ВК');
assert.equal(call({...vkScope,discipline:'ОК',action:'status'}).error,'SCOPE_DENIED');
const bootstrap={...vkScope};delete bootstrap.discipline;
assert.equal(call({...bootstrap,action:'status'}).discipline,'ВК'); // Admin setup reads it from the token.
assert.equal(call({...bootstrap,action:'catalog'}).error,'SCOPE_DENIED');
const vkData=globalData('VK-P','vk-model');vkData.tasks.a.discipline='ВК';
assert.equal(pub(vkData,0,vkScope).version,1);
assert.equal(pub(vkData,0,bootstrap).error,'SCOPE_DENIED');


// The model supplies the project code; a new object's directory starts with НЧ/ПЧ.
const autoScope={...globalScope,project:'AUTO-PARTS',model:'auto-model',action:'catalog'};
assert.deepEqual(call(autoScope).parts,['НЧ','ПЧ']);
assert.deepEqual(call(autoScope).parts,['НЧ','ПЧ']);
assert.equal(sheets['Части объектов'].rows.filter(r=>r[0]==='AUTO-PARTS').length,2);
assert.equal(sheets['Части объектов'].rows.filter(r=>r[0]==='AUTO-PARTS')[0][0],'AUTO-PARTS');

// Correct HVAC label and compatibility with already distributed ОК tokens.
assert.equal(sandbox.disciplineCode_('ОВиК'),'ОВиК');
assert.equal(sandbox.disciplineCode_('овик'),'ОВиК');
const hvacToken='h'.repeat(64);
properties['TOKEN_'+sandbox.sha_(hvacToken)]=JSON.stringify({group:'HVAC',role:'VIS',discipline:'ОК'});
const hvacScope={token:hvacToken,project:'HVAC-P',model:'hvac-model',role:'VIS',discipline:'ОВиК'};
assert.equal(call({...hvacScope,action:'status'}).discipline,'ОВиК');
assert.equal(call({...hvacScope,discipline:'ОК',action:'status'}).discipline,'ОВиК');
assert.equal(call({...hvacScope,discipline:'ВК',action:'status'}).error,'SCOPE_DENIED');
