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
