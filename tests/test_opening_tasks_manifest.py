# -*- coding: utf-8 -*-
import ast
from pathlib import Path
import pytest
from lowlife import opening_tasks_manifest as m

ROOT=Path(__file__).parents[1]


def test_roles_have_disjoint_business_actions():
    vis={key for key,label in m.actions('VIS')}
    kr={key for key,label in m.actions('KR')}
    assert vis=={'place','place_ar','issue','issue_ar','confirm_ar','withdraw','confirm','focus','control'}
    assert kr=={'show','accept','merge','reject','remove','structures','kr_plans','kr_sections'}
    assert not vis.intersection(kr)
    for key in kr:
        with pytest.raises(ValueError):m.validate_action('VIS',key)
    for key in vis:
        with pytest.raises(ValueError):m.validate_action('KR',key)
    assert m.validate_action('VIS','refresh')=='refresh'
    assert m.validate_action('KR','settings')=='settings'


@pytest.mark.parametrize('role',['vis','ВИС','KR ','',None])
def test_invalid_role_never_falls_back_to_kr(role):
    with pytest.raises(ValueError):m.actions(role)


def test_ribbon_layout_and_scripts_match_role_manifest():
    panel=ROOT/'LowLife.tab/OpeningTasks.panel'
    layout=[line.strip()[2:] for line in (panel/'bundle.yaml').read_text().splitlines() if line.strip().startswith('- ')]
    assert set(layout)==set(m.INTERFACES.values())
    for role,folder in m.INTERFACES.items():
        path=panel/(folder+'.pushbutton')/'script.py'
        tree=ast.parse(path.read_text())
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='show']
        assert len(calls)==1
        assert ast.literal_eval(calls[0].args[0])==role
        text=(path.parent/'bundle.yaml').read_text()
        assert 'persistent: true' in text


def test_interface_reads_manifest_and_checks_both_dispatch_boundaries():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_window.py').read_text())
    methods={node.name:node for cls in tree.body if isinstance(cls,ast.ClassDef) for node in cls.body if isinstance(node,ast.FunctionDef)}
    def calls(node,name):
        return [n for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                and isinstance(n.func.value,ast.Name) and n.func.value.id=='manifest' and n.func.attr==name]
    assert calls(methods['Execute'],'validate_action')
    assert calls(methods['dispatch'],'validate_action')
    window=next(cls for cls in tree.body if isinstance(cls,ast.ClassDef) and cls.name=='TaskWindow')
    ctor=next(n for n in window.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    assert calls(ctor,'actions')


def test_ar_receiving_actions_are_separate_from_kr():
    ar={key for key,label in m.actions('AR')}
    assert ar=={'ar_show','ar_accept','ar_merge','ar_reject','ar_remove'}
    for role in ('VIS','KR'):
        for key in ar:
            with pytest.raises(ValueError):m.validate_action(role,key)
    assert dict(m.actions('KR'))['accept']==u'Принять задания КР'
    assert dict(m.actions('VIS'))['issue']==u'Выдать задания ВИС-КР'


def test_installer_uses_discipline_names_for_engineers_and_receivers():
    assert set(m.INSTALL_DISCIPLINES)=={u'ОВиК',u'ВК',u'ЭОМ',u'СС',u'АК',u'КР',u'АР'}
    assert all(m.INSTALL_DISCIPLINES[d]=='VIS' for d in (u'ОВиК',u'ВК',u'ЭОМ',u'СС',u'АК'))
    assert m.INSTALL_DISCIPLINES[u'КР']=='KR'
    assert m.INSTALL_DISCIPLINES[u'АР']=='AR'


def test_hvac_spelling_and_legacy_alias_resolve_to_same_discipline():
    assert m.canonical_discipline(u'ОВиК')==u'ОВиК'
    assert m.canonical_discipline(u'ОВИК')==u'ОВиК'
    assert m.canonical_discipline(u'ОК')==u'ОВиК'
    assert m.canonical_discipline(u'ВК')==u'ВК'
