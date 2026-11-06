# -*- coding: utf-8 -*-
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife.opening_tasks_names import safe_name


@pytest.mark.parametrize('value',[
    'LowLife | project | issued',u'КР:проект/модель [01] {стена}',
    'a\\b;c<d>e?f"g`h~i','\n\t\x00',u'Очень длинное имя '*80])
def test_generated_names_contain_no_prohibited_characters(value):
    result=safe_name(value)
    assert result and len(result)<=200
    assert not any(c in result for c in '\\:{}[]|;<>?"`~\n\t\x00')


def test_russian_names_are_preserved():
    assert safe_name(u'LowLife | Планы | Этаж 01')==u'LowLife - Планы - Этаж 01'
    assert safe_name(u'Отверстие 500 × 300')==u'Отверстие 500 × 300'


def test_unique_view_names_are_compared_after_sanitization():
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_views.py'
    fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='unique_name')
    # Replace only the local Revit type import; naming behavior stays intact.
    fn.body=[n for n in fn.body if not isinstance(n,ast.ImportFrom)]
    collector=NS(OfClass=lambda cls:[NS(Name='LowLife - Test'),NS(Name='LowLife - Test (2)')])
    ns=dict(View=object,FilteredElementCollector=lambda doc:collector,safe_name=safe_name)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    assert ns['unique_name'](None,'LowLife | Test')=='LowLife - Test (3)'


def test_focus_uses_host_view_when_kr_has_no_prepared_view():
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_focus.py'
    fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='link_visibility')
    ns=dict(LinkVisibility=NS(ByHostView='host',ByLinkView='linked'))
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    result=ns['link_visibility'](NS(),None)
    assert result.LinkVisibilityType=='host'
    result=ns['link_visibility'](NS(),NS(Id=42))
    assert result.LinkVisibilityType=='linked' and result.LinkedViewId==42
