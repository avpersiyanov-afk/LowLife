"""Count model reads while preserving displayed geometry/status semantics."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import opening_tasks_core as core
from lowlife import opening_tasks_browser as browser


@pytest.mark.parametrize('preloaded',[False,True])
@pytest.mark.parametrize('status',['issued','withdrawn'])
def test_row_reads_metadata_and_geometry_only_once(preloaded,status):
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_window.py'
    tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TaskWindow')
    fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='row')
    calls=[]
    geometry=dict(kind='wall',center_mm=[0,0,1000],size_mm=[400,200,300],
                  x_dir=[1,0,0],host_uid='wall',host_model='KR')
    data=dict(host_link_uid='link',host_uid='wall',size_params=['w','d','h'],
              kind='wall',level={'name':'AR ground'})
    current=dict(geometry,center_mm=[10,0,1000])
    record=dict(task_id='task',source_model='VIS',status=status,geometry=geometry,
                level=data['level'],revision=2,issued_at='now',discipline='VK')
    inst=object()
    linked=NS(GetElement=lambda uid:NS(LevelId='level') if uid=='wall' else NS(Name='AR ground'))
    link=NS(GetLinkDocument=lambda:linked)
    doc=NS(Title='VIS',GetElement=lambda uid:{'box':inst,'link':link}[uid])
    def metadata(el):calls.append('metadata');return data
    def host_geometry(*args):calls.append('geometry');return current
    def forbidden(*args):raise AssertionError('Redundant dimension read')
    api=NS(metadata=metadata,host_geometry=host_geometry,core=core,read_size=forbidden)
    ns=dict(api=api,browser=browser,tr=lambda ru,en=None:ru,unicode=str)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    window=NS(document=doc,role='VIS',sizes=lambda values:' / '.join(str(v) for v in values))
    kw=dict(inst=inst,data=data) if preloaded else {}
    row=ns['row'](window,'task','box',record,{},**kw)
    assert calls.count('metadata')==(0 if preloaded else 1)
    assert calls.count('geometry')==1
    assert row['displacement']=='+10.0 / +0.0 / +0.0'
    assert row['sizes']=='400 / 200 / 300'
    assert row['status']==('Изменено после выдачи' if status=='issued' else 'Отозвано')


def test_feedback_skips_unrelated_links_and_reads_repeated_model_once():
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_revit.py'
    tree=ast.parse(path.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='recipient_feedback')
    reads=[]
    target=NS(model='KR');unrelated=NS(model='OTHER')
    links=[NS(GetLinkDocument=lambda:target),NS(GetLinkDocument=lambda:unrelated),NS(GetLinkDocument=lambda:target)]
    task=dict(project='P',geometry={'host_model':'KR'},status='issued',source_model='VIS',task_id='1',revision=1)
    local={'tasks':{'1':task}}
    def registry(doc):
        reads.append(doc.model)
        return {'receipts':{}}
    ns=dict(store=NS(model_id=lambda doc:doc.model,registry=registry),core=core,
            FilteredElementCollector=lambda doc:NS(OfClass=lambda cls:links),RevitLinkInstance=object,
            unicode=str,tr=lambda ru,en=None:ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    result=ns['recipient_feedback'](NS(model='VIS'),'P',registry=local)
    assert reads==['KR']
    assert result['VIS/1']['attention']


def test_receiver_action_does_not_rebuild_incoming_list_for_preselected_rows():
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_ui.py'
    tree=ast.parse(path.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='kr')
    def forbidden(*args):raise AssertionError('Redundant model enumeration')
    prompts=[]
    ns=dict(revit=NS(doc=object()),script=NS(get_output=lambda:object()),
            store=NS(registry=forbidden),api=NS(incoming=forbidden),FilteredElementCollector=forbidden,
            forms=NS(alert=lambda text,**kw:prompts.append(text) or False),tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    ns['kr']({'opening_recipient':'KR'},'accept',[{'task_id':'checked-in-handler'}])
    assert len(prompts)==1
