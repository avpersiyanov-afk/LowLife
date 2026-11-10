"""Actual register builder with a small native schedule adapter."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
ROOT=Path(__file__).parents[1]


class Definition:
    def __init__(self,category):
        self.CategoryId=category;self.fields=[];self.filters=[];self.sort=[]
    def GetFilterCount(self):return len(self.filters)
    def RemoveFilter(self,i):self.filters.pop(i)
    def GetSortGroupFieldCount(self):return len(self.sort)
    def RemoveSortGroupField(self,i):self.sort.pop(i)
    def ClearFields(self):self.fields=[]
    def AddField(self,sf):
        f=NS(FieldId=len(self.fields),source=sf)
        self.fields.append(f);return f
    def CanFilterByValue(self,field):return True
    def AddFilter(self,f):self.filters.append(f)
    def AddSortGroupField(self,f):self.sort.append(f)


class Schedule:
    def __init__(self,cat):
        self.UniqueId='schedule';self.Name='old';self.Definition=Definition(cat)


def run_builder(categories=(1,1),legacy=False,missing=False):
    schedules=[];objects={};registry={'control_views':{},'tasks':{}}
    if legacy:
        old=Schedule(categories[0]);objects['old']=old
        registry['control_views']['P/1/schedule']='old'
    class Native(Schedule):
        @staticmethod
        def CreateSchedule(doc,cat):
            item=Native(cat);schedules.append(item);objects[item.UniqueId]=item;return item
    if legacy:
        objects['old'].__class__=Native
    settings={'opening_project':'P','box_width_param':'w','box_depth_param':'d','box_height_param':'h','opening_status_param':'status'}
    elements=[]
    for i,cat in enumerate(categories):
        params={key:NS(Id=key,AsString=lambda:'Draft') for key in ('w','d','h','status')}
        elements.append(NS(Category=NS(Id=cat),LookupParameter=params.get,Symbol=NS(LookupParameter=lambda key:None)))
    by_id={key:key for key in ('w','d','h','status') if not (missing and key=='h')}
    node=next(n for n in ast.parse((ROOT/'lib/lowlife/opening_tasks_schedule.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='build')
    node.body=[n for n in node.body if not isinstance(n,ast.ImportFrom)]
    scope=dict(ElementId=NS(InvalidElementId=-1),ViewSchedule=Native,
               api=NS(boxes=NS(_id_int=int)),unique_name=lambda doc,name:name,
               _schedulable_index=lambda doc,definition:(by_id,{}), _LEVEL_BIPS=('FAMILY_LEVEL_PARAM',),
               _first_by_bips=lambda by_id,bips:bips[0],
               _add_field=lambda definition,sf,heading:definition.AddField(sf),
               ScheduleFieldType=NS(Count='count'),ScheduleFilter=lambda *a:a,
               ScheduleFilterType=NS(NotEqual='not_equal'),ScheduleSortGroupField=lambda *a:a,
               ScheduleSortOrder=NS(Ascending='asc'),tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'register','exec'),scope)
    doc=NS(GetElement=objects.get)
    return scope['build'],doc,settings,elements,registry,schedules


@pytest.mark.parametrize('categories,expected', [((1,1),1),((1,2),-1)])
def test_one_register_all_boxes_separate_rows_without_json(categories,expected):
    build,doc,settings,elements,registry,created=run_builder(categories)
    view=build(doc,settings,elements,registry)
    assert len(created)==1 and view.Definition.CategoryId==expected
    assert view.Definition.IsItemized is True and view.Definition.ShowGrandTotalCount is True
    assert [f.source for f in view.Definition.fields]==[
        'ELEM_FAMILY_AND_TYPE_PARAM','ALL_MODEL_MARK','FAMILY_LEVEL_PARAM','w','d','h','status','count']
    assert view.Definition.filters==[(6,'not_equal','')]
    assert len(view.Definition.sort)==3
    assert registry['control_views']['P/register']==view.UniqueId
    # Repeat creation reuses the register and replaces fields instead of duplicating them.
    again=build(doc,settings,elements,registry)
    assert again is view and len(created)==1 and len(view.Definition.fields)==8


def test_legacy_single_category_register_is_reused_in_place():
    build,doc,settings,elements,registry,created=run_builder(legacy=True)
    old=doc.GetElement('old')
    assert build(doc,settings,elements,registry) is old
    assert not created and registry['control_views']['P/register']==old.UniqueId


def test_missing_dimension_is_explicit_not_silently_omitted():
    build,doc,settings,elements,registry,created=run_builder(missing=True)
    with pytest.raises(ValueError,match='h'):
        build(doc,settings,elements,registry)
    assert 'P/register' not in registry['control_views']
