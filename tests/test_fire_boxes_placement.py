"""Native drawing lifecycle and isolation; Revit geometry is verified in Revit."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)
        return self


def adapter():
    source = Path(__file__).parents[1] / 'lib/lowlife/fire_boxes_placement.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))]
    registered, env, alerts, applied = set(), {}, [], []
    table = NS(active=1)
    table.GetActiveWorksetId = lambda: table.active
    table.SetActiveWorksetId = lambda value: setattr(table, 'active', value)
    elements = {'type': NS(Id=10), 'system': NS(Id=20)}
    doc = NS(IsWorkshared=True, IsValidObject=True, IsModifiable=False,
             ActiveView=NS(GenLevel=object()), GetElement=elements.get,
             GetWorksetTable=lambda: table)
    doc.Equals = lambda other: other is doc
    binding = NS(BeforeExecuted=Event())
    uiapp = NS(ActiveAddInId=1, Idling=Event(), Application=NS(DocumentClosing=Event()),
               CreateAddInCommandBinding=lambda command: binding, RemoveAddInCommandBinding=lambda command: None)
    requests = []
    uiapp.PostCommand = requests.append
    uiapp.CanPostCommand = lambda command: True
    uidoc = NS(Application=uiapp)
    registry = NS(RegisterUpdater=lambda updater, doc, optional: registered.add(updater.GetUpdaterId()),
                  AddTrigger=lambda *args: None,
                  IsUpdaterRegistered=lambda identifier, doc: identifier in registered,
                  UnregisterUpdater=lambda identifier, doc: registered.remove(identifier))
    db = NS(IUpdater=object, UpdaterId=lambda *args: 42, UpdaterRegistry=registry,
            BuiltInCategory=int, ElementMulticategoryFilter=lambda cats: cats,
            Element=NS(GetChangeTypeElementAddition=lambda: 'addition'))
    class GenericList:
        def __class_getitem__(cls, key):
            return list
    fb = NS(resolve_workset=lambda doc, name: 2, CURVE_CATS=(1,), FITTING_CATS=(2,),
            in_categories=lambda el, cats: el is not None and el.category in cats,
            connected_curves=lambda el: el.connections, is_duct_type=lambda el: True)
    scope = dict(DB=db, UI=NS(RevitCommandId=NS(LookupPostableCommandId=lambda cmd: cmd),
                             PostableCommand=NS(CreateSimilar='similar')),
                 List=GenericList, UPDATER_GUID='guid', SESSION_KEY='session', copy=copy,
                 fb=fb, core=NS(mounting_section=lambda settings: dict(width=500, height=400)),
                 script=NS(get_envvar=env.get, set_envvar=lambda key, value: env.update({key: value})),
                 forms=NS(alert=alerts.append), tr=lambda ru, en: en, unicode=str)
    exec(compile(tree, str(source), 'exec'), scope)
    scope['PlacementSession'].prepare = lambda session: None
    settings = dict(box_type_uid='type', system_type_uid='system', elevation_mm=3000)
    return NS(scope=scope, doc=doc, uiapp=uiapp, uidoc=uidoc, settings=settings,
              registered=registered, env=env, alerts=alerts, table=table, elements=elements,
              requests=requests, applied=applied)


def test_native_request_keeps_session_until_idle_then_restores_workset():
    a = adapter()
    session = a.scope['start'](a.doc, a.uidoc, a.settings)
    assert a.requests == ['similar']
    assert session.active and a.registered and a.table.active == 2
    assert a.env['session'] is session
    a.settings['elevation_mm'] = 999
    assert session.settings['elevation_mm'] == 3000
    a.doc.IsModifiable = True
    session.on_idle(None, None)
    assert session.active
    a.doc.IsModifiable = False
    session.on_idle(None, None)  # Queued command has not started yet.
    assert session.active
    session.on_begin(None, None)
    session.on_idle(None, NS(SetRaiseWithoutDelay=lambda: None))
    session.on_idle(None, None)
    assert not session.active and not a.registered and a.table.active == 1
    assert not a.uiapp.Idling.handlers and not a.uiapp.Application.DocumentClosing.handlers
    assert a.env['session'] is None
    session.stop()  # Cleanup is idempotent.


def test_workset_selected_by_user_is_preserved():
    a = adapter()
    session = a.scope['start'](a.doc, a.uidoc, a.settings)
    a.table.active = 3
    session.stop()
    assert a.table.active == 3


def test_failed_request_cleans_up_registration_and_events():
    a = adapter()
    def fail(element_type):
        raise RuntimeError('request rejected')
    a.uiapp.PostCommand = fail
    with pytest.raises(RuntimeError, match='request rejected'):
        a.scope['start'](a.doc, a.uidoc, a.settings)
    assert not a.registered and a.table.active == 1
    assert not a.uiapp.Idling.handlers and not a.uiapp.Application.DocumentClosing.handlers
    assert a.env['session'] is None


def test_only_new_matching_curves_and_their_fittings_are_processed():
    a = adapter()
    session = a.scope['start'](a.doc, a.uidoc, a.settings)
    def curve(uid, type_id=10):
        return NS(UniqueId=uid, category=1, GetTypeId=lambda: type_id)
    own, other, existing = curve('own'), curve('other', 11), curve('existing')
    fitting = NS(UniqueId='fitting', category=2, connections={1: own})
    foreign = NS(UniqueId='foreign', category=2, connections={1: existing})
    a.elements.update(own=own, other=other, fitting=fitting, foreign=foreign)
    session.apply = a.applied.append
    session.process(['fitting', 'other', 'missing', 'foreign', 'own'])
    assert a.applied == [own, fitting]
    assert session.created == {'own', 'fitting'}
    # A later fitting can connect to an earlier session segment.
    session.process(['fitting'])
    assert a.applied[-1] is fitting


def test_errors_are_reported_after_exit_only_for_surviving_elements():
    a = adapter()
    session = a.scope['start'](a.doc, a.uidoc, a.settings)
    element = NS(UniqueId='own', category=1, GetTypeId=lambda: 10)
    a.elements['own'] = element
    def fail(el):
        raise ValueError('parameter unavailable')
    session.apply = fail
    session.process(['own'])
    session.errors['deleted'] = 'already undone'
    assert not a.alerts
    session.on_begin(None, None)
    session.starting_idle = False
    session.on_idle(None, None)
    assert len(a.alerts) == 1
    assert 'parameter unavailable' in a.alerts[0] and 'already undone' not in a.alerts[0]


def test_preflight_rejects_missing_type_or_system_and_non_plan():
    for missing in ('type', 'system', 'level'):
        a = adapter()
        if missing == 'level':
            a.doc.ActiveView.GenLevel = None
        else:
            del a.elements[missing]
        with pytest.raises(ValueError):
            a.scope['start'](a.doc, a.uidoc, a.settings)
        assert not a.requests and not a.registered


def test_unavailable_native_command_does_not_leave_handlers():
    a = adapter()
    a.uiapp.CanPostCommand = lambda command: False
    with pytest.raises(ValueError, match='cannot start drawing'):
        a.scope['start'](a.doc, a.uidoc, a.settings)
    assert not a.requests and not a.registered and not a.uiapp.Idling.handlers


def test_seed_is_removed_inside_first_native_transaction():
    a = adapter()
    session = a.scope['start'](a.doc, a.uidoc, a.settings)
    a.elements['seed'] = NS(Id=55)
    session.seed_uid = 'seed'
    deleted = []
    a.doc.Delete = deleted.append
    a.doc.IsModifiable = True
    session.remove_seed()
    assert deleted == [55] and session.seed_uid is None


def test_new_curve_receives_section_elevation_system_and_metadata():
    a = adapter()
    session = a.scope['start'](a.doc, a.uidoc, a.settings)
    writes = []
    db, fb = a.scope['DB'], a.scope['fb']
    db.BuiltInParameter = NS(RBS_DUCT_SYSTEM_TYPE_PARAM='system', RBS_OFFSET_PARAM='offset')
    parameters = {'system': NS(AsElementId=lambda: 99),
                  'offset': NS(IsReadOnly=False, AsDouble=lambda: 0,
                               Set=lambda value: writes.append(('offset', value)) or True)}
    fb.size = lambda el, w, h: writes.append(('size', w, h))
    fb.assign_workset = lambda el, ws: writes.append(('workset', ws))
    fb.note = lambda el, settings: writes.append(('note', settings))
    fb.write_data = lambda el, data: writes.append(('data', data))
    element = NS(category=1, get_Parameter=parameters.get,
                 SetSystemType=lambda identifier: writes.append(('system', identifier)))
    session.apply(element)
    assert writes[:4] == [('size', 500, 400), ('system', 20), ('offset', 3000/304.8), ('workset', 2)]
    assert writes[-1][1] == dict(version=1, settings=session.settings)
