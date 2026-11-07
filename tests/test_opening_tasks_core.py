# -*- coding: utf-8 -*-
import copy
import math
import pytest
from lowlife import opening_tasks_core as c


def geometry(center=(0,0,1000), size=(400,200,300), kind='wall', host='wall1', axis=(1,0,0)):
    return dict(kind=kind,center_mm=list(center),size_mm=list(size),x_dir=list(axis),host_uid=host,host_model='kr1')


def draft(tid='a', g=None):
    return dict(task_id=tid,source_model='vis1',source_uid='pipe1',owner_uid='box1',geometry=g or geometry())


def issued(drafts=None, registry=None, time='t1'):
    return c.issue(registry or c.empty_registry(),drafts or [draft()],'P','OV','author',time)


def test_release_is_snapshot_and_not_live_geometry():
    original = c.empty_registry()
    d = draft()
    registry, changes = issued([d],original)
    d['geometry']['center_mm'][0] = 100
    assert not original['tasks']
    assert registry['tasks']['a']['geometry']['center_mm'][0] == 0
    registry['tasks']['a']['geometry']['center_mm'][0] = 200
    assert registry['issues'][0]['tasks'][0]['geometry']['center_mm'][0] == 0


def test_unchanged_issue_is_idempotent_and_keeps_dates():
    registry, _ = issued()
    again, changes = issued(registry=registry,time='t2')
    assert not changes
    assert again == registry


def test_changed_issue_preserves_guid_created_at_and_history():
    registry, _ = issued()
    d = draft(g=geometry(center=(5,0,1000)))
    next_registry, changes = issued([d],registry,'t2')
    assert changes[0]['task_id'] == 'a'
    assert changes[0]['revision'] == 2
    assert changes[0]['created_at'] == 't1'
    assert changes[0]['issued_at'] == 't2'
    assert len(next_registry['issues']) == 2
    assert next_registry['issues'][0]['tasks'][0]['geometry']['center_mm'][0] == 0


def test_selected_scope_does_not_withdraw_unselected_or_deleted_boxes():
    registry,_ = issued([draft('a'),draft('b')])
    result,changes = issued([draft('a')],registry)
    assert not changes
    assert result['tasks']['b']['status'] == 'issued'


def test_explicit_withdrawal_preserves_geometry_and_history():
    registry,_ = issued()
    withdrawn, changes = c.withdraw(registry,['a'],'who','t2')
    record = withdrawn['tasks']['a']
    assert record['status']=='withdrawn' and record['revision']==2
    assert record['geometry']==registry['tasks']['a']['geometry']
    assert registry['tasks']['a']['status']=='issued'
    assert withdrawn['issues'][0]['tasks'][0]['status']=='issued'
    repeat,changes=c.withdraw(withdrawn,['a'],'who','t3')
    assert not changes and repeat==withdrawn
    reissued,changes=issued(registry=withdrawn,time='t4')
    assert changes[0]['revision']==3 and changes[0]['status']=='issued'


def test_duplicate_guid_and_identity_conflicts_fail_before_publication():
    with pytest.raises(ValueError):
        issued([draft(),draft()])
    registry,_=issued()
    d=draft();d['source_model']='other'
    with pytest.raises(ValueError):
        issued([d],registry)
    with pytest.raises(ValueError):
        c.issue(registry,[draft()],'another-project','OV','who','t2')


def test_geometry_tolerance_and_orientation():
    assert c.geometry_equal(geometry(),geometry(center=(0.05,0,1000)))
    assert not c.geometry_equal(geometry(),geometry(center=(0.2,0,1000)))
    assert not c.geometry_equal(geometry(),geometry(axis=(0,1,0)))
    assert not c.geometry_equal(geometry(),geometry(host='wall2'))


@pytest.mark.parametrize('g',[
    geometry(size=(0,200,300)),geometry(size=(-1,200,300)),
    geometry(center=(float('nan'),0,0)),geometry(size=(float('inf'),1,1)),
    geometry(axis=(0,0,1)),geometry(axis=(2,0,0)),geometry(kind='beam'),
])
def test_invalid_geometry_rejected(g):
    with pytest.raises(ValueError):
        issued([draft(g=g)])


def test_merge_same_host_contains_all_boxes_and_keeps_height():
    merged=c.merge_geometry([geometry(),geometry(center=(500,0,1100))])
    assert merged['size_mm']==[900,200,400]
    assert merged['center_mm']==[250,0,1050]
    assert merged['host_uid']=='wall1'


def test_merge_in_rotated_host_frame():
    axis=(math.sqrt(.5),math.sqrt(.5),0)
    g=geometry(axis=axis)
    h=geometry(center=(500*axis[0],500*axis[1],1000),axis=axis)
    result=c.merge_geometry([g,h])
    assert result['size_mm']==pytest.approx([900,200,300])
    assert result['center_mm']==pytest.approx([250*axis[0],250*axis[1],1000])


def test_merge_floor_depth_and_incompatible_hosts():
    result=c.merge_geometry([geometry(kind='floor'),geometry(kind='floor',center=(0,500,1000))])
    assert result['size_mm']==[400,700,300]
    for other in [geometry(host='other'),geometry(kind='floor'),geometry(axis=(0,1,0))]:
        with pytest.raises(ValueError):
            c.merge_geometry([geometry(),other])


def test_receipt_is_revision_specific_and_deleted_opening_requires_review():
    registry,_=issued();r=registry['tasks']['a'];key=c.task_key(r)
    receipt=dict(status='accepted',revisions={key:1})
    assert c.incoming_state(r,None)=='new'
    assert c.incoming_state(r,receipt)=='accepted'
    assert c.incoming_state(r,receipt,False)=='missing_opening'
    changed=copy.deepcopy(r);changed['revision']=2
    assert c.incoming_state(changed,receipt)=='changed'
    changed['status']='withdrawn'
    assert c.incoming_state(changed,receipt)=='withdrawn'


def test_json_roundtrip_schema_and_nonfinite_values():
    registry,_=issued()
    assert c.loads(c.dumps(registry))==registry
    with pytest.raises(ValueError):
        c.loads('{"schema":2}')
    with pytest.raises(ValueError):
        c.dumps(dict(schema=1,value=float('nan')))


def test_change_report_distinguishes_movement_and_size():
    registry,_=issued();old=registry['tasks']['a']
    new=copy.deepcopy(old)
    new['geometry']['center_mm'][1]+=5
    assert c.change_kinds(old,new)==['moved']
    new['geometry']['size_mm'][0]+=100
    assert c.change_kinds(old,new)==['moved','resized']
    assert c.change_kinds(None,new)==['new']


def test_human_numbers_are_unique_and_stable_across_revisions():
    registry,changes=issued([draft('a'),draft('b')])
    assert [r['task_number'] for r in changes]==[1,2]
    changed=draft('a',geometry(center=(10,0,1000)))
    updated,changes=issued([changed,draft('c')],registry,'t2')
    assert [r['task_number'] for r in changes]==[1,3]
    assert updated['tasks']['b']['task_number']==2


def test_issue_and_withdraw_keep_actor_identity_in_event_snapshots():
    r,changes=c.issue(c.empty_registry(),[draft()],'P','OV','Revit-user','t1',windows_user='DOMAIN\\first')
    assert r['issues'][0]['tasks'][0]['revit_user']=='Revit-user'
    assert r['issues'][0]['tasks'][0]['windows_user']=='DOMAIN\\first'
    r,changes=c.withdraw(r,['a'],'Other-Revit','t2',windows_user='DOMAIN\\second')
    assert changes[0]['windows_user']=='DOMAIN\\second'
    assert r['issues'][0]['tasks'][0]['windows_user']=='DOMAIN\\first'
