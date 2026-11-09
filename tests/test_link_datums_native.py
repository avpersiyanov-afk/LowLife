"""Revit session sequencing: keep one subscription across asynchronous views."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from lowlife import link_datums_views


@pytest.fixture
def session_api(monkeypatch):
    import lowlife
    monkeypatch.setitem(sys.modules, 'Autodesk', NS())
    monkeypatch.setitem(sys.modules, 'Autodesk.Revit', NS(DB=NS(), UI=NS()))
    monkeypatch.setitem(sys.modules, 'pyrevit', NS(script=NS(), forms=NS(alert=lambda *a: None)))
    monkeypatch.setattr(lowlife, 'link_datums', NS(), raising=False)
    path = Path(__file__).parents[1] / 'lib/lowlife/link_datums_native.py'
    spec = importlib.util.spec_from_file_location('_test_native_session', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    link = NS(GetLinkDocument=lambda: object())
    doc = NS(IsValidObject=True, IsModifiable=False, GetElement=lambda i: link)
    doc.Equals = lambda other: other is doc
    current = NS(Id=1, IsValidObject=True)
    target = NS(Id=2, IsValidObject=True)
    uidoc = NS(Document=doc, ActiveView=current,
               RequestViewChange=lambda view: calls.append(('request', view.Id)))
    obj = module.NativeSession.__new__(module.NativeSession)
    obj.uiapp = NS(ActiveUIDocument=uidoc, PostCommand=lambda c: calls.append(('post', c)))
    obj.doc = doc
    obj.link_id = 10
    obj.choices = ['levels']
    obj.pending = [(target, ['grids'])]
    obj.waiting_view = None
    obj.view_waits = 0
    obj.multiple = NS(stop=lambda: calls.append('timer-stop'))
    obj.started = True
    obj.settling = False
    obj.command = 'copy-monitor'
    obj.original_ids = set()
    obj.tolerance = 1
    obj.report = lambda *a: calls.append('report')
    obj.stop = lambda: calls.append('stop')
    monkeypatch.setattr(module.link_datums_copy, 'configure_copies', lambda *a: ([9], []))
    monkeypatch.setattr(link_datums_views, 'activate', lambda *a: calls.append('activate'))
    return obj, calls, module, target


def test_keeps_same_session_and_waits_for_requested_view(session_api):
    obj, calls, module, target = session_api
    obj.idle(None, None)
    assert calls == ['report', 'timer-stop', ('request', 2)]
    assert obj.choices == ['grids']
    assert not obj.started
    obj.idle(None, None)
    assert not any(isinstance(c, tuple) and c[0] == 'post' for c in calls)
    obj.uiapp.ActiveUIDocument.ActiveView = target
    obj.idle(None, None)
    assert calls[-2:] == ['activate', ('post', 'copy-monitor')]
    assert obj.waiting_view is None


def test_cancel_does_not_start_next_group(session_api, monkeypatch):
    obj, calls, module, target = session_api
    monkeypatch.setattr(module.link_datums_copy, 'configure_copies', lambda *a: ([], []))
    obj.idle(None, None)
    assert calls == ['report', 'stop']


def test_document_switch_stops_without_model_changes(session_api):
    obj, calls, module, target = session_api
    obj.uiapp.ActiveUIDocument = None
    obj.idle(None, None)
    assert calls == ['stop']


def test_deleted_pending_view_stops_before_posting(session_api):
    obj, calls, module, target = session_api
    obj.waiting_view = target
    target.IsValidObject = False
    obj.idle(None, None)
    assert calls == ['stop']
