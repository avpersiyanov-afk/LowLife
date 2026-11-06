# -*- coding: utf-8 -*-
import copy
import pytest
from lowlife import opening_tasks_core as c
from lowlife import opening_tasks_preview_core as preview


def draft(i,kind='wall',model='visOV'):
    return dict(task_id='task'+str(i),source_model=model,source_uid='route'+str(i),owner_uid='box'+str(i),
                geometry=dict(kind=kind,host_model='KR',host_uid='host',x_dir=[1,0,0],
                              center_mm=[i*500,0,1000],size_mm=[400,200,300]))


def test_ten_tasks_from_two_disciplines_issue_and_receive_protocol():
    incoming=[]
    for discipline in ('OV','VK'):
        registry,records=c.issue(c.empty_registry(),[draft(i,model='vis'+discipline) for i in range(5)],'P',discipline,'who','t1')
        assert len(registry['issues'])==1
        incoming+=records
    assert len(set(c.task_key(r) for r in incoming))==10
    for record in incoming:
        assert c.incoming_state(record,None)=='new'
        receipt=dict(status='accepted',revisions={c.task_key(record):record['revision']})
        assert c.incoming_state(record,receipt)=='accepted'


def test_two_changed_tasks_and_merged_group_require_review():
    original=[draft(i) for i in range(5)]
    registry,records=c.issue(c.empty_registry(),original,'P','OV','who','t1')
    receipt=dict(status='accepted',revisions={c.task_key(r):r['revision'] for r in records[:2]})
    changed=copy.deepcopy(original)
    changed[0]['geometry']['center_mm'][0]+=100
    changed[1]['geometry']['size_mm'][0]+=100
    updated,changes=c.issue(registry,changed,'P','OV','who','t2')
    assert len(changes)==2
    group=[updated['tasks']['task0'],updated['tasks']['task1']]
    assert all(c.incoming_state(r,receipt)=='changed' for r in group)
    diagram=preview.project(group)
    assert diagram['geometry']['size_mm']==[850,200,300]
    assert len(diagram['rectangles'])==2
    assert not c.translation_only(records[1]['geometry'],group[1]['geometry'])
    assert c.translation_only(records[0]['geometry'],group[0]['geometry'])
    assert registry['issues'][0]['tasks'][0]['geometry']==original[0]['geometry']


def test_withdraw_one_member_preserves_other_members_and_history():
    registry,records=c.issue(c.empty_registry(),[draft(0),draft(1)],'P','OV','who','t1')
    result,withdrawn=c.withdraw(registry,['task0'],'who','t2')
    assert result['tasks']['task1']['status']=='issued'
    assert c.incoming_state(withdrawn[0],None)=='withdrawn'
    assert result['issues'][0]['tasks'][0]['status']=='issued'
    assert len(result['issues'])==2


def test_floor_preview_uses_width_and_depth_not_slab_thickness():
    a=draft(0,'floor');b=draft(1,'floor')
    diagram=preview.project([a,b])
    assert diagram['outline']==(-450,-100,900,200)
    assert diagram['rectangles'][0]==(-450,-100,400,200)
    with pytest.raises(ValueError):
        preview.project([a,draft(2,'wall')])
