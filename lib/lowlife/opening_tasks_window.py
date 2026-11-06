# -*- coding: utf-8 -*-
"""Persistent modeless role interface. All Revit interaction uses ExternalEvent."""
try:
    unicode
except NameError:
    unicode = str

from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler
from Autodesk.Revit.DB import FamilyInstance, FilteredElementCollector, ElementId
from System.Collections.Generic import List
from System.Windows.Controls import Button, ListBoxItem
from System.Windows import Thickness
from pyrevit import forms
from lowlife.i18n import tr
from lowlife import opening_tasks_ui as flow
from lowlife import opening_tasks_storage as store
from lowlife import opening_tasks_revit as api
from lowlife import opening_tasks_settings as cfg
from lowlife import text_search

_WINDOWS = {}


class Handler(IExternalEventHandler):
    __namespace__ = "LowLife.OpeningTasks.Interface_" + api.core.guid().replace("-", "")
    def __init__(self, window):
        self.window=window
    def GetName(self):
        return 'LowLife opening tasks'
    def Execute(self, uiapp):
        w=self.window
        try:
            if uiapp.ActiveUIDocument is None or uiapp.ActiveUIDocument.Document != w.document:
                forms.alert(tr(u'Вернитесь в модель, для которой открыто окно.',u'Return to the model this window belongs to.'))
                return
            uidoc=uiapp.ActiveUIDocument
            action,rows=w.pending
            if action=='refresh':
                w.refresh()
                return
            if action=='settings':
                cfg.make(w.role).get_settings_interactive()
                w.refresh()
                return
            settings_form=cfg.make(w.role)
            settings=settings_form.get_settings_silent()
            settings_form.require(settings,['opening_project'])
            if action=='structures':
                from lowlife.opening_tasks_focus import run
                run(structures=True)
            elif action=='control':
                from lowlife.opening_tasks_views import run
                run()
            elif action=='place':
                settings_form.require(settings,['opening_json_param','box_width_param','box_depth_param','box_height_param','box_host_filter_param'])
                uidoc.Selection.SetElementIds(List[ElementId]())
                flow.place(settings)
            elif action=='confirm':
                settings_form.require(settings,['opening_json_param'])
                if not rows:
                    raise ValueError(tr(u'Выберите задания для подтверждения.',u'Select tasks to confirm.'))
                flow.confirm(settings,[row['task_id'] for row in rows])
            else:
                if not rows:
                    forms.alert(tr(u'Выберите задания в списке.',u'Select tasks in the list.'))
                    return
                if action=='focus':
                    from lowlife.opening_tasks_focus import focus
                    inst=w.document.GetElement(rows[0]['uid'])
                    if inst is None:
                        raise ValueError(tr(u'Бокс удалён. Обновите список.',u'Box was deleted. Refresh the list.'))
                    from pyrevit import revit
                    with revit.Transaction(tr(u'Просмотр бокса',u'Box preview')):
                        view,crop=focus(w.document,inst)
                    uidoc.ActiveView=view
                    uidoc.RefreshActiveView()
                    for ui in uidoc.GetOpenUIViews():
                        if ui.ViewId==view.Id:
                            ui.ZoomToFit()
                            break
                elif w.role=='KR':
                    # Reload records before acting: cached rows must never apply stale revisions.
                    fresh={api.core.task_key(r):r for r,link in api.incoming(w.document,settings['opening_project'])}
                    selected=[]
                    for row in rows:
                        record=fresh.get(api.core.task_key(row['record']))
                        if record != row['record']:
                            raise ValueError(tr(u'Выпуск изменился. Обновите список и проверьте выбор.',u'Release changed. Refresh and review the selection.'))
                        selected.append(record)
                    flow.kr(settings,action,selected)
                elif action=='issue':
                    settings_form.require(settings,['opening_discipline','opening_json_param','opening_status_param','opening_issue_param','opening_revision_param','opening_date_param'])
                    elements=[w.document.GetElement(row['uid']) for row in rows]
                    if any(e is None for e in elements):
                        raise ValueError(tr(u'Часть боксов удалена. Обновите список.',u'Some boxes were deleted. Refresh the list.'))
                    flow.publish(settings,elements)
                elif action=='withdraw':
                    settings_form.require(settings,['opening_json_param'])
                    tasks=store.registry(w.document)['tasks']
                    if any(row['task_id'] not in tasks or tasks[row['task_id']]['status']!='issued' for row in rows):
                        raise ValueError(tr(u'Для отзыва выберите только выданные задания.',u'Select issued tasks only for withdrawal.'))
                    flow.withdraw(settings,[row['task_id'] for row in rows])
            w.refresh()
        except Exception as ex:
            forms.alert(tr(u'Действие не выполнено: {}',u'Action failed: {}').format(unicode(ex)))
        finally:
            w.pending=None
            w.IsEnabled=True
            if not w.closed:
                w.Show()


class TaskWindow(forms.WPFWindow):
    def __init__(self,role,doc):
        forms.WPFWindow.__init__(self,u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
            xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Width="1150" Height="720"
            MinWidth="850" MinHeight="500" WindowStartupLocation="CenterScreen">
          <Grid Margin="18">
            <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/>
              <RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
            <TextBlock x:Name="heading" FontSize="20" FontWeight="Bold" Margin="0,0,0,12"/>
            <WrapPanel x:Name="actions" Grid.Row="1" Margin="0,0,0,8"/>
            <DockPanel Grid.Row="2" Margin="0,0,0,10">
              <ComboBox x:Name="state" Width="220" DockPanel.Dock="Right" Margin="12,0,0,0"/>
              <TextBox x:Name="search" Height="28"/>
            </DockPanel>
            <ListBox x:Name="tasks" Grid.Row="3" SelectionMode="Extended" FontFamily="Consolas" FontSize="13"
                 ScrollViewer.HorizontalScrollBarVisibility="Auto"/>
            <TextBlock x:Name="details" Grid.Row="4" TextWrapping="Wrap" Margin="0,12,0,0"/>
          </Grid>
        </Window>''',literal_string=True)
        self.role,self.document=role,doc
        self.pending=None
        self.closed=False
        self.rows=[]
        self.Title=tr(u'Задания ВИС',u'VIS tasks') if role=='VIS' else tr(u'Задания КР',u'KR tasks')
        self.heading.Text=self.Title+u' | '+doc.Title
        self.tasks.ToolTip=tr(u'Статус | GUID | Дисциплина | Выпуск | Ревизия | Дата | Размеры, мм | Элемент',
                             u'Status | GUID | Discipline | Issue | Revision | Date | Sizes, mm | Element')
        self.search.ToolTip=tr(u'Поиск по GUID, статусу, дисциплине, выпуску и размерам',u'Search GUID, status, discipline, issue and sizes')
        self.handler=Handler(self)
        self.event=ExternalEvent.Create(self.handler)
        self.add('refresh',tr(u'Обновить',u'Refresh'))
        self.add('settings',tr(u'Настройки',u'Settings'))
        if role=='VIS':
            actions=[('place',tr(u'Расставить боксы',u'Place boxes')),('issue',tr(u'Выдать КР',u'Issue to KR')),
                     ('withdraw',tr(u'Отозвать',u'Withdraw')),('confirm',tr(u'Подтвердить КР',u'Confirm KR')),
                     ('focus',tr(u'Бокс в 3D',u'Box in 3D')),('control',tr(u'Виды и реестр',u'Views and register'))]
        else:
            actions=[('show',tr(u'Показать конструкцию',u'Show host')),('accept',tr(u'Принять отдельно',u'Accept separately')),
                     ('merge',tr(u'Объединить',u'Merge')),('reject',tr(u'Замечание',u'Comment')),
                     ('remove',tr(u'Отработать отзыв',u'Process withdrawal')),('structures',tr(u'Вид конструкций',u'Structural view'))]
        for action,label in actions:
            self.add(action,label)
        self.search.TextChanged+=lambda s,e:self.render()
        self.state.SelectionChanged+=lambda s,e:self.render()
        self.tasks.SelectionChanged+=self.selection_changed
        self.Closed+=self.on_closed
        self.refresh()

    def add(self,action,label):
        button=Button()
        button.Content=label
        button.Padding=Thickness(10,6,10,6)
        button.Margin=Thickness(0,0,8,8)
        button.Click+=lambda s,e,a=action:self.dispatch(a)
        self.actions.Children.Add(button)

    def dispatch(self,action):
        if self.pending:
            return
        self.pending=(action,[item.Tag for item in self.tasks.SelectedItems])
        self.IsEnabled=False
        self.Hide()
        result=self.event.Raise()
        if unicode(result) not in ('Accepted','Pending'):
            self.pending=None
            self.IsEnabled=True
            self.Show()

    def refresh(self):
        settings=cfg.make(self.role).get_settings_silent()
        registry=store.registry(self.document)
        self.rows=[]
        if self.role=='VIS':
            found=set()
            for inst in FilteredElementCollector(self.document).OfClass(FamilyInstance):
                data=api.metadata(inst)
                if not data or data['owner_uid']!=inst.UniqueId:
                    continue
                found.add(data['task_id'])
                r=registry['tasks'].get(data['task_id'])
                self.rows.append(self.row(data['task_id'],inst.UniqueId,r,settings))
            for tid,r in registry['tasks'].items():
                if tid not in found and r['project']==settings.get('opening_project'):
                    self.rows.append(self.row(tid,r['owner_uid'],r,settings,True))
        elif settings.get('opening_project'):
            for r,link in api.incoming(self.document,settings['opening_project']):
                row=self.row(r['task_id'],r['owner_uid'],r,settings)
                row['status']=flow.state_label(flow.receipt_state(r,registry,self.document))
                row['record']=r
                self.rows.append(row)
        previous=self.state.SelectedItem
        self.state.Items.Clear()
        all_label=tr(u'Все статусы',u'All statuses')
        self.state.Items.Add(all_label)
        for status in sorted(set(row['status'] for row in self.rows)):
            self.state.Items.Add(status)
        self.state.SelectedItem=previous if previous in list(self.state.Items) else all_label
        self.render()

    def row(self,tid,uid,r,settings,missing=False):
        status=(u'Отозвано' if r and r['status']=='withdrawn' else u'Выдано' if r else u'Черновик')
        inst=self.document.GetElement(uid) if self.role=='VIS' else None
        if inst and settings.get('opening_status_param'):
            p=inst.LookupParameter(settings['opening_status_param'])
            if p and p.AsString():
                status=p.AsString()
        if missing:
            status=tr(u'Бокс удалён',u'Box deleted')
        if inst and r and r['status']=='issued':
            data=api.metadata(inst)
            link=self.document.GetElement(data['host_link_uid'])
            if link and link.GetLinkDocument():
                try:
                    if not api.core.geometry_equal(r['geometry'],api.host_geometry(inst,data,link)):
                        status=u'Изменено после выдачи'
                except Exception:
                    status=tr(u'Нужна проверка геометрии',u'Geometry requires review')
        dimensions=u' × '.join(u'{:.0f}'.format(float(v)) for v in r['geometry']['size_mm']) if r else u'—'
        if inst:
            try:
                data=api.metadata(inst)
                dimensions=u' × '.join(u'{:.0f}'.format(float(api.boxes.mm(api.read_size(inst,name)))) for name in data['size_params'])
            except Exception:
                pass
        return dict(task_id=tid,uid=uid,status=status,record=r,
                    info=u'{} | {} | {} | r{} | {} | {} | {}'.format(tid,r.get('discipline','') if r else '',
                         r.get('issue_number',r.get('issue_id','')) if r else '',r['revision'] if r else '—',
                         r['issued_at'] if r else '',dimensions,uid))

    def render(self):
        selected=set(item.Tag['task_id'] for item in self.tasks.SelectedItems)
        self.tasks.Items.Clear()
        for row in self.rows:
            text=row['status']+u' | '+row['info']
            if self.state.SelectedIndex>0 and self.state.SelectedItem!=row['status']:
                continue
            if not text_search.matches(text,self.search.Text):
                continue
            item=ListBoxItem()
            item.Content=text
            item.Tag=row
            item.IsSelected=row['task_id'] in selected
            self.tasks.Items.Add(item)
        self.details.Text=tr(u'Всего: {}. Показано: {}. Выберите строки и действие. Окно можно оставить открытым при работе в модели.',
                             u'Total: {}. Shown: {}. Select rows and an action. This window can stay open while working in the model.').format(len(self.rows),self.tasks.Items.Count)

    def selection_changed(self,sender,event):
        if self.tasks.SelectedItem:
            self.details.Text=self.tasks.SelectedItem.Content

    def on_closed(self,sender,event):
        self.closed=True
        _WINDOWS.pop(self.role,None)
        self.event.Dispose()


def show(role,config_mode=False):
    from pyrevit import revit
    if config_mode:
        cfg.make(role).get_settings_interactive()
        return
    existing=_WINDOWS.get(role)
    if existing and not existing.closed:
        existing.Show()
        existing.Activate()
        return
    window=TaskWindow(role,revit.doc)
    _WINDOWS[role]=window
    window.Show()
