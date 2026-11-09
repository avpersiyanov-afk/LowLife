"""Guard native preparation against unrelated documents/commands and reentry."""
from types import SimpleNamespace as NS

from lowlife import link_datums_native_ui as native


def preparation(active='ID_BUTTON_SELECT', copy_visible=True):
    obj = native.MultipleSelection.__new__(native.MultipleSelection)
    doc = NS(IsValidObject=True)
    doc.Equals = lambda other: other is doc
    obj.doc = doc
    obj.uiapp = NS(ActiveUIDocument=NS(Document=doc),
                   MainWindowHandle=NS(ToInt64=lambda: 123))
    item = NS(Id=native.COPY_COMMAND if copy_visible else 'unrelated', IsEnabled=True)
    obj.ribbon = NS(ActiveTab=NS(Panels=[NS(Source=NS(Items=[item]))]))
    calls = []
    obj.commands = NS(getActiveCommandId=lambda: active, canExecute=lambda command: True,
                      invokeCommandHandler=lambda command: calls.append(command))
    obj.ticks = 0
    obj.invoked = False
    obj.busy = False
    obj.error = None
    obj.stop = lambda: calls.append('stop')
    return obj, calls


def test_waits_for_link_and_native_copy_ribbon():
    for active, visible in [('ID_COPY_WATCH_LINK', True), ('ID_BUTTON_SELECT', False)]:
        obj, calls = preparation(active, visible)
        obj.tick(None, None)
        assert calls == []


def test_invokes_copy_only_once_and_blocks_nested_dispatch():
    obj, calls = preparation()

    def invoke(command):
        calls.append(command)
        obj.tick(None, None)

    obj.commands.invokeCommandHandler = invoke
    obj.tick(None, None)
    obj.tick(None, None)
    assert calls == [native.COPY_COMMAND]


def test_stops_after_checkbox_confirmed(monkeypatch):
    obj, calls = preparation(native.COPY_COMMAND)
    results = iter([False, True])
    monkeypatch.setattr(native, 'enable_multiple', lambda hwnd: next(results))
    obj.tick(None, None)
    assert calls == []
    obj.tick(None, None)
    assert calls == ['stop']


def test_stops_when_document_changes_or_deadline_expires():
    for reason in ['document', 'deadline', 'closed']:
        obj, calls = preparation()
        if reason == 'document':
            obj.uiapp.ActiveUIDocument = None
        elif reason == 'closed':
            obj.doc.IsValidObject = False
        else:
            obj.ticks = 1199
        obj.tick(None, None)
        assert calls == ['stop']
        assert not obj.invoked


def test_unsupported_ui_stops_without_breaking_native_session():
    obj, calls = preparation()
    obj.ribbon = None
    obj.tick(None, None)
    assert calls == ['stop']
    assert obj.error
