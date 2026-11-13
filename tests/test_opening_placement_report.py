"""Placement failures remain readable even when no box was created."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


@pytest.mark.parametrize('count',[0,13])
def test_placement_report_exposes_every_reason_in_dialog_and_output(count):
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_ui.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    methods=[n for n in tree.body if isinstance(n,ast.FunctionDef)
             and n.name in ('report_errors','report_placement_result')]
    tables=[];shown=[];alerts=[]
    output=NS(print_md=lambda text:None,print_table=lambda rows,columns:tables.append(rows),
              linkify=lambda eid:'link:'+str(eid),show=lambda:shown.append(True))
    ns=dict(script=NS(get_output=lambda:output),forms=NS(alert=lambda text,**kw:alerts.append((text,kw))),
            boxes=NS(_id_int=lambda eid:eid),unicode=str,tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=methods,type_ignores=[]),str(path),'exec'),ns)
    errors=[(i,'reason '+str(i)) for i in range(count)]
    ns['report_placement_result'](0,errors)
    message,options=alerts[0]
    assert 'Created/updated: 0' in message
    if count:
        assert shown==[True]
        assert tables==[[['link:'+str(i),'reason '+str(i)] for i in range(count)]]
        assert options['expanded'].splitlines()==['ID {}: reason {}'.format(i,i) for i in range(count)]
    else:
        assert not shown and not tables and options['expanded'] is None
