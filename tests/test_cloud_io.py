# -*- coding: utf-8 -*-
import json
import ast
from pathlib import Path
import pytest
from lowlife import cloud_io


def test_existing_ascii_encoder_preserves_unicode_and_surrogate_pairs():
    value={'label':u'НЧ-1 😀','token':'secret'}
    encoded=cloud_io.dumps_ascii(value)
    assert encoded.isascii()
    assert json.loads(encoded)==value


def test_request_uses_explicit_connection_and_optional_error_translation(monkeypatch):
    transport=cloud_io.Transport()
    sent=[]
    def post(url,text,timeout,track):
        sent.append((url,json.loads(text),timeout,track))
        return '{"ok":true,"ms":12}'
    monkeypatch.setattr(transport,'_post',post)
    assert transport.call('status',{'project':'P'},url='endpoint',token='secret',track=False)['ok']
    assert sent[0]==('endpoint',{'project':'P','action':'status','token':'secret'},15000,False)
    assert transport.last_server_ms==[12.0]
    monkeypatch.setattr(transport,'_post',lambda *args:'{"ok":false,"error":"DENIED"}')
    with pytest.raises(cloud_io.ApiError,match='translated DENIED'):
        transport.call('status',url='endpoint',token='secret',error_transform=lambda v:'translated '+v)


def test_window_cancellation_isolated_from_other_tool_and_detached_requests(monkeypatch):
    notes=cloud_io.Transport()
    openings=cloud_io.Transport()
    monkeypatch.setattr(notes,'_post',lambda *args:'{"ok":true}')
    monkeypatch.setattr(openings,'_post',lambda *args:'{"ok":true}')
    notes.abort_requests()
    with pytest.raises(cloud_io.ApiError):
        notes.call('status',url='u',token='t',track=True)
    assert notes.call('status',url='u',token='t',track=False)['ok']
    assert openings.call('status',url='u',token='t',track=True)['ok']


def test_existing_retry_logic_is_reused(monkeypatch):
    transport=cloud_io.Transport()
    attempts=[]
    def post(*args):
        attempts.append(True)
        if len(attempts)==1:raise IOError('transient')
        return '{"ok":true}'
    monkeypatch.setattr(transport,'_post',post)
    monkeypatch.setattr(transport,'_is_transient',lambda *args:True)
    monkeypatch.setattr(cloud_io.time,'sleep',lambda seconds:None)
    assert transport.call('status',url='u',token='t',retries=1)['ok']
    assert len(attempts)==2


def test_opening_modules_do_not_import_notes():
    root=Path(__file__).parents[1]/'lib/lowlife'
    for path in list(root.glob('opening*.py'))+[root/'cloud_io.py',root/'background.py']:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            names=([node.module] if isinstance(node,ast.ImportFrom) else
                   [alias.name for alias in node.names] if isinstance(node,ast.Import) else [])
            assert all(not name or not name.startswith('pnotes') for name in names),path


def test_notes_adapter_keeps_its_own_config_and_error_formatter():
    import ast
    path=Path(__file__).parents[1]/'lib/pnotes/core.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='call')
    transport=cloud_io.Transport()
    transport._post=lambda *args:'{"ok":true}'
    ns=dict(TRANSPORT=transport,load_config=lambda:{'url':'notes-url','token':'notes-token'},
            server_error=lambda text:'translated '+text)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
    assert ns['call']('status')['ok']
    transport._post=lambda *args:'{"ok":false,"error":"NOTES"}'
    with pytest.raises(cloud_io.ApiError,match='translated NOTES'):
        ns['call']('status')


def test_shared_background_ignores_delivery_after_window_closes(monkeypatch):
    import sys
    from types import SimpleNamespace as NS
    from lowlife import background
    callbacks=[]
    class Event:
        def __iadd__(self,callback):
            self.callback=callback
            return self
    class Thread:
        def __init__(self,callback):self.callback=callback
        def Start(self):self.callback()
        def Join(self,timeout):pass
    monkeypatch.setitem(sys.modules,'System',NS(Action=lambda f:f))
    monkeypatch.setitem(sys.modules,'System.Threading',NS(Thread=Thread,ThreadStart=lambda f:f))
    transport=cloud_io.Transport()
    window=NS(Closed=Event(),Dispatcher=NS(BeginInvoke=callbacks.append))
    delivered=[]
    background.in_background(window,lambda:42,lambda value,error:delivered.append((value,error)),transport)
    assert delivered==[] and len(callbacks)==1
    background.stop_background(window,transport)
    callbacks[0]()
    assert delivered==[]


def test_shared_project_reader_keeps_custom_and_builtin_reference_support(monkeypatch):
    import sys
    from types import SimpleNamespace as NS
    path=Path(__file__).parents[1]/'lib/lowlife/params.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='read_project_parameter')
    monkeypatch.setitem(sys.modules,'Autodesk.Revit.DB',NS(BuiltInParameter=NS(PROJECT_NUMBER='number')))
    doc=NS(ProjectInformation=NS(get_Parameter=lambda bip:NS(value='BUILTIN'),
         LookupParameter=lambda name:NS(value=' CUSTOM ') if name=='Code' else None))
    ns=dict(param_to_text=lambda p:p.value if p else '')
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    assert ns['read_project_parameter'](doc,'Code')=='CUSTOM'
    assert ns['read_project_parameter'](doc,'Localized name [PROJECT_NUMBER]')=='BUILTIN'
    assert ns['read_project_parameter'](doc,'Missing')==''
