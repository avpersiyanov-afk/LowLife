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


def publish_async(window,settings):
    # Capture all model data in the ExternalEvent, then release Revit for network IO.
    from lowlife import opening_tasks_storage as storage
    from System.Threading import Thread, ThreadStart
    from System import Action
    from pyrevit import forms
    doc=window.document
    project=settings['opening_project']
    model=storage.model_id(doc)
    connection=load_connection(project,window.role,model)
    data=snapshot(storage.registry(doc),project,window.role,model,unicode(doc.Title),window.rows)
    if window.role in ('KR','AR'):
        from lowlife import opening_tasks_revit as api
        for key,receipt in data['receipts'].items():
            opening=doc.GetElement(receipt['opening_uid']) if receipt.get('opening_uid') else None
            data['observations'][key]=dict(exists=opening is not None,
                matches=bool(opening is not None and api.opening_matches(opening,receipt)))
    payload=core.dumps(data)
    scope=dict(project=project,role=window.role,model=model)
    window.journal_busy=True
    window.exchange_hint.Text=tr(u'Публикация журнала… Можно продолжать работу в модели.',
                                 u'Publishing journal… You can continue working in the model.')
    def worker():
        message=None
        try:
            status=request(connection,'status',scope)
            result=request(connection,'publish',dict(scope,base_version=status['version'],payload=payload))
            message=tr(u'Журнал опубликован. Версия публикации: {}. Выдача заданий и решения в модели не изменены.',
                       u'Journal published. Publication version: {}. Model releases and decisions are unchanged.').format(result['version'])
        except Exception:
            # Never echo HTTP bodies/credentials. A retry uses the same content hash.
            message=tr(u'Не удалось подтвердить публикацию журнала. Проверьте сеть и подключение. Повторная публикация не создаёт дубликат неизменённого снимка. При откате модели обратитесь к администратору.',
                       u'Journal publication could not be confirmed. Check the network and connection. Republishing an unchanged snapshot does not create duplicates. Contact the administrator if the model was rolled back.')
        def done():
            window.journal_busy=False
            if not window.closed:
                window.exchange_hint.Text=message
                forms.alert(message)
        window.Dispatcher.BeginInvoke(Action(done))
    thread=Thread(ThreadStart(worker))
    thread.IsBackground=True
    thread.Start()


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
