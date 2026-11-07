# -*- coding: utf-8 -*-
from lowlife import opening_tasks_settings as settings


def test_first_run_requires_project_names_instead_of_embedding_them(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    vis=settings.make('VIS')
    values=vis.load_saved_values()
    assert values['opening_project_param']==''
    assert values['opening_discipline']==''
    assert values['opening_json_param']==''
    assert 'opening_json_param' in [f.key for f in vis.fields if f.required]
    assert values['size_extra_mm']==50.0
    assert values['opening_increase']=='none'
    assert 'box_source_model' not in values  # target is explicitly selected per placement


def test_kr_settings_do_not_require_a_box_family_or_json_binding():
    kr=settings.make('KR')
    assert {f.key for f in kr.fields}=={'opening_project_param','opening_json_param'}
    assert {f.key for f in kr.fields if f.required}==set()


def test_ar_has_its_own_settings_store_and_only_receiver_fields(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    ar=settings.make('AR');kr=settings.make('KR')
    assert {f.key for f in ar.fields}=={'opening_project_param','opening_json_param'}
    assert ar.store.path()!=kr.store.path()
    assert ar.load_saved_values()['opening_project_param']==''


def test_project_code_reuses_notes_reference_without_network(monkeypatch):
    import sys
    import types
    calls=[]
    notes=types.SimpleNamespace(FILE_KEY='file',
        get_settings=lambda online:({'key_param':'Code [PROJECT_NUMBER]'},False),
        read_param=lambda doc,ref:calls.append(ref) or 'PROJECT')
    monkeypatch.setitem(sys.modules,'pnotes.core',notes)
    import pnotes
    monkeypatch.setattr(pnotes,'core',notes,raising=False)
    doc=types.SimpleNamespace(ProjectInformation=types.SimpleNamespace(Number='FALLBACK'))
    assert settings.for_document({'opening_project':'STALE'},doc)['opening_project']=='PROJECT'
    assert calls==['Code [PROJECT_NUMBER]']
    assert settings.for_document({'opening_project_param':'Custom code'},doc)['opening_project']=='PROJECT'
    assert calls[-1]=='Custom code'
    notes.get_settings=lambda online:({'key_param':'file'},False)
    assert settings.for_document({},doc)['opening_project']=='FALLBACK'


def test_installed_discipline_is_used_for_new_tasks(monkeypatch):
    from types import SimpleNamespace as NS
    from lowlife import opening_tasks_journal as journal
    monkeypatch.setattr(settings,'project_code',lambda doc,values:'P')
    monkeypatch.setattr(journal,'connection_value',lambda project,role,model:{'discipline':u'ОК'})
    doc=NS(ProjectInformation=NS(UniqueId='model'))
    assert settings.for_document({'opening_discipline':'OLD'},doc)['opening_discipline']==u'ОК'
    assert 'opening_discipline' not in settings.for_document({},doc)
    assert settings.make('VIS',doc).load_saved_values()['opening_discipline']==u'ОК'
