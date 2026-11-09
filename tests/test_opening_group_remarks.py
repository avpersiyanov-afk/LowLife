# -*- coding: utf-8 -*-
import copy
import pytest
from lowlife import opening_tasks_core as core
from lowlife import opening_tasks_remarks as r
from lowlife import opening_tasks_journal as journal


def task(model='OV',tid='1',revision=1,recipient='KR'):
    return dict(source_model=model,task_id=tid,revision=revision,status='issued',project='P',recipient=recipient,
                object_part='НЧ-1',geometry=dict(host_model='RECEIVER',host_uid='wall'))


def create(registry,records,recipient='KR'):
    return r.create(registry,records,'P',recipient,'RECEIVER','Move clear of column','Reviewer','2026-11-09T12:00:00Z','BUREAU\\reviewer')


def test_one_remark_across_disciplines_keeps_individual_revisions_and_history():
    source=core.empty_registry();before=copy.deepcopy(source)
    records=[task('OV'),task('VK',revision=2),task('EOM')]
    result,group=create(source,records)
    assert source==before
    assert group['number']=='КР-ЗМ-001'
    assert group['revisions']=={'OV/1':1,'VK/1':2,'EOM/1':1}
    assert len(result['decisions'])==3
    for record in records:
        reply=result['receipts'][core.task_key(record)]
        assert reply['remark_group_id']==group['id']
        assert group['number'] in reply['comment']
        assert r.state(record,reply,group)=='correction'
    snapshot=journal.snapshot(result,'P','KR','RECEIVER','KR model')
    assert snapshot['decisions'][0]['remark_group']['id']==group['id']
    assert r.group_state(group,result['receipts'])=='open'


def test_partial_acceptance_does_not_close_group_and_reissue_requires_review():
    records=[task('OV'),task('VK')]
    result,group=create(core.empty_registry(),records)
    receipts=result['receipts']
    updated=task('OV',revision=2)
    assert r.state(updated,receipts['OV/1'],group)=='review'
    receipts['OV/1']=dict(status='accepted',revisions={'OV/1':2})
    assert r.state(updated,receipts['OV/1'],group)=='closed'
    assert r.group_state(group,receipts)=='open'
    receipts['VK/1']=dict(status='accepted',revisions={'VK/1':1})
    assert r.group_state(group,receipts)=='closed'
    assert r.group_state(group,receipts,{'VK/1':task('VK',revision=2)})=='open'
    assert r.group_state(group,receipts,verified=lambda reply:False)=='open'
    assert r.latest_by_task(result,'P','KR')['OV/1']['id']==group['id']


def test_group_remark_preserves_existing_merged_opening_and_requires_all_members():
    records=[task('OV'),task('VK')]
    old=dict(status='accepted',opening_uid='opening',opening_id='opening-guid',geometry={'host_model':'RECEIVER'},
             revisions={'OV/1':1,'VK/1':1})
    registry=dict(receipts={'OV/1':old,'VK/1':old},tasks={},issues=[])
    with pytest.raises(ValueError):create(registry,records[:1])
    result,group=create(registry,records)
    assert len(result['decisions'])==1
    reply=result['receipts']['OV/1']
    assert reply['opening_uid']=='opening' and reply['revisions']==old['revisions']
    assert result['receipts']['VK/1'] is reply
    assert reply['status']=='rejected'


def test_explicit_withdrawal_and_receiver_processing_close_member():
    record=task();result,group=create(core.empty_registry(),[record])
    record.update(status='withdrawn',revision=2)
    assert r.state(record,result['receipts']['OV/1'],group)=='withdraw_pending'
    reply=dict(status='withdrawn',revisions={'OV/1':2})
    assert r.state(record,reply,group)=='closed'
    assert r.group_state(group,{'OV/1':reply},{'OV/1':record})=='closed'
    assert r.group_state(group,{'OV/1':reply},{'OV/1':task(revision=2)})=='open'


def test_ar_and_kr_groups_do_not_mix_and_same_timestamp_keeps_latest_sequence():
    result,first=create(core.empty_registry(),[task()])
    result,second=create(result,[task()])
    assert second['number']=='КР-ЗМ-002'
    assert r.latest_by_task(result,'P','KR')['OV/1']['id']==second['id']
    result,ar=create(result,[task(recipient='AR')],'AR')
    assert ar['number']=='АР-ЗМ-001'
    assert r.latest_by_task(result,'P','KR')['OV/1']['id']==second['id']
    assert r.latest_by_task(result,'P','AR')['OV/1']['id']==ar['id']
    with pytest.raises(ValueError):create(result,[task(recipient='AR')])


def test_empty_comment_withdrawn_records_and_wrong_host_are_rejected_without_mutation():
    registry=core.empty_registry()
    with pytest.raises(ValueError):r.create(registry,[task()],'P','KR','RECEIVER',' ','a','t')
    withdrawn=task();withdrawn['status']='withdrawn'
    with pytest.raises(ValueError):create(registry,[withdrawn])
    with pytest.raises(ValueError):r.create(registry,[task()],'P','KR','OTHER','text','a','t')
    assert registry==core.empty_registry()


def test_vis_feedback_shares_group_number_and_waits_for_kr_review():
    import ast
    from pathlib import Path
    from types import SimpleNamespace as NS
    ov=task('OV');vk=task('VK')
    remote,group=create(core.empty_registry(),[ov,vk])
    own={'tasks':{'1':ov}}
    read=[]
    receiver=NS(model='RECEIVER',GetElement=lambda uid:NS(UniqueId=uid))
    def accepted(key,revision):
        return dict(project='P',status='accepted',revisions={key:revision},opening_uid='opening-'+key,
                    opening_id='id-'+key,geometry={'host_model':'RECEIVER'})
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_revit.py'
    tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='recipient_feedback')
    ns=dict(store=NS(model_id=lambda doc:doc.model,registry=lambda doc:remote),
            core=core,FilteredElementCollector=lambda doc:NS(OfClass=lambda cls:[NS(GetLinkDocument=lambda:receiver)]),
            RevitLinkInstance=object,opening_matches=lambda opening,receipt:read.append(opening.UniqueId) or True,
            unicode=str,tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    def feedback():return ns['recipient_feedback'](NS(model='OV'),'P',registry=own)['OV/1']
    assert feedback()['remark_state']=='correction'
    assert feedback()['remark_number']==group['number']
    own['tasks']['1']=dict(ov,revision=2)
    assert feedback()['remark_state']=='review'
    remote['receipts']['OV/1']=accepted('OV/1',2)
    assert feedback()['remark_state']=='closed'
    assert feedback()['remark_group_state']=='open'
    remote['receipts']['VK/1']=accepted('VK/1',1)
    read[:]=[]
    assert feedback()['remark_group_state']=='closed'
    assert sorted(read)==['opening-OV/1','opening-VK/1']


def test_group_payload_does_not_repeat_full_membership_in_every_receipt():
    sizes=[]
    for count in (10,20):
        result,group=create(core.empty_registry(),[task('OV',str(i)) for i in range(count)])
        assert sum('remark_group' in receipt for receipt in result['decisions'])==1
        assert all('remark_group' not in receipt for receipt in result['receipts'].values())
        snapshot=journal.snapshot(result,'P','KR','RECEIVER','KR')
        assert snapshot['remark_groups'][group['id']]['revisions']==group['revisions']
        sizes.append(len(core.dumps(snapshot)))
    assert sizes[1]<sizes[0]*2.5


def test_group_rejection_updates_merged_opening_metadata_once_without_geometry_edits():
    import ast
    from pathlib import Path
    from types import SimpleNamespace as NS
    records=[task('OV'),task('VK')]
    old=dict(status='accepted',opening_uid='opening',opening_id='stable-id',
             geometry={'host_model':'RECEIVER'},revisions={'OV/1':1,'VK/1':1})
    registry=dict(receipts={'OV/1':old,'VK/1':old},tasks={},issues=[])
    opening=object();writes=[];saved=[]
    doc=NS(Application=NS(Username='Reviewer'),GetElement=lambda uid:opening)
    store=NS(registry=lambda doc:registry,model_id=lambda doc:'RECEIVER',
             write=lambda opening,data:writes.append(data),save_registry=lambda doc,data:saved.append(data))
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_revit.py'
    tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='reject')
    ns=dict(core=core,store=store,now=lambda:'now',windows_user=lambda:'Reviewer')
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    group=ns['reject'](doc,records,{'opening_project':'P'},'Comment',grouped=True)
    assert len(writes)==1 and writes[0]['status']=='rejected'
    assert writes[0]['opening_id']=='stable-id'
    assert saved[0]['remark_groups'][group['id']]['revisions']=={'OV/1':1,'VK/1':1}
