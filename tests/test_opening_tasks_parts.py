# -*- coding: utf-8 -*-
import copy
import pytest
from lowlife import opening_tasks_parts as p
from lowlife import opening_tasks_core as c
from lowlife import opening_tasks_browser as browser


def draft(part=None):
    data=dict(task_id='a',source_model='vis',source_uid='route',owner_uid='box',
              geometry=dict(kind='wall',center_mm=[0,0,1000],size_mm=[300,200,300],x_dir=[1,0,0],
                            host_uid='wall',host_model='kr'))
    if part is not None:data['object_part']=part
    return data


def test_part_is_issued_snapshot_and_cannot_change_on_reissue():
    registry,_=c.issue(c.empty_registry(),[draft(u'НЧ-1')],'P','OV','user','t1')
    assert registry['issues'][0]['tasks'][0]['object_part']==u'НЧ-1'
    again,changed=c.issue(registry,[draft(u'НЧ-1')],'P','OV','user','t2')
    assert not changed
    with pytest.raises(ValueError):c.issue(registry,[draft(u'ПЧ-1')],'P','OV','user','t2')
    with pytest.raises(ValueError):c.issue(registry,[draft()],'P','OV','user','t2')
    assert registry['tasks']['a']['revision']==1


def test_explicit_legacy_assignment_creates_revision_and_preserves_history():
    registry,_=c.issue(c.empty_registry(),[draft()],'P','OV','user','t1')
    updated,changed=c.issue(registry,[draft(u'НЧ-2')],'P','OV','user','t2')
    assert changed[0]['revision']==2
    assert updated['tasks']['a']['object_part']==u'НЧ-2'
    assert 'object_part' not in updated['issues'][0]['tasks'][0]


def test_cached_choices_are_project_scoped_and_selection_model_scoped(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    assert p.store().write({'catalogs':{'P':[u'НЧ',u'ПЧ',u'НЧ-01']}})
    assert p.catalog('OTHER')==[]
    p.select('P','VIS','model1',u'НЧ-01')
    assert p.selection('P','VIS','model1')==u'НЧ-01'
    assert p.selection('P','VIS','model2')==''
    assert p.selection('P','KR','model1')==''
    assert p.require_choice('P',u'НЧ-01')==u'НЧ-01'
    with pytest.raises(ValueError):p.require_choice('P',u'НЧ-02')
    with pytest.raises(ValueError):p.require_choice('P','')
    p.store().write({'catalogs':{'P':[u'ПЧ']}})
    with pytest.raises(ValueError):p.require_choice('P',u'НЧ-01')


@pytest.mark.parametrize('label',[u'НЧ',u'ПЧ',u'НЧ-1',u'ПЧ-02',u'НЧ-А'])
def test_catalog_labels(label):
    assert p.valid_label(label)


def test_part_filter_separates_records_without_reassigning_them():
    rows=[dict(object_part=u'НЧ-1',search_text=''),dict(object_part=u'ПЧ-1',search_text='')]
    original=copy.deepcopy(rows)
    assert browser.select_rows(rows,{'object_part':u'НЧ-1'})==rows[:1]
    assert rows==original


def test_merging_requires_same_part_even_for_one_physical_host():
    assert c.common_part([draft(u'НЧ-1'),draft(u'НЧ-1')])==u'НЧ-1'
    assert c.common_part([draft(),draft()])==''
    with pytest.raises(ValueError):c.common_part([draft(u'НЧ-1'),draft(u'ПЧ-1')])
    with pytest.raises(ValueError):c.common_part([draft(),draft(u'НЧ-1')])


def test_catalog_reuses_background_helper_and_preserves_cache_on_error(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace as NS
    from lowlife import opening_tasks_journal as journal
    monkeypatch.setenv('APPDATA',str(tmp_path))
    callbacks=[]
    monkeypatch.setattr(journal,'in_background',lambda w,work,done:callbacks.append((work,done)))
    monkeypatch.setattr(journal,'load_connection',lambda *a:{'url':'url','token':'secret'})
    network=[]
    def request(connection,action,scope,track=False):
        network.append((action,scope,track))
        return {'parts':[u'НЧ-1',u'ПЧ-2',u'НЧ-1','invalid']}
    monkeypatch.setattr(journal,'request',request)
    updated=[]
    window=NS(role='VIS',model_uid='model',project_code='P',parts_loading=False,
              closed=False,load_parts=lambda:updated.append(True))
    p.fetch(window,{'opening_project':'P'})
    assert network==[] and window.parts_loading
    work,done=callbacks.pop()
    done(work(),None)
    assert network==[('catalog',{'project':'P','role':'VIS','model':'model'},True)]
    assert p.catalog('P')==[u'НЧ-1',u'ПЧ-2']
    assert not window.parts_loading and updated==[True]
    p.fetch(window,{'opening_project':'P'})
    work,done=callbacks.pop()
    done(None,'offline')
    assert p.catalog('P')==[u'НЧ-1',u'ПЧ-2']
