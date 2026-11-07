"""Connection validation stays off the UI thread and uses the existing worker."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace as NS


def test_connection_is_saved_only_after_background_validation(monkeypatch):
    import lowlife
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_journal.py'
    tree=ast.parse(path.read_text())
    setup=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='setup')
    cls=next(n for n in setup.body if isinstance(n,ast.ClassDef) and n.name=='ConnectionWindow')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='on_save')
    callbacks=[];sent=[];saved=[];alerts=[]
    monkeypatch.setitem(sys.modules,'pnotes.ui',NS(in_background=lambda w,work,done:callbacks.append((work,done))))
    def request(connection,action,scope,track=False):
        sent.append((scope,track))
        return {'sheet_url':'sheet'}
    ns=dict(unicode=str,validate_url=lambda url:url,project='P',role='KR',model='model',
            request=request,save_connection=lambda *args,**kw:saved.append((args,kw)),
            forms=NS(alert=alerts.append),tr=lambda ru,en=None:ru)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),ns)
    closed=[]
    window=NS(url=NS(Text='url',IsEnabled=True),token=NS(Password='secret',IsEnabled=True),
              save=NS(IsEnabled=True),Close=lambda:closed.append(True))
    ns['on_save'](window,None,None)
    assert not window.save.IsEnabled and not sent and not saved
    work,done=callbacks.pop()
    done(work(),None)
    assert sent==[({'project':'P','role':'KR','model':'model'},True)]
    assert saved==[(('P','KR','model','url','secret','sheet'),{'shared':False,'all_projects':False})]
    assert closed==[True] and window.token.Password=='' and not alerts
    window.token.Password='new'
    ns['on_save'](window,None,None)
    work,done=callbacks.pop()
    done(None,'offline')
    assert window.save.IsEnabled and alerts==['offline'] and len(saved)==1
