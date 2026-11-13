"""Working building edits preserve released JSON/history until reissue."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import opening_tasks_core as core

ROOT=Path(__file__).parents[1]


def adapter():
    geometry=dict(kind='wall',center_mm=[0,0,1000],size_mm=[300,200,300],x_dir=[1,0,0],host_uid='wall',host_model='KR')
    draft=dict(task_id='issued',source_model='VIS',source_uid='route',owner_uid='box',geometry=geometry,object_part='old')
    registry,records=core.issue(core.empty_registry(),[draft],'P','OV','user','time')
    writes=[]
    doc=NS()
    def box(tid,uid):
        el=NS(Document=doc,UniqueId=uid,data=dict(schema=1,role='draft',task_id=tid,owner_uid=uid,source_model='VIS',object_part='old'))
        el.json=core.dumps(records[0] if tid=='issued' else dict(el.data,geometry=geometry))
        el.LookupParameter=lambda name:NS(StorageType='text',AsString=lambda:el.json)
        return el
    issued=box('issued','box');unissued=box('draft','draft-box')
    ns=dict(parts=NS(require_choice=lambda project,value: None if value=='new' else (_ for _ in ()).throw(ValueError('catalog'))),
            store=NS(registry=lambda doc:registry,model_id=lambda doc:'VIS',
                     write=lambda inst,data:(setattr(inst,'data',data),writes.append('metadata')),
                     set_parameter=lambda inst,name,data:(setattr(inst,'json',core.dumps(data)),writes.append('json'))),
            metadata=lambda el:el.data,StorageType=NS(String='text'),core=core,
            visible_issue=lambda inst,settings,record,changed:setattr(inst,'changed',changed),
            sync_selection_filters=lambda *args:None,tr=lambda ru,en=None:en or ru)
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_revit.py').read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='change_building')
    fn.body=[n for n in fn.body if not isinstance(n,ast.ImportFrom)]
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'building','exec'),ns)
    return ns['change_building'],doc,issued,unissued,registry,writes


def test_draft_metadata_changes_but_official_issue_remains_until_reissued():
    change,doc,issued,unissued,registry,writes=adapter()
    before=copy.deepcopy(registry)
    released=issued.json
    count=change(doc,[issued,unissued],'new',dict(opening_project='P',opening_json_param='JSON',opening_status_param='Status'))
    assert count==2 and registry==before
    assert issued.data['object_part']=='new' and issued.json==released and issued.changed
    assert core.loads(unissued.json)['object_part']=='new' and not unissued.changed
    assert core.loads(unissued.json)['geometry']['size_mm']==[300,200,300]


def test_invalid_selection_or_catalog_is_rejected_before_any_writes():
    change,doc,issued,unissued,registry,writes=adapter()
    copied=NS(Document=doc,UniqueId='copy',data=dict(issued.data))
    settings=dict(opening_project='P',opening_json_param='JSON')
    with pytest.raises(ValueError):change(doc,[issued,copied],'new',settings)
    assert writes==[] and issued.data['object_part']=='old'
    with pytest.raises(ValueError):change(doc,[issued],'not-in-catalog',settings)
    assert writes==[]


def test_building_cell_leaves_dropdown_in_control_and_context_keeps_selected_group():
    tree=ast.parse((ROOT/'lib/lowlife/opening_tasks_window.py').read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TaskWindow')
    methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('open_row','select_context_row')]
    class Row:
        def __init__(self,selected):self.IsSelected=selected;self.Item='clicked'
    row=Row(True)
    events=[]
    scope=dict(DataGridRow=Row,VisualTreeHelper=NS(GetParent=lambda n:None),
               ItemsControl=NS(ContainerFromElement=lambda grid,source:source))
    exec(compile(ast.Module(body=methods,type_ignores=[]),'table-actions','exec'),scope)
    window=NS(role='VIS',selected_rows=lambda:[dict(uid='box')],dispatch=events.append,
              tasks=NS(CurrentCell=NS(Column=NS(SortMemberPath='ObjectPart')),SelectedItem='existing group'))
    scope['open_row'](window,None,NS(OriginalSource=row))
    assert events==[]  # cell dropdown handles editing without another chooser
    window.tasks.CurrentCell.Column.SortMemberPath='Sizes'
    scope['open_row'](window,None,NS(OriginalSource=row))
    assert events[-1]=='focus'
    scope['select_context_row'](window,None,NS(OriginalSource=row))
    assert window.tasks.SelectedItem=='existing group'
    row.IsSelected=False
    scope['select_context_row'](window,None,NS(OriginalSource=row))
    assert window.tasks.SelectedItem=='clicked'
