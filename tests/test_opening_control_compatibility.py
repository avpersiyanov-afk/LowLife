"""Exercise the real adapter functions without loading Revit or WPF."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]


def load_function(file, name, ns):
    tree = ast.parse((ROOT / 'lib/lowlife' / file).read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    node.body = [n for n in node.body if not isinstance(n, ast.ImportFrom)]
    exec(compile(ast.Module(body=[node], type_ignores=[]), file, 'exec'), ns)
    return ns[name]


class Lists:
    def __class_getitem__(cls, _):
        return cls

    def __new__(cls, items=()):
        return list(items)


class Filter:
    def __init__(self):
        self.ids = []
        self.writes = 0
        self.Id = 99

    def SetElementIds(self, ids):
        self.ids = list(ids)
        self.writes += 1

    def GetElementIds(self):
        return self.ids


class Collector(list):
    def OfClass(self, _):
        return self

    def WhereElementIsNotElementType(self):
        return self


def box(eid, status, owner=True, project='P'):
    return NS(Id=eid, UniqueId=str(eid), Category=NS(Id=1), status=status,
              data=dict(owner_uid=str(eid) if owner else 'original', project=project),
              LookupParameter=lambda _: NS(AsString=lambda: status))


def test_nonfilterable_family_parameter_uses_selection_and_reuses_filter():
    instances = [box(1, 'Issued'), box(2, 'Draft')]
    saved = {}
    ns = dict(doc=None, use_parameters=False, root='P/1', prefix='Control', instances=instances,
              settings={'opening_status_param': 'Status'}, FilterElement=object,
              SelectionFilterElement=Filter, List=Lists, ElementId=int,
              _selection_filter=lambda *args: Filter(),
              safe_name=lambda s, _: s, api=NS(core=NS(guid=lambda: 'guid')),
              existing=lambda key, _: saved.get(key),
              remember=lambda key, f: saved.setdefault(key, f))
    pf = load_function('opening_tasks_views.py', 'pf', ns)
    f = pf('/color/1', 'Issued', 'Issued')
    assert f.ids == [1]
    assert pf('/color/1', 'Issued', 'Issued') is f
    assert pf('/hide/2', 'Others', 'Issued', True).ids == [2]
    # No rule factory is available: any attempted parameter-rule creation fails.


def test_filterable_parameter_path_uses_parameter_rules():
    calls = []
    class ParamFilter:
        @staticmethod
        def Create(doc, name, categories, rules):
            calls.append((categories, rules))
            return NS()
    ns = dict(use_parameters=True, root='P/1', prefix='Control',
              doc=None, categories=[1], ids={'opening_json_param': 5, 'opening_status_param': 6},
              existing=lambda *args: None, remember=lambda key, f: f,
              FilterElement=object, SelectionFilterElement=Filter, List=Lists, ElementFilter=object,
              ParameterFilterElement=ParamFilter,
              ParameterFilterRuleFactory=NS(CreateContainsRule=lambda *a: ('contains', a),
                  CreateEqualsRule=lambda *a: ('equals', a)),
              ElementParameterFilter=lambda *a: a, LogicalAndFilter=lambda a: a,
              safe_name=lambda s, _: s, api=NS(core=NS(guid=lambda: 'guid')))
    pf = load_function('opening_tasks_views.py', 'pf', ns)
    pf('/color/1', 'Issued', 'Issued')
    assert calls == [([1], [(('contains', (5, 'task_id')),),
                            (('equals', (6, 'Issued')), False)])]


def test_fallback_membership_refreshes_after_status_change_and_deletion():
    issued, hidden, other_project = Filter(), Filter(), Filter()
    issued.ids = [10]  # stale deleted element
    hidden.ids = [20]
    objects = {'i': issued, 'h': hidden, 'o': other_project}
    elements = [box(1, 'Issued'), box(2, 'Draft'), box(3, 'Issued', owner=False),
                box(4, 'Issued', project='Q')]
    registry = {'control_views': {'P/1/color/1': 'i', 'P/1/hide/2': 'h', 'Q/1/color/1': 'o'}}
    doc = NS(GetElement=objects.get)
    ns = dict(SelectionFilterElement=Filter, FamilyInstance=object,
              FilteredElementCollector=lambda _: Collector(elements),
              List=Lists, ElementId=int, STATUSES=[('Draft', None), ('Issued', None)],
              api=NS(metadata=lambda el: el.data, boxes=NS(_id_int=int)))
    sync = load_function('opening_tasks_views.py', 'sync_selection_filters', ns)
    sync(doc, {'opening_project': 'P', 'opening_status_param': 'Status'}, registry)
    assert issued.ids == [1]
    assert hidden.ids == [2]
    assert other_project.writes == 0
    sync(doc, {'opening_project': 'P', 'opening_status_param': 'Status'}, registry)
    assert issued.writes == 1  # unchanged membership is not rewritten
    elements[:] = [box(2, 'Issued')]
    sync(doc, {'opening_project': 'P', 'opening_status_param': 'Status'}, registry)
    assert issued.ids == [2]
    assert hidden.ids == []


def test_preview_unhides_through_existing_element_api_helper():
    class IdList(list):
        @property
        def Count(self):
            return len(self)
        def Add(self, v):
            self.append(v)
    class Generic:
        def __class_getitem__(cls, _):
            return IdList
    elements = [NS(Id=i, IsHidden=lambda view, h=h: h) for i, h in [(1, True), (2, False)]]
    shown = []
    view = NS(UnhideElements=lambda ids: shown.extend(ids))
    unhide = load_function('loi_check.py', '_unhide_all', dict(
        List=Generic, ElementId=int, FilteredElementCollector=lambda _: Collector(elements)))
    unhide(None, view)
    assert shown == [1]
    tree = ast.parse((ROOT / 'lib/lowlife/opening_tasks_focus.py').read_text())
    assert not any(isinstance(n, ast.Attribute) and n.attr == 'GetHiddenElementIds' for n in ast.walk(tree))
    for name in ('focus', 'structures_view'):
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_unhide_all'
                   for n in ast.walk(fn))


def test_unschedulable_family_parameters_do_not_discard_created_views():
    tree = ast.parse((ROOT / 'lib/lowlife/opening_tasks_views.py').read_text())
    build = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build')
    loop = next(n for n in build.body if isinstance(n, ast.For) and isinstance(n.target, ast.Tuple))
    start = next(i for i, n in enumerate(loop.body) if isinstance(n, ast.Assign)
                 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'schedule_tx')
    block = loop.body[start:]
    events, messages = [], []
    class Tx:
        def __init__(self, doc):
            pass
        def Start(self):
            events.append('start')
        def Commit(self):
            events.append('commit')
        def RollBack(self):
            events.append('rollback')
        def Dispose(self):
            events.append('dispose')
    schedule = NS(UniqueId='new', Definition=NS(GetSchedulableFields=lambda: [], GetFieldOrder=lambda: []))
    output, managed = ['existing 3D', 'existing plan'], {}
    def remember(key, value):
        managed[key] = value.UniqueId
        return value
    scope = dict(SubTransaction=Tx, doc=None, managed=managed, root='P/1',
                 existing=lambda *args: None, remember=remember,
                 ViewSchedule=NS(CreateSchedule=lambda *args: schedule), category=1,
                 unique_name=lambda doc, name: name, prefix='Control',
                 KEYS=['opening_json_param'], ids={'opening_json_param': 5},
                 settings={'opening_json_param': 'JSON'}, output=output,
                 instances=[NS(Category=NS(Name='Boxes'))],
                 forms=NS(alert=messages.append), tr=lambda ru, en=None: en or ru)
    exec(compile(ast.Module(body=block, type_ignores=[]), 'schedule', 'exec'), scope)
    assert events == ['start', 'rollback', 'dispose']
    assert output == ['existing 3D', 'existing plan']
    assert managed == {}  # no UID of the rolled-back schedule remains
    assert len(messages) == 1 and 'JSON' in messages[0]


def test_focus_never_hides_itself_or_other_views_even_if_api_says_hideable():
    tree = ast.parse((ROOT / 'lib/lowlife/opening_tasks_focus.py').read_text())
    focus = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'focus')
    start = next(i for i, n in enumerate(focus.body) if isinstance(n, ast.Assign)
                 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'keep')
    end = next(i for i, n in enumerate(focus.body[start:], start) if isinstance(n, ast.If)
               and isinstance(n.test, ast.Name) and n.test.id == 'others')
    class PreviewView:
        def __init__(self, eid):
            self.Id = eid
            self.Category = object()
        def CanBeHidden(self, view):
            return True  # Revit's per-element check does not exclude the view.
        def HideElements(self, ids):
            assert self.Id not in ids
            self.hidden = list(ids)
    view = PreviewView(1)
    other_view = PreviewView(2)
    elements = [view, other_view]
    for eid in (3, 4, 5, 6):
        elements.append(NS(Id=eid, Category=object(), CanBeHidden=lambda v: True))
    scope = dict(view=view, inst=elements[2], source=elements[3], link=elements[4],
                 doc=None, View=PreviewView, _unhide_all=lambda *a: None,
                 List=Lists, ElementId=int,
                 FilteredElementCollector=lambda doc: Collector(elements))
    exec(compile(ast.Module(body=focus.body[start:end+1], type_ignores=[]), 'focus', 'exec'), scope)
    assert view.hidden == [6]


def test_control_visibility_isolates_boxes_and_preserves_structures_only_on_plans():
    class V:
        Id = 100
        UniqueId = 'control'
        Category = NS(Id=1)
        def CanBeHidden(self, view):
            raise AssertionError('must never inspect a view for hiding')
    elements = [NS(Id=eid, Category=NS(Id=cat), CanBeHidden=lambda v: True)
                for eid, cat in [(1, 1), (2, 1), (3, 2), (4, 3), (5, 4)]]
    hidden, categories = [], []
    view = V()
    scope = dict(ElementId=NS(InvalidElementId=-1), View=V,
                 BuiltInCategory=NS(OST_RvtLinks=4),
                 boxes=NS(_id_int=int), structural_categories=lambda: {2},
                 _keep_with_nested=lambda doc, ids: ids,
                 _hide_other_categories=lambda doc, v, ids, **kw: categories.append(ids),
                 _hide_by_filter=lambda doc, v, ids, name: hidden.append(ids),
                 FilteredElementCollector=lambda doc: Collector(elements+[view]))
    configure = load_function('opening_tasks_visibility.py', 'configure', scope)
    configure(None, view, [elements[0]])
    assert categories[-1] == {1}
    assert hidden[-1] == [2]  # unrelated family in the box category
    configure(None, view, [elements[0]], structures=True)
    assert categories[-1] == {1, 2, 4}  # boxes, structures, links; no MEP category
    assert hidden[-1] == [2]
    assert view.ViewTemplateId == -1


def test_schedule_filters_by_plain_status_instead_of_multiline_json():
    tree = ast.parse((ROOT / 'lib/lowlife/opening_tasks_views.py').read_text())
    build = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build')
    assignment = next(n for n in ast.walk(build) if isinstance(n, ast.Assign)
                      and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'status_field')
    check = next(n for n in ast.walk(build) if isinstance(n, ast.If)
                 and isinstance(n.test, ast.UnaryOp) and isinstance(n.test.operand, ast.Call)
                 and isinstance(n.test.operand.func, ast.Attribute)
                 and n.test.operand.func.attr == 'CanFilterByValue')
    add = next(n for n in ast.walk(build) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
               and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'AddFilter')
    calls = []
    scope = dict(fields={1: NS(FieldId='json'), 2: NS(FieldId='status')},
                 ids={'opening_json_param': 1, 'opening_status_param': 2},
                 definition=NS(CanFilterByValue=lambda fid: fid == 'status', AddFilter=calls.append),
                 ScheduleFilter=lambda *args: args, ScheduleFilterType=NS(NotEqual='not_equal'))
    exec(compile(ast.Module(body=[assignment, check, add], type_ignores=[]), 'filter', 'exec'), scope)
    assert calls == [('status', 'not_equal', '')]
