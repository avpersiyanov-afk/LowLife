"""Modeless table interactions execute API work only through external events."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

ROOT=Path(__file__).parents[1]


def method(name,scope):
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_window.py').read_text())
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'table','exec'),scope)
    return scope[name]


class Generic:
    def __class_getitem__(cls,t):return list


def test_selection_handler_uses_latest_rows_and_does_no_refresh_or_zoom():
    scope=dict(List=Generic,ElementId=int)
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_window.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SelectionHandler')
    fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='Execute')
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'selection-api','exec'),scope)
    updates=[]
    doc=NS(GetElement=lambda uid: {'a':NS(Id=1),'b':NS(Id=2)}.get(uid))
    current=[]
    def select(ids):
        current[:]=ids;updates.append(list(ids))
    uidoc=NS(Document=doc,Selection=NS(GetElementIds=lambda:current,SetElementIds=select))
    window=NS(closed=False,document=doc,selection_uids=['a'])
    handler=NS(window=window)
    window.selection_uids=['b','deleted']  # latest selection before Revit processes event
    scope['Execute'](handler,NS(ActiveUIDocument=uidoc))
    assert updates==[[2]]
    scope['Execute'](handler,NS(ActiveUIDocument=uidoc))
    assert updates==[[2]]  # no redundant native selection call
    scope['Execute'](handler,NS(ActiveUIDocument=NS(Document=object())))
    window.closed=True
    scope['Execute'](handler,NS(ActiveUIDocument=uidoc))
    assert updates==[[2]]


def test_selection_queue_is_coalesced_and_ignored_for_render_or_other_role():
    raises=[]
    rows=[dict(uid='a')]
    window=NS(role='VIS',closed=False,rendering=False,selection_event=NS(Raise=lambda:raises.append('raise')),
              selected_rows=lambda:rows,selection_uids=[])
    queue=method('queue_model_selection',{})
    queue(window)
    rows[:]=[dict(uid='b'),dict(uid='c')]
    queue(window)
    assert window.selection_uids==['b','c']
    window.rendering=True;queue(window)
    window.rendering=False;window.role='KR';queue(window)
    assert raises==['raise','raise']


def test_building_dropdown_ignores_binding_initialization_then_dispatches_single_row():
    row=dict(uid='box',object_part='old')
    calls=[]
    def dispatch(action,rows):
        calls.append((action,rows));return True
    window=NS(parts_updating=False,rendering=False,pending=None,closed=False,
              building_choices=['old','new'],visible={'key':row},tasks=NS(),dispatch=dispatch,pending_part=None)
    sender=NS(SelectedItem='old',DataContext={'Key':'key'})
    changed=method('building_cell_changed',dict(unicode=str))
    changed(window,sender,None)
    assert calls==[]
    sender.SelectedItem='new'
    changed(window,sender,None)
    assert calls==[('change_part',[row])] and window.pending_part=='new'
    assert row['object_part']=='old'  # one-way cell binding; data changes in API callback
    calls[:]=[]
    window.pending=('other',[])
    changed(window,sender,None)
    assert calls==[]


def test_rejected_inline_dispatch_restores_cell_value():
    row=dict(uid='box',object_part='old')
    window=NS(parts_updating=False,rendering=False,pending=None,closed=False,
              building_choices=['old','new'],visible={'key':row},tasks=NS(),dispatch=lambda *a,**kw:False,pending_part=None)
    sender=NS(SelectedItem='new',DataContext={'Key':'key'})
    method('building_cell_changed',dict(unicode=str))(window,sender,None)
    assert sender.SelectedItem=='old' and window.pending_part is None


def test_inline_building_value_bypasses_second_picker_and_uses_validated_api():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_ui.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='change_building_from_table')
    fn.body=[n for n in fn.body if not isinstance(n,ast.ImportFrom)]
    calls=[]
    box=object()
    doc=NS(GetElement=lambda uid:box)
    class Tx:
        def __init__(self,title):pass
        def __enter__(self):calls.append('transaction')
        def __exit__(self,*args):pass
    def no_picker(*args):raise AssertionError('inline cell value requires no picker')
    scope=dict(parts=NS(catalog=lambda project:['new'],require_choice=lambda project,value:calls.append(('validate',value)),
                        select=lambda *args:calls.append('remember')),
               choose=no_picker,revit=NS(Transaction=Tx),store=NS(model_id=lambda doc:'model'),
               api=NS(change_building=lambda doc,elements,value,settings:calls.append(('change',elements,value))),
               tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'inline-api','exec'),scope)
    scope['change_building_from_table'](NS(Document=doc),[dict(uid='box')],dict(opening_project='P'),value='new')
    assert calls==[('validate','new'),'transaction',('change',[box],'new'),'remember']


def test_cell_combo_events_do_not_trigger_model_selection():
    window=NS(tasks=object(),queue_model_selection=lambda:(_ for _ in ()).throw(AssertionError('cell event must not select')))
    method('selection_changed',{})(window,None,NS(OriginalSource=object()))
