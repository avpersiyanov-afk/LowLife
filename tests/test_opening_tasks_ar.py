# -*- coding: utf-8 -*-
import copy
import pytest
from lowlife import opening_tasks_core as c
from lowlife import opening_tasks_browser as browser


def task(tid,recipient):
    return dict(task_id=tid,source_model='VIS',source_uid='route',owner_uid='box'+tid,recipient=recipient,
                geometry=dict(kind='wall',center_mm=[0,0,1000],x_dir=[1,0,0],size_mm=[400,200,200],
                              host_uid='wall'+recipient,host_model='model'+recipient))


def test_independent_kr_and_ar_issues_keep_history_and_recipients():
    kr,changes=c.issue(c.empty_registry(),[task('kr','KR')],'P','OV','who','t1')
    ar,changes=c.issue(kr,[task('ar','AR')],'P','OV','who','t2',recipient='AR')
    assert ar['tasks']['kr']==kr['tasks']['kr']
    assert ar['tasks']['ar']['recipient']=='AR'
    assert ar['issues'][0]==kr['issues'][0]
    assert ar['issues'][1]['tasks'][0]['recipient']=='AR'
    c.check_recipient([ar['tasks']['ar']],'AR','P','modelAR')
    for role,model in [('KR','modelAR'),('AR','modelKR')]:
        with pytest.raises(ValueError):c.check_recipient([ar['tasks']['ar']],role,'P',model)


def test_issued_task_cannot_be_readdressed_even_when_geometry_matches():
    registry,_=c.issue(c.empty_registry(),[task('same','KR')],'P','OV','who','t1')
    changed=task('same','AR')
    with pytest.raises(ValueError):c.issue(registry,[changed],'P','OV','who','t2',recipient='AR')
    with pytest.raises(ValueError):c.issue(c.empty_registry(),[task('ar','AR')],'P','OV','who','t1')
    assert registry['tasks']['same']['revision']==1


def test_ar_receipts_and_rejection_do_not_overwrite_kr_decisions():
    registry=c.empty_registry()
    c.receipts(registry,'KR')['VIS/task']=dict(status='accepted',opening_uid='kr-opening')
    c.receipts(registry,'AR')['VIS/task']=dict(status='rejected',comment='AR note')
    assert registry['receipts']['VIS/task']['opening_uid']=='kr-opening'
    assert registry['ar_receipts']['VIS/task']['status']=='rejected'
    with pytest.raises(ValueError):c.receipts(registry,'unknown')


def test_ar_withdrawal_does_not_withdraw_kr_task():
    registry,_=c.issue(c.empty_registry(),[task('kr','KR')],'P','OV','who','t1')
    registry,_=c.issue(registry,[task('ar','AR')],'P','OV','who','t2',recipient='AR')
    withdrawn,_=c.withdraw(registry,['ar'],'who','t3')
    assert withdrawn['tasks']['kr']['status']=='issued'
    assert withdrawn['tasks']['ar']['status']=='withdrawn'


def test_legacy_kr_issues_and_recipient_filter_remain_supported():
    old=task('legacy','KR');old.pop('recipient')
    registry,_=c.issue(c.empty_registry(),[old],'P','OV','who','t1')
    c.check_recipient([registry['tasks']['legacy']],'KR','P','modelKR')
    rows=[dict(recipient='KR',search_text='OV'),dict(recipient='AR',search_text='OV')]
    assert browser.select_rows(rows,{'recipient':'AR'})==[rows[1]]
