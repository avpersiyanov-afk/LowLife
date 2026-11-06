# -*- coding: utf-8 -*-
"""Project part catalog cached from Google, with per-model local selection."""
try:
    unicode
except NameError:
    unicode = str

from lowlife import settings_core as sc
from lowlife import opening_tasks_core as core
from lowlife.i18n import tr


def store():
    return sc.JsonStore('LowLifeOpeningTasks_parts.json',share=False)


def valid_label(value):
    return isinstance(value,type(u'')) and (value in (u'НЧ',u'ПЧ') or
        any(value.startswith(prefix) and bool(value[len(prefix):].strip()) for prefix in (u'НЧ-',u'ПЧ-')))


def catalog(project):
    return store().read().get('catalogs',{}).get(project,[])


def selection(project,role,model):
    key=core.dumps([project,role,model])
    return store().read().get('selected',{}).get(key,'')


def select(project,role,model,value):
    data=store().read()
    data.setdefault('selected',{})[core.dumps([project,role,model])]=value
    store().write(data,notify=False)


def require_choice(project,value):
    if not value or value not in catalog(project):
        raise ValueError(tr(u'Выберите часть объекта из Google-справочника. Заполните лист «Части объектов» и обновите список.',
                            u'Select an object part from the Google catalog. Fill the Object parts sheet and refresh the list.'))
    return value


def fetch(window,settings):
    """Capture scope in API context, perform network IO without accessing the model."""
    from lowlife import opening_tasks_journal as journal
    from System.Threading import Thread, ThreadStart
    from System import Action
    project=settings['opening_project']
    scope=dict(project=project,role=window.role,model=window.model_uid)
    connection=journal.load_connection(project,window.role,window.model_uid)
    window.parts_loading=True
    def worker():
        values=None
        try:
            response=journal.request(connection,'catalog',scope)
            values=sorted(set(v for v in response['parts'] if valid_label(v)))
        except Exception:
            pass
        def done():
            window.parts_loading=False
            if values is not None:
                data=store().read()
                data.setdefault('catalogs',{})[project]=values
                store().write(data,notify=False)
            if not window.closed and window.project_code==project:
                window.load_parts()
        try:
            window.Dispatcher.BeginInvoke(Action(done))
        except Exception:
            pass
    thread=Thread(ThreadStart(worker))
    thread.IsBackground=True
    try:
        thread.Start()
    except Exception:
        window.parts_loading=False
        raise
