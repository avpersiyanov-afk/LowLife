# -*- coding: utf-8 -*-
"""Explicit Google journal publication. Secrets never enter model/settings exports."""
try:
    unicode
except NameError:
    unicode = str

import copy
import os
import re
from lowlife import opening_tasks_core as core
from lowlife.i18n import tr

ADMIN_LOGIN = 'persiyanov'
CONFIG_FILE = 'LowLifeOpeningJournal_connections.json'


def is_admin(login=None):
    return (login if login is not None else os.environ.get('USERNAME','')).lower() == ADMIN_LOGIN


def validate_url(url):
    if not re.match(r'^https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec$',url or ''):
        raise ValueError(tr(u'Нужен адрес Google Apps Script вида https://script.google.com/macros/s/…/exec',
                            u'Use a Google Apps Script URL: https://script.google.com/macros/s/…/exec'))
    return url


def scope_key(project, role, model):
    return core.dumps(dict(project=project,role=role,model=model))


def connection_store():
    from lowlife.settings_core import JsonStore
    return JsonStore(CONFIG_FILE,share=False)


def crypt(text, decrypt=False):
    import clr
    clr.AddReference('System.Security')
    from System.Security.Cryptography import ProtectedData, DataProtectionScope
    from System.Text import Encoding
    from System import Convert
    if decrypt:
        return unicode(Encoding.UTF8.GetString(ProtectedData.Unprotect(
            Convert.FromBase64String(text),None,DataProtectionScope.CurrentUser)))
    return unicode(Convert.ToBase64String(ProtectedData.Protect(
        Encoding.UTF8.GetBytes(text),None,DataProtectionScope.CurrentUser)))


def load_connection(project,role,model):
    value=connection_store().read().get(scope_key(project,role,model))
    if not value:
        raise ValueError(tr(u'Журнал не подключён для этой модели. Администратор persiyanov должен выдать подключение.',
                            u'Journal is not configured for this model. Ask administrator persiyanov for a connection.'))
    validate_url(value['url'])
    return dict(url=value['url'],token=crypt(value['token_dpapi'],True))


def save_connection(project,role,model,url,token,sheet_url=''):
    validate_url(url)
    if not token.strip():
        raise ValueError(tr(u'Введите токен подключения',u'Enter a connection token'))
    config=connection_store()
    data=config.read()
    data[scope_key(project,role,model)]=dict(url=url,token_dpapi=crypt(token.strip()),sheet_url=sheet_url)
    if not config.write(data):
        raise ValueError(tr(u'Подключение журнала не сохранено',u'Journal connection was not saved'))


def snapshot(registry,project,role,model,title,rows=None):
    """Full released records/history, scoped to one project and originating model."""
    if role not in ('VIS','KR','AR') or not project or not model:
        raise ValueError(tr(u'Не задан проект, модель или роль журнала',u'Journal project, model or role is missing'))
    value=dict(schema=1,project=project,role=role,model=model,model_title=title,
               tasks={},issues=[],receipts={},decisions=[],confirmations=[],working=[],observations={})
    if role=='VIS':
        value['tasks']={key:copy.deepcopy(r) for key,r in registry.get('tasks',{}).items()
                        if r['project']==project and r['source_model']==model}
        for issue in registry.get('issues',[]):
            tasks=[copy.deepcopy(r) for r in issue.get('tasks',[])
                   if r['project']==project and r['source_model']==model]
            if tasks:
                item=copy.deepcopy(issue)
                item['tasks']=tasks
                value['issues'].append(item)
        ids=set(value['tasks'])
        value['confirmations']=[copy.deepcopy(r) for r in registry.get('confirmations',[])
                                if r.get('task_id') in ids]
    else:
        def own(r):
            return r.get('project')==project and r.get('recipient','KR')==role
        value['receipts']={key:copy.deepcopy(r) for key,r in registry.get('receipts' if role=='KR' else 'ar_receipts',{}).items() if own(r)}
        value['decisions']=[copy.deepcopy(r) for r in registry.get('decisions' if role=='KR' else 'ar_decisions',[]) if own(r)]
    # UI diagnostics are observations, never formal releases or acceptance.
    for row in rows or []:
        if role=='VIS' and row.get('task_id') not in value['tasks']:
            continue
        value['working'].append({key:copy.deepcopy(row[key]) for key in (
            'key','number','task_id','status','result','recipient','discipline','level','kind',
            'revision','date','sizes','previous_sizes','displacement','comment','next_action','attention') if key in row})
    return value


def request(connection, action, payload):
    # Shared, proven .NET transport handles Google's redirect and Windows proxies.
    from pnotes.core import call
    return call(action,payload,url=connection['url'],token=connection['token'],
                timeout_ms=25000,retries=0,track=False)


def queue_store():
    from lowlife.settings_core import JsonStore
    return JsonStore('LowLifeOpeningJournal_pending.json',share=False)


def enqueue(items, data):
    """Keep every changed snapshot in order, without credentials."""
    payload=core.dumps(data)
    scope=dict(project=data['project'],role=data['role'],model=data['model'])
    if any(item['scope']==scope and item['payload']==payload for item in items):
        return list(items)
    return list(items)+[dict(id=core.guid(),scope=scope,payload=payload)]


def deliver(items, send):
    """A failed scope blocks its later revisions, but not other models."""
    sent,blocked=[],set()
    for item in items:
        key=scope_key(**item['scope'])
        if key in blocked:
            continue
        try:
            send(item)
            sent.append(item['id'])
        except Exception:
            blocked.add(key)
    return sent,blocked


def capture(window,settings):
    from lowlife import opening_tasks_storage as storage
    doc=window.document
    data=snapshot(storage.registry(doc),settings['opening_project'],window.role,
                  storage.model_id(doc),unicode(doc.Title),window.rows)
    if window.role in ('KR','AR'):
        from lowlife import opening_tasks_revit as api
        for key,receipt in data['receipts'].items():
            opening=doc.GetElement(receipt['opening_uid']) if receipt.get('opening_uid') else None
            data['observations'][key]=dict(exists=opening is not None,
                matches=bool(opening is not None and api.opening_matches(opening,receipt)))
    # The transaction is committed; saving/synchronizing the RVT remains explicit.
    return data


def auto_publish(window,settings):
    from pnotes.core import _QueueLock
    with _QueueLock('lowlife_opening_journal_queue'):
        store=queue_store()
        data=store.read()
        data['items']=enqueue(data.get('items',[]),capture(window,settings))
        if not store.write(data):
            raise ValueError(tr(u'Изменения в модели зафиксированы, но очередь журнала не сохранена. Обратитесь к администратору.',
                                u'Model changes were committed, but the journal queue was not saved. Contact the administrator.'))
    retry_pending(window)


def retry_pending(window):
    """Detached network operation; durable acknowledgements run on the UI thread."""
    from pnotes.core import _QueueLock
    from System import Action, AppDomain
    from System.Threading import Thread, ThreadStart
    domain=AppDomain.CurrentDomain
    flag='lowlife_opening_journal_sending'
    with _QueueLock('lowlife_opening_journal_queue'):
        items=queue_store().read().get('items',[])
        if not items or domain.GetData(flag):
            return
        domain.SetData(flag,True)
    window.exchange_hint.Text=tr(u'Изменения зафиксированы в Revit. Журнал отправляется автоматически; сохраните/синхронизируйте модель.',
                                 u'Changes committed in Revit. Sending journal automatically; save/synchronize the model.')
    def flush():
        def send(item):
            scope=item['scope']
            connection=load_connection(scope['project'],scope['role'],scope['model'])
            status=request(connection,'status',scope)
            request(connection,'publish',dict(scope,base_version=status['version'],payload=item['payload']))
        sent,blocked=deliver(items,send)
        def done():
            with _QueueLock('lowlife_opening_journal_queue'):
                store=queue_store()
                data=store.read()
                data['items']=[i for i in data.get('items',[]) if i['id'] not in set(sent)]
                saved=store.write(data)
                remaining=len(data['items']) if saved else len(store.read().get('items',[]))
            if not window.closed:
                window.exchange_hint.Text=(
                    tr(u'Журнал обновлён автоматически. Сохраните/синхронизируйте модель для обмена связями.',
                       u'Journal updated automatically. Save/synchronize the model for linked-model exchange.')
                    if not remaining and saved else
                    tr(u'Журнал ожидает отправки: {}. Проверьте подключение. Повтор — при «Обновить обмен», открытии окна или следующем изменении.',
                       u'Journal entries awaiting delivery: {}. Check the connection. Retry on Refresh exchange, window opening or next change.').format(remaining))
            if not blocked and saved and remaining:
                retry_pending(window)
        # Release the sender before the UI acknowledgement can resume queued work.
        with _QueueLock('lowlife_opening_journal_queue'):
            domain.SetData(flag,None)
        window.Dispatcher.BeginInvoke(Action(done))
    def safe_worker():
        try:
            flush()
        except Exception:
            with _QueueLock('lowlife_opening_journal_queue'):
                domain.SetData(flag,None)
    thread=Thread(ThreadStart(safe_worker))
    thread.IsBackground=True
    try:
        thread.Start()
    except Exception:
        with _QueueLock('lowlife_opening_journal_queue'):
            domain.SetData(flag,None)
        raise


def setup(doc,role,project):
    """Admin-only UI; normal users receive scoped credentials through provisioning."""
    if not is_admin():
        raise ValueError(tr(u'Настройка журнала доступна только persiyanov',u'Only persiyanov can configure the journal'))
    from pyrevit import forms
    from lowlife import opening_tasks_storage as storage
    model=storage.model_id(doc)
    class ConnectionWindow(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self,u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
              xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Width="720" Height="370"
              WindowStartupLocation="CenterScreen" ResizeMode="NoResize">
              <StackPanel Margin="20">
                <TextBox x:Name="info" TextWrapping="Wrap" IsReadOnly="True" BorderThickness="0" Margin="0,0,0,16"/>
                <TextBlock Text="Google Apps Script URL"/>
                <TextBox x:Name="url" Margin="0,6,0,12"/>
                <TextBlock Text="Token"/>
                <PasswordBox x:Name="token" Margin="0,6,0,18"/>
                <Button x:Name="save" Padding="12,7"/>
              </StackPanel></Window>''',literal_string=True)
            self.Title=tr(u'Подключение журнала — persiyanov',u'Journal connection — persiyanov')
            self.info.Text=tr(u'Проект: {} | Роль: {}\nID модели: {}\nСоздайте токен для этих значений в меню Google-таблицы LowLife.',
                              u'Project: {} | Role: {}\nModel ID: {}\nCreate a token for these values in the Google sheet LowLife menu.').format(project,role,model)
            self.save.Content=tr(u'Проверить и сохранить',u'Check and save')
            self.save.Click+=self.on_save
        def on_save(self,sender,event):
            try:
                url=validate_url(unicode(self.url.Text).strip())
                token=unicode(self.token.Password).strip()
                if not token:
                    raise ValueError(tr(u'Введите токен подключения',u'Enter a connection token'))
                result=request(dict(url=url,token=token),'status',dict(project=project,role=role,model=model))
                save_connection(project,role,model,url,token,result.get('sheet_url',''))
                self.token.Password=''
                self.Close()
            except Exception as ex:
                forms.alert(unicode(ex))
    ConnectionWindow().ShowDialog()


def open_sheet(doc,role,project):
    from lowlife import opening_tasks_storage as storage
    from pyrevit import script
    value=connection_store().read().get(scope_key(project,role,storage.model_id(doc)),{})
    url=value.get('sheet_url','')
    if not re.match(r'^https://docs\.google\.com/spreadsheets/d/[A-Za-z0-9_-]+(?:/edit)?$',url):
        raise ValueError(tr(u'Нет ссылки на журнал. Переустановите подключение таблицы.',u'Journal link is missing. Reinstall the sheet connection.'))
    script.open_url(url)
