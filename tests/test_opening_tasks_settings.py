# -*- coding: utf-8 -*-
from lowlife import opening_tasks_settings as settings


def test_first_run_requires_project_names_instead_of_embedding_them(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    vis=settings.make('VIS')
    values=vis.load_saved_values()
    assert values['opening_project']==''
    assert values['opening_discipline']==''
    assert values['opening_json_param']==''
    assert 'opening_json_param' in [f.key for f in vis.fields if f.required]
    assert values['size_extra_mm']==50.0
    assert values['opening_increase']=='none'
    assert 'box_source_model' not in values  # target is explicitly selected per placement


def test_kr_settings_do_not_require_a_box_family_or_json_binding():
    kr=settings.make('KR')
    assert {f.key for f in kr.fields}=={'opening_project','opening_json_param'}
    assert {f.key for f in kr.fields if f.required}=={'opening_project'}
