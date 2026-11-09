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
from lowlife.opening_tasks_manifest import canonical_discipline, INSTALL_DISCIPLINES
from lowlife.cloud_io import Transport, AppDomainLock as QueueLock

TRANSPORT=Transport()

CONFIG_FILE = 'LowLifeOpeningJournal_connections.json'


def validate_url(url):
    if not re.match(r'^https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec$',url or ''):
        raise ValueError(tr(u'Нужен адрес Google Apps Script вида https://script.google.com/macros/s/…/exec',
                            u'Use a Google Apps Script URL: https://script.google.com/macros/s/…/exec'))
    return url


def scope_key(project, role, model):
    return core.dumps(dict(project=project,role=role,model=model))



def connection_value(project,role,model):
    data=connection_store().read()
    # A new shared connection replaces per-model setup, while old files still work.
    return (data.get(scope_key('*',role,'*')) or
            data.get(scope_key(project,role,'*')) or data.get(scope_key(project,role,model)))


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
    value=connection_value(project,role,model)
    if not value:
        raise ValueError(tr(u'Журнал не подключён. Откройте «Подключение таблицы» и введите адрес и токен отдела.',
                            u'Journal is not connected. Open Sheet connection and enter the URL and department token.'))
    validate_url(value['url'])
    return dict(url=value['url'],token=crypt(value['token_dpapi'],True),discipline=canonical_discipline(value.get('discipline','')))


def save_connection(project,role,model,url,token,sheet_url='',shared=False,all_projects=False,discipline=''):
    validate_url(url)
    if not token.strip():
        raise ValueError(tr(u'Введите токен подключения',u'Enter a connection token'))
    config=connection_store()
    data=config.read()
    data[scope_key('*' if all_projects else project,role,'*' if shared or all_projects else model)]=dict(url=url,token_dpapi=crypt(token.strip()),sheet_url=sheet_url,discipline=discipline)
    if not config.write(data):
        raise ValueError(tr(u'Подключение журнала не сохранено',u'Journal connection was not saved'))


def snapshot(registry,project,role,model,title,rows=None,revit_user='',windows_user=''):
    """Full released records/history, scoped to one project and originating model."""
    if role not in ('VIS','KR','AR') or not project or not model:
        raise ValueError(tr(u'Не задан проект, модель или роль журнала',u'Journal project, model or role is missing'))
    value=dict(schema=1,project=project,role=role,model=model,model_title=title,
               revit_user=revit_user,windows_user=windows_user,
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
        value['remark_groups']={key:copy.deepcopy(group) for key,group in registry.get('remark_groups',{}).items() if own(group)}
    # UI diagnostics are observations, never formal releases or acceptance.
    for row in rows or []:
        if role=='VIS' and row.get('task_id') not in value['tasks']:
            continue
        value['working'].append({key:copy.deepcopy(row[key]) for key in (
            'key','number','object_part','task_id','status','result','recipient','discipline','level','kind',
            'remark_number','remark_group_id','remark_state','revision','date','sizes','previous_sizes','displacement','comment','next_action','attention') if key in row})
    return value


def request(connection, action, payload, track=False):
    # Shared transport; no Notes settings, credentials, requests or cancellation state.
    call=TRANSPORT.call
    payload=dict(payload)
    if connection.get('discipline'):
        payload['discipline']=connection['discipline']
    return call(action,payload,url=connection['url'],token=connection['token'],
                timeout_ms=25000,retries=0,track=track)




def discover_connection(url,token,track=False,project=None,role=None,model=None):
    """Read the department from the token, without asking the employee for it."""
    validate_url(url)
    if not token.strip():
        raise ValueError(tr(u'Введите токен отдела',u'Enter the department token'))
    from lowlife.cloud_io import ApiError
    try:
        result=request(dict(url=url,token=token),'connect',{},track=track)
    except ApiError as ex:
        if ex.args and ex.args[0]=='DEPARTMENT_REQUIRED':
            raise ValueError(tr(u'У старого токена не указан отдел. Администратору нужно выдать новый токен отдела.',
                                u'This legacy token has no department. Ask the administrator for a department token.'))
        raise
    department=canonical_discipline(result.get('department') or result.get('discipline'))
    if not department or INSTALL_DISCIPLINES.get(department)!=result.get('role'):
        raise ValueError(tr(u'Не удалось определить отдел по токену. Обновите Apps Script и проверьте токен.',
                            u'Could not identify the department from the token. Update Apps Script and check the token.'))
    if ((role and result['role']!=role) or
            (result.get('project') and project and result['project']!=project) or
            (result.get('model') and model and result['model']!=model)):
        raise ValueError(tr(u'Токен отдела {} не подходит для этого интерфейса или модели.',
                            u'The {} department token does not match this interface or model.').format(department))
    if result.get('credential_scope') not in ('group','project_group','model'):
        raise ValueError(tr(u'Формат подключения не поддерживается. Обновите Apps Script.',
                            u'Unsupported connection format. Update Apps Script.'))
    result=dict(result,department=department,discipline=department)
    return result


def in_background(window,work,done):
    from lowlife import background
    return background.in_background(window,work,done,TRANSPORT)


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



def windows_user():
    user=os.environ.get('USERNAME') or os.environ.get('USER') or ''
    domain=os.environ.get('USERDOMAIN') or ''
    return domain+u'\\'+user if domain and user else user


def capture(window,settings):
    from lowlife import opening_tasks_storage as storage
    doc=window.document
    data=snapshot(storage.registry(doc),settings['opening_project'],window.role,
                  storage.model_id(doc),unicode(doc.Title),window.rows,
                  revit_user=unicode(doc.Application.Username or ''),
                  windows_user=windows_user())
    if window.role in ('KR','AR'):
        from lowlife import opening_tasks_revit as api
        for key,receipt in data['receipts'].items():
            opening=doc.GetElement(receipt['opening_uid']) if receipt.get('opening_uid') else None
            data['observations'][key]=dict(exists=opening is not None,
                matches=bool(opening is not None and api.opening_matches(opening,receipt)))
    # The transaction is committed; saving/synchronizing the RVT remains explicit.
    return data


def auto_publish(window,settings):
    with QueueLock('lowlife_opening_journal_queue'):
        store=queue_store()
        data=store.read()
        data['items']=enqueue(data.get('items',[]),capture(window,settings))
        if not store.write(data,notify=False):
            raise ValueError(tr(u'Изменения в модели зафиксированы, но очередь журнала не сохранена. Обратитесь к администратору.',
                                u'Model changes were committed, but the journal queue was not saved. Contact the administrator.'))
    retry_pending(window)


def drain_pending(store,send,lock):
    """Read without holding a network lock; acknowledge only delivered IDs."""
    with lock():
        items=store.read().get('items',[])
    sent,blocked=deliver(items,send)
    if sent:
        with lock():
            data=store.read()
            data['items']=[i for i in data.get('items',[]) if i['id'] not in set(sent)]
            store.write(data,notify=False)
    return sent,blocked


def install_sender():
    """One process-wide timer; no model, window, Dispatcher or Revit API required."""
    from System import AppDomain
    from System.Threading import Timer, TimerCallback
    domain=AppDomain.CurrentDomain
    with QueueLock('lowlife_opening_journal_queue'):
        if domain.GetData('lowlife_opening_journal_timer') is not None:
            return
        def tick(state):
            try:
                retry_pending()
            except Exception:
                pass
        timer=Timer(TimerCallback(tick),None,60000,60000)
        domain.SetData('lowlife_opening_journal_timer',timer)


def retry_pending(window=None):
    """Silent background attempts now and every minute, even with closed windows."""
    from System import AppDomain
    from System.Threading import Thread, ThreadStart
    install_sender()
    domain=AppDomain.CurrentDomain
    flag='lowlife_opening_journal_sending'
    with QueueLock('lowlife_opening_journal_queue'):
        if domain.GetData(flag) or not queue_store().read().get('items',[]):
            return
        domain.SetData(flag,True)
    def worker():
        try:
            def send(item):
                scope=item['scope']
                connection=load_connection(scope['project'],scope['role'],scope['model'])
                status=request(connection,'status',scope)
                request(connection,'publish',dict(scope,base_version=status['version'],payload=item['payload']))
            drain_pending(queue_store(),send,lambda:QueueLock('lowlife_opening_journal_queue'))
        except Exception:
            pass
        finally:
            with QueueLock('lowlife_opening_journal_queue'):
                domain.SetData(flag,None)
    thread=Thread(ThreadStart(worker))
    thread.IsBackground=True
    try:
        thread.Start()
    except Exception:
        with QueueLock('lowlife_opening_journal_queue'):
            domain.SetData(flag,None)


def setup(doc,role,project):
    """Per-user connection UI; the server token determines department and role."""
    from pyrevit import forms
    from lowlife import opening_tasks_storage as storage
    model=storage.model_id(doc)
    class ConnectionWindow(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self,u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
              xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Width="760" Height="530" MinHeight="430"
              WindowStartupLocation="CenterScreen">
              <ScrollViewer VerticalScrollBarVisibility="Auto">
              <StackPanel Margin="20">
                <TextBox x:Name="info" TextWrapping="Wrap" IsReadOnly="True" BorderThickness="0" Margin="0,0,0,16"/>
                <TextBlock x:Name="info_hint" Foreground="Gray" FontSize="11" TextWrapping="Wrap" Margin="0,0,0,12"/>
                <TextBlock x:Name="url_label"/>
                <TextBox x:Name="url" Margin="0,6,0,2"/>
                <TextBlock x:Name="url_hint" Foreground="Gray" FontSize="11" TextWrapping="Wrap" Margin="0,0,0,12"/>
                <TextBlock x:Name="token_label"/>
                <PasswordBox x:Name="token" Margin="0,6,0,2"/>
                <TextBlock x:Name="token_hint" Foreground="Gray" FontSize="11" TextWrapping="Wrap" Margin="0,0,0,16"/>
                <Button x:Name="guide" Padding="12,7" Margin="0,0,0,8"/>
                <Button x:Name="save" Padding="12,7"/>
              </StackPanel></ScrollViewer></Window>''',literal_string=True)
            self.Title=tr(u'Подключение журнала',u'Journal connection')
            installed=connection_value(project,role,model) or {}
            discipline=canonical_discipline(installed.get('discipline')) or ({'KR':u'КР','AR':u'АР'}.get(role)) or tr(u'Определится по токену',u'Determined by the token')
            self.info.Text=tr(u'Проект: {} | Отдел: {}\nID модели: {}',
                              u'Project: {} | Department: {}\nModel ID: {}').format(project,discipline,model)
            self.url_label.Text=tr(u'Адрес Google Apps Script',u'Google Apps Script URL')
            self.token_label.Text=tr(u'Токен',u'Token')
            self.info_hint.Text=tr(u'Шифр берётся из сведений о проекте. В меню LowLife Google-таблицы выберите отдел и выдайте его токен. При подключении отдел определяется автоматически. ID модели сохраняется в журнале и не ограничивает токен.',
                                   u'The code comes from Project Information. Select a department and issue its token in the Google sheet LowLife menu. The department is identified automatically on connection. The model ID is recorded in the journal, not bound to the token.')
            self.url_hint.Text=tr(u'Вставьте адрес развёрнутого веб-приложения Apps Script с окончанием /exec. Ссылка на саму Google-таблицу сюда не подходит.',
                                  u'Paste the deployed Apps Script web app URL ending in /exec. The spreadsheet URL cannot be used here.')
            self.token_hint.Text=tr(u'Настройка сохраняется только в вашем профиле Windows для всех моделей отдела. Общий токен отдела. Отдел определяется по токену; выбирать его повторно не нужно. Подходит для всех объектов и моделей отдела. Пользователи Revit и Windows записываются отдельно; токен хранится зашифрованным.',
                                    u'Saved only in your Windows profile for all department models. Shared department token. The department is identified from it without a second selection. Works across all department projects and models. Revit and Windows users are recorded separately; the token is stored encrypted.')
            self.guide.Content=tr(u'Инструкция подключения Google',u'Google connection guide')
            self.guide.Click+=self.open_guide
            self.save.Content=tr(u'Проверить и сохранить',u'Check and save')
            self.save.ToolTip=tr(u'Проверяет доступ в фоне. Сохраняет подключение только после успешного ответа Google.',
                                 u'Checks access in the background. Saves the connection only after Google responds successfully.')
            self.save.Click+=self.on_save
        def open_guide(self,sender,event):
            from pyrevit import script
            script.open_url('https://github.com/avpersiyanov-afk/LowLife/blob/main/docs/opening-journal/README.md')
        def on_save(self,sender,event):
            try:
                url=validate_url(unicode(self.url.Text).strip())
                token=unicode(self.token.Password).strip()
                if not token:
                    raise ValueError(tr(u'Введите токен подключения',u'Enter a connection token'))
                self.save.IsEnabled=False
                self.url.IsEnabled=False
                self.token.IsEnabled=False
                def work():
                    return discover_connection(url,token,track=True,project=project,role=role,model=model)
                def done(result,error):
                    self.save.IsEnabled=True
                    self.url.IsEnabled=True
                    self.token.IsEnabled=True
                    if error is not None:
                        forms.alert(error)
                        return
                    try:
                        save_connection(project,role,model,url,token,result.get('sheet_url',''),
                                        shared=result.get('credential_scope') in ('group','project_group'),
                                        all_projects=result.get('credential_scope')=='group',discipline=result.get('discipline',''))
                        self.token.Password=''
                        self.Close()
                    except Exception as ex:
                        forms.alert(unicode(ex))
                in_background(self,work,done)
            except Exception as ex:
                self.save.IsEnabled=True
                self.url.IsEnabled=True
                self.token.IsEnabled=True
                forms.alert(unicode(ex))
    ConnectionWindow().ShowDialog()


def open_sheet(doc,role,project):
    from lowlife import opening_tasks_storage as storage
    from pyrevit import script
    value=connection_value(project,role,storage.model_id(doc)) or {}
    url=value.get('sheet_url','')
    if not re.match(r'^https://docs\.google\.com/spreadsheets/d/[A-Za-z0-9_-]+(?:/edit)?$',url):
        raise ValueError(tr(u'Нет ссылки на журнал. Переустановите подключение таблицы.',u'Journal link is missing. Reinstall the sheet connection.'))
    script.open_url(url)
