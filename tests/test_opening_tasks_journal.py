# -*- coding: utf-8 -*-
import copy
import pytest
from lowlife import opening_tasks_journal as j
from lowlife import opening_tasks_core as c


def registry():
    t=dict(project='P',source_model='vis',task_id='a',recipient='KR',revision=1)
    other=dict(t,project='OTHER',task_id='b')
    return dict(tasks={'a':t,'b':other},issues=[dict(id='i',tasks=[t,other])],
                receipts={'vis/a':dict(project='P',status='accepted',revisions={'vis/a':1})},
                ar_receipts={'vis/c':dict(project='P',recipient='AR',status='rejected',comment='AR')},
                decisions=[dict(project='P',status='accepted')],
                ar_decisions=[dict(project='P',recipient='AR',status='rejected')],
                confirmations=[dict(task_id='a',revision=1),dict(task_id='b',revision=1)])


def test_vis_snapshot_scopes_project_and_model_without_secrets_or_foreign_receipts():
    r=registry()
    original=copy.deepcopy(r)
    s=j.snapshot(r,'P','VIS','vis','Name',[dict(task_id='a',status='changed',record={'secret':'hidden'}),
                                         dict(task_id='b',status='issued')])
    assert set(s['tasks'])=={'a'}
    assert len(s['issues'][0]['tasks'])==1
    assert s['receipts']=={}
    assert s['decisions']==[]
    assert s['confirmations']==[dict(task_id='a',revision=1)]
    assert s['working']==[dict(task_id='a',status='changed')]
    assert r==original
    assert j.snapshot(r,'P','VIS','other','Name')['tasks']=={}


@pytest.mark.parametrize('role,key',[('KR','vis/a'),('AR','vis/c')])
def test_receiver_snapshot_is_separate_from_issuer(role,key):
    s=j.snapshot(registry(),'P',role,'model','Name')
    assert s['tasks']=={}
    assert s['issues']==[]
    assert set(s['receipts'])=={key}
    assert len(s['decisions'])==1
    assert s['confirmations']==[]


def test_only_named_admin_sees_configuration():
    assert j.is_admin('persiyanov')
    assert j.is_admin('PERSIYANOV')
    assert not j.is_admin('engineer')
    assert not j.is_admin('persiyanov2')


@pytest.mark.parametrize('url',[
    'http://script.google.com/macros/s/abc/exec',
    'https://example.com/macros/s/abc/exec',
    'https://script.google.com.evil/macros/s/abc/exec',
    'https://script.google.com/macros/s/abc/exec?token=secret',
    'https://script.google.com/macros/s/abc/dev',
])
def test_token_can_only_be_sent_to_deployed_google_endpoint(url):
    with pytest.raises(ValueError):j.validate_url(url)


def test_canonical_scope_and_url():
    assert j.scope_key('P','KR','model')=='{"model":"model","project":"P","role":"KR"}'
    assert j.validate_url('https://script.google.com/macros/s/abc-123_X/exec')


def test_plaintext_token_is_never_saved(monkeypatch):
    class Store:
        data={}
        def read(self):return copy.deepcopy(self.data)
        def write(self,v):
            self.data=v
            return True
    store=Store()
    monkeypatch.setattr(j,'connection_store',lambda:store)
    monkeypatch.setattr(j,'crypt',lambda text,decrypt=False:'cipher' if not decrypt else 'secret')
    j.save_connection('P','VIS','vis','https://script.google.com/macros/s/abc/exec','secret')
    assert 'secret' not in c.dumps(store.data)
    assert j.load_connection('P','VIS','vis')['token']=='secret'


def test_queue_preserves_each_release_and_reissue_without_tokens():
    data=j.snapshot(registry(),'P','VIS','vis','Name')
    items=j.enqueue([],data)
    assert j.enqueue(items,data)==items
    data['tasks']['a']['revision']=2
    items=j.enqueue(items,data)
    assert len(items)==2
    assert [c.loads(i['payload'])['tasks']['a']['revision'] for i in items]==[1,2]
    assert all('token' not in i for i in items)
    assert items[0]['id']!=items[1]['id']


def test_failed_revision_blocks_later_revisions_but_not_other_models():
    data=j.snapshot(registry(),'P','VIS','vis','Name')
    items=j.enqueue([],data)
    data['tasks']['a']['revision']=2
    items=j.enqueue(items,data)
    other=j.snapshot(registry(),'P','KR','kr','KR')
    items=j.enqueue(items,other)
    attempts=[]
    def send(item):
        attempts.append(item['id'])
        if item['scope']['role']=='VIS':
            raise IOError('offline')
    sent,blocked=j.deliver(items,send)
    assert attempts==[items[0]['id'],items[2]['id']]
    assert sent==[items[2]['id']]
    assert len(blocked)==1
    retry=[]
    sent,blocked=j.deliver(items[:2],lambda i:retry.append(i['id']))
    assert retry==[items[0]['id'],items[1]['id']]
    assert sent==retry and not blocked


def test_manual_publish_is_removed_from_manifest():
    from lowlife import opening_tasks_manifest as m
    for role in ('VIS','KR','AR'):
        with pytest.raises(ValueError):m.validate_action(role,'journal')


def test_background_drain_keeps_failed_items_and_concurrent_additions():
    from contextlib import nullcontext
    data=j.snapshot(registry(),'P','VIS','vis','Name')
    first=j.enqueue([],data)[0]
    second=dict(first,id='next')
    class Store:
        data={'items':[first]}
        def read(self):return copy.deepcopy(self.data)
        def write(self,value,notify=True):
            assert notify is False
            self.data=copy.deepcopy(value)
            return True
    store=Store()
    sent,blocked=j.drain_pending(store,lambda item:(_ for _ in ()).throw(IOError('offline')),nullcontext)
    assert sent==[] and blocked
    assert store.data['items']==[first]
    def success(item):
        store.data['items'].append(second)
    sent,blocked=j.drain_pending(store,success,nullcontext)
    assert sent==[first['id']] and not blocked
    assert store.data['items']==[second]


def test_failed_background_acknowledgement_leaves_item_for_idempotent_retry():
    from contextlib import nullcontext
    item=j.enqueue([],j.snapshot(registry(),'P','VIS','vis','Name'))[0]
    class Store:
        def read(self):return {'items':[item]}
        def write(self,value,notify=True):
            assert notify is False
            return False
    store=Store()
    calls=[]
    j.drain_pending(store,lambda i:calls.append(i['id']),nullcontext)
    j.drain_pending(store,lambda i:calls.append(i['id']),nullcontext)
    assert calls==[item['id'],item['id']]
    assert store.read()['items']==[item]


def test_process_timer_is_singleton_and_retries_without_window(monkeypatch):
    import sys
    import types
    from contextlib import nullcontext
    class Domain:
        data={}
        def GetData(self,key):return self.data.get(key)
        def SetData(self,key,value):self.data[key]=value
    domain=Domain()
    timers=[]
    def timer(callback,state,due,period):
        timers.append((callback,state,due,period))
        return object()
    monkeypatch.setitem(sys.modules,'System',types.SimpleNamespace(AppDomain=types.SimpleNamespace(CurrentDomain=domain)))
    monkeypatch.setitem(sys.modules,'System.Threading',types.SimpleNamespace(Timer=timer,TimerCallback=lambda f:f))
    monkeypatch.setattr(j,'QueueLock',lambda key:nullcontext())
    j.install_sender()
    j.install_sender()
    assert len(timers)==1
    callback,state,due,period=timers[0]
    assert due==period==60000
    attempts=[]
    monkeypatch.setattr(j,'retry_pending',lambda:attempts.append(True))
    callback(None)
    callback(None)
    assert attempts==[True,True]


def test_shared_connection_is_reused_across_models_but_not_projects_or_roles(monkeypatch):
    class Store:
        data={}
        def read(self):return copy.deepcopy(self.data)
        def write(self,value):
            self.data=value
            return True
    config=Store()
    monkeypatch.setattr(j,'connection_store',lambda:config)
    monkeypatch.setattr(j,'crypt',lambda text,decrypt=False:'shared-token' if decrypt else 'encrypted')
    url='https://script.google.com/macros/s/group/exec'
    j.save_connection('P','VIS','model1',url,'token',shared=True)
    assert j.load_connection('P','VIS','model1')['token']=='shared-token'
    assert j.load_connection('P','VIS','model2')['token']=='shared-token'
    with pytest.raises(ValueError):j.load_connection('OTHER','VIS','model2')
    with pytest.raises(ValueError):j.load_connection('P','KR','model2')


def test_windows_identity_and_queued_actor_are_preserved(monkeypatch):
    monkeypatch.setenv('USERNAME','ivanov')
    monkeypatch.setenv('USERDOMAIN','BUREAU')
    assert j.windows_user()=='BUREAU\\ivanov'
    data=j.snapshot(registry(),'P','VIS','vis','Name',revit_user='Revit Ivanov',windows_user=j.windows_user())
    item=j.enqueue([],data)[0]
    data['revit_user']='Another user'
    assert c.loads(item['payload'])['revit_user']=='Revit Ivanov'
    assert c.loads(item['payload'])['windows_user']=='BUREAU\\ivanov'


def test_global_group_connection_works_for_all_projects_and_models(monkeypatch):
    class Store:
        data={}
        def read(self):return copy.deepcopy(self.data)
        def write(self,value):
            self.data=value
            return True
    config=Store()
    monkeypatch.setattr(j,'connection_store',lambda:config)
    monkeypatch.setattr(j,'crypt',lambda text,decrypt=False:'token' if decrypt else 'encrypted')
    j.save_connection('P','VIS','model','https://script.google.com/macros/s/g/exec','token',
                      shared=True,all_projects=True)
    assert j.load_connection('P','VIS','model')['token']=='token'
    assert j.load_connection('OTHER','VIS','another-model')['token']=='token'
    with pytest.raises(ValueError):j.load_connection('OTHER','KR','another-model')


def test_saved_discipline_is_returned_with_shared_credentials(monkeypatch):
    value={'url':'https://script.google.com/macros/s/g/exec','token_dpapi':'encrypted','discipline':u'ВК'}
    monkeypatch.setattr(j,'connection_value',lambda *a:value)
    monkeypatch.setattr(j,'crypt',lambda *a:'token')
    assert j.load_connection('P','VIS','model')['discipline']==u'ВК'


def test_department_is_discovered_from_token_without_user_role_or_discipline(monkeypatch):
    captured=[]
    def request(connection,action,payload,track=False):
        captured.append((action,payload,track))
        return dict(department=u'ОВиК',role='VIS',credential_scope='group',sheet_url='sheet')
    monkeypatch.setattr(j,'request',request)
    value=j.discover_connection('https://script.google.com/macros/s/d/exec','secret',track=True)
    assert captured==[('connect',{},True)]
    assert value['department']==value['discipline']==u'ОВиК'
    with pytest.raises(ValueError):
        j.discover_connection('https://script.google.com/macros/s/d/exec','secret',role='KR')


def test_discovery_rejects_unknown_department_and_legacy_scope_mismatch(monkeypatch):
    response=dict(department=u'ВК',role='VIS',credential_scope='project_group',project='P')
    monkeypatch.setattr(j,'request',lambda *a,**kw:dict(response))
    url='https://script.google.com/macros/s/d/exec'
    assert j.discover_connection(url,'token',role='VIS',project='P')['department']==u'ВК'
    with pytest.raises(ValueError):j.discover_connection(url,'token',role='VIS',project='OTHER')
    response.update(department='UNKNOWN')
    with pytest.raises(ValueError):j.discover_connection(url,'token')
