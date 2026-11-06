# -*- coding: utf-8 -*-
"""Persistent modeless role interface. All Revit interaction uses ExternalEvent."""
try:
    unicode
except NameError:
    unicode = str

from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler
from Autodesk.Revit.DB import FamilyInstance, FilteredElementCollector, ElementId
from System.Collections.Generic import List
import clr
clr.AddReference("System.Data")
from System.Windows.Controls import Button, DataGridTextColumn, DataGridLength, DataGridRow
from System.Windows.Media import VisualTreeHelper
from System.Windows.Data import Binding
from System.Data import DataTable
from System import String, Int32
from System.Windows import Thickness
from pyrevit import forms
from lowlife.i18n import tr
from lowlife import opening_tasks_ui as flow
from lowlife import opening_tasks_storage as store
from lowlife import opening_tasks_revit as api
from lowlife import opening_tasks_settings as cfg
from lowlife import opening_tasks_manifest as manifest
from lowlife import text_search
from lowlife import opening_tasks_browser as browser

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
            manifest.validate_action(w.role,action)
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
            if action in ('kr_plans','kr_sections'):
                from lowlife.opening_tasks_kr_views import build
                from pyrevit import revit, script
                with revit.Transaction(tr(u'Виды контроля КР',u'KR control views')):
                    views=build(w.document,settings['opening_project'],
                                'plans' if action=='kr_plans' else 'sections',
                                [row['record'] for row in rows] if rows else None)
                for view in views:
                    script.get_output().print_md(u'- {}: {}'.format(view.Name,script.get_output().linkify(view.Id)))
                forms.alert(tr(u'Создано/обновлено видов: {}. Ссылки — в окне вывода.',
                               u'Views created/updated: {}. See output links.').format(len(views)))
            elif action=='structures':
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
        manifest.validate_role(role)
        forms.WPFWindow.__init__(self,u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
            xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Width="1150" Height="720"
            MinWidth="850" MinHeight="500" WindowStartupLocation="CenterScreen">
          <Grid Margin="18">
            <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/>
              <RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
            <TextBlock x:Name="heading" FontSize="20" FontWeight="Bold" Margin="0,0,0,12"/>
            <WrapPanel x:Name="actions" Grid.Row="1" Margin="0,0,0,8"/>
            <StackPanel Grid.Row="2" Margin="0,0,0,10">
              <TextBox x:Name="search" Height="28" Margin="0,0,0,8"/>
              <WrapPanel>
                <ComboBox x:Name="state" Width="190" Margin="0,0,8,6"/>
                <ComboBox x:Name="discipline_filter" Width="145" Margin="0,0,8,6"/>
                <ComboBox x:Name="level_filter" Width="170" Margin="0,0,8,6"/>
                <ComboBox x:Name="kind_filter" Width="150" Margin="0,0,8,6"/>
                <ComboBox x:Name="issue_filter" Width="130" Margin="0,0,8,6"/>
                <CheckBox x:Name="attention" VerticalAlignment="Center" Margin="0,0,8,6"/>
                <Button x:Name="reset" Padding="10,4"/>
              </WrapPanel>
            </StackPanel>
            <DataGrid x:Name="tasks" Grid.Row="3" SelectionMode="Extended" SelectionUnit="FullRow"
                 IsReadOnly="True" AutoGenerateColumns="False" CanUserAddRows="False"
                 CanUserSortColumns="True" CanUserReorderColumns="True"/>
            <ScrollViewer Grid.Row="4" MaxHeight="170" VerticalScrollBarVisibility="Auto"><TextBlock x:Name="details" TextWrapping="Wrap" Margin="0,12,0,0"/></ScrollViewer>
          </Grid>
        </Window>''',literal_string=True)
        self.role,self.document=role,doc
        self.manifest_version=manifest.VERSION
        self.pending=None
        self.closed=False
        self.rows=[]
        self.updating=False
        self.visible={}
        self.Title=tr(u'Задания ВИС',u'VIS tasks') if role=='VIS' else tr(u'Задания КР',u'KR tasks')
        purpose=tr(u'Подготовка и выдача заданий',u'Prepare and issue tasks') if role=='VIS' else tr(u'Рассмотрение и создание отверстий',u'Review and create openings')
        self.heading.Text=self.Title+u' — '+purpose+u' | '+doc.Title
        self.filter_controls=[('status',self.state,tr(u'Все статусы',u'All statuses')),
            ('discipline',self.discipline_filter,tr(u'Все дисциплины',u'All disciplines')),
            ('level',self.level_filter,tr(u'Все уровни',u'All levels')),
            ('kind',self.kind_filter,tr(u'Все конструкции',u'All hosts')),
            ('issue',self.issue_filter,tr(u'Все выпуски',u'All issues'))]
        self.attention.Content=tr(u'Требуют внимания',u'Need attention')
        self.reset.Content=tr(u'Сбросить фильтры',u'Reset filters')
        self.search.ToolTip=tr(u'Поиск по номеру, GUID, модели, уровню и размерам',u'Search number, GUID, model, level and sizes')
        self.columns=[('Number',tr(u'Задание',u'Task'),150),('Status',tr(u'Статус',u'Status'),170),
            ('Discipline',tr(u'Дисциплина',u'Discipline'),95),('Model',tr(u'Модель',u'Model'),140),
            ('Level',tr(u'Уровень',u'Level'),120),('Kind',tr(u'Конструкция',u'Host'),100),
            ('Issue',tr(u'Выпуск',u'Issue'),90),('Revision',tr(u'Ревизия',u'Revision'),75),
            ('Date',tr(u'Дата выдачи',u'Issue date'),155),('Sizes',tr(u'Размеры, мм',u'Sizes, mm'),150)]
        for key,label,width in self.columns:
            column=DataGridTextColumn()
            column.Header=label
            column.Binding=Binding(key)
            column.Width=DataGridLength(float(width))
            self.tasks.Columns.Add(column)
        self.handler=Handler(self)
        self.event=ExternalEvent.Create(self.handler)
        self.add('refresh',tr(u'Обновить',u'Refresh'))
        self.add('settings',tr(u'Настройки',u'Settings'))
        select_button=Button()
        select_button.Content=tr(u'Выбрать показанные',u'Select visible')
        select_button.Padding=Thickness(10,6,10,6)
        select_button.Margin=Thickness(0,0,8,8)
        select_button.Click+=lambda s,e:self.tasks.SelectAll()
        self.actions.Children.Add(select_button)
        for action,label in manifest.actions(role):
            self.add(action,tr(label))
        self.search.TextChanged+=lambda s,e:self.render()
        for key,control,label in self.filter_controls:
            control.SelectionChanged+=lambda s,e:self.render()
        self.attention.Checked+=lambda s,e:self.render()
        self.attention.Unchecked+=lambda s,e:self.render()
        self.reset.Click+=self.reset_filters
        self.tasks.SelectionChanged+=self.selection_changed
        self.tasks.MouseDoubleClick+=self.open_row
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
        try:
            manifest.validate_action(self.role,action)
        except ValueError as ex:
            forms.alert(unicode(ex))
            return
        if self.pending:
            return
        self.pending=(action,self.selected_rows())
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
                row['model']=link.Name
                row['attention']=flow.receipt_state(r,registry,self.document) not in ('accepted','withdrawn')
                receipt=registry['receipts'].get(api.core.task_key(r))
                row['comment']=receipt.get('comment','') if receipt else ''
                if receipt:
                    prior=next((t for t in receipt.get('issued_tasks',[]) if api.core.task_key(t)==api.core.task_key(r)),None)
                    if prior:
                        row['previous_sizes']=self.sizes(prior['geometry']['size_mm'])
                self.rows.append(row)
        self.updating=True
        for key,control,label in self.filter_controls:
            previous=control.SelectedItem
            control.Items.Clear()
            control.Items.Add(label)
            for value in sorted(set(row.get(key,'') for row in self.rows)):
                if value:
                    control.Items.Add(value)
            control.SelectedItem=previous if previous in list(control.Items) else label
        self.updating=False
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
        if inst and r and r['status']=='issued' and (link is None or link.GetLinkDocument() is None):
            status=tr(u'Связь не загружена',u'Link unloaded')
        raw_status=status
        status=tr(status)
        dimensions=u' × '.join(u'{:.0f}'.format(float(v)) for v in r['geometry']['size_mm']) if r else u'—'
        if inst:
            try:
                data=api.metadata(inst)
                dimensions=u' × '.join(u'{:.0f}'.format(float(api.boxes.mm(api.read_size(inst,name)))) for name in data['size_params'])
            except Exception:
                pass
        data=api.metadata(inst) if inst else None
        geometry=r['geometry'] if r else None
        host_doc=self.document
        host=None
        if self.role=='VIS' and data:
            link=self.document.GetElement(data['host_link_uid'])
            host_doc=link.GetLinkDocument() if link else None
            host=host_doc.GetElement(data['host_uid']) if host_doc else None
        elif geometry:
            host=self.document.GetElement(geometry['host_uid'])
        level=host_doc.GetElement(host.LevelId) if host is not None else None
        kind=geometry['kind'] if geometry else data.get('kind','') if data else ''
        discipline=r.get('discipline','') if r else settings.get('opening_discipline','')
        number=(u'{}-ОТВ-{:05d}'.format(discipline,r['task_number']) if r and r.get('task_number') else
                u'{}-{}'.format(discipline,tid[:8]))
        displacement=u'—'
        if inst and r and data:
            link=self.document.GetElement(data['host_link_uid'])
            if link and link.GetLinkDocument():
                try:
                    current=api.host_geometry(inst,data,link)['center_mm']
                    displacement=u' / '.join(u'{:+.1f}'.format(float(a-b)) for a,b in zip(current,r['geometry']['center_mm']))
                except Exception:
                    pass
        return dict(task_id=tid,uid=uid,status=status,record=r,key=browser.row_key(r,tid),displacement=displacement,
                    number=number,discipline=discipline,model=self.document.Title,
                    level=level.Name if level else u'—',
                    kind=tr(u'Стена',u'Wall') if kind=='wall' else tr(u'Перекрытие',u'Floor') if kind=='floor' else u'—',
                    issue=unicode(r.get('issue_number',r.get('issue_id',''))) if r else '',
                    revision=r['revision'] if r else 0,date=r['issued_at'] if r else '',sizes=dimensions,
                    previous_sizes=self.sizes(r['geometry']['size_mm']) if r else u'—',comment='',
                    attention=missing or raw_status not in (u'Выдано',u'Отозвано'))

    def sizes(self,values):
        return u' × '.join(u'{:.0f}'.format(float(v)) for v in values)

    def open_row(self,sender,event):
        node=event.OriginalSource
        try:
            while node is not None and not isinstance(node,DataGridRow):
                node=VisualTreeHelper.GetParent(node)
        except Exception:
            return
        if node is not None and self.selected_rows():
            event.Handled=True
            self.dispatch('focus' if self.role=='VIS' else 'show')

    def selected_rows(self):
        return [self.visible[item['Key']] for item in self.tasks.SelectedItems if item['Key'] in self.visible]

    def reset_filters(self,sender,event):
        self.updating=True
        self.search.Text=''
        for key,control,label in self.filter_controls:
            control.SelectedIndex=0
        self.attention.IsChecked=False
        self.updating=False
        self.render()

    def render(self):
        if self.updating:
            return
        selected=set(row['key'] for row in self.selected_rows())
        filters={key:unicode(control.SelectedItem) for key,control,label in self.filter_controls if control.SelectedIndex>0}
        for row in self.rows:
            row['search_text']=u' '.join(unicode(row.get(key,'')) for key in
                ('number','task_id','status','discipline','model','level','kind','issue','date','sizes'))
        visible=browser.select_rows(self.rows,filters,self.search.Text,bool(self.attention.IsChecked))
        table=DataTable()
        table.Columns.Add('Key',String)
        for key,label,width in self.columns:
            table.Columns.Add(key,Int32 if key=='Revision' else String)
        self.visible={row['key']:row for row in visible}
        for row in visible:
            item=table.NewRow()
            item['Key']=row['key']
            for column,key in [('Number','number'),('Status','status'),('Discipline','discipline'),('Model','model'),
                               ('Level','level'),('Kind','kind'),('Issue','issue'),('Revision','revision'),('Date','date'),('Sizes','sizes')]:
                item[column]=row[key]
            table.Rows.Add(item)
        self.tasks.ItemsSource=table.DefaultView
        for item in self.tasks.Items:
            if item['Key'] in selected:
                self.tasks.SelectedItems.Add(item)
        self.details.Text=tr(u'Всего: {}. По фильтрам: {}. Ctrl/Shift — выбор нескольких строк. Фильтры не меняют данные заданий.',
                             u'Total: {}. Filtered: {}. Ctrl/Shift selects multiple rows. Filters do not change task data.').format(len(self.rows),len(visible))

    def selection_changed(self,sender,event):
        rows=self.selected_rows()
        if rows:
            row=rows[0]
            self.details.Text=tr(u'Выбрано: {} | {} | {}\nВыданные / ранее принятые размеры: {} мм → Текущие: {} мм\nСмещение XYZ от выдачи, мм: {}\nGUID: {} | Элемент: {}\nЗамечание КР: {}',
                                u'Selected: {} | {} | {}\nIssued / previously accepted sizes: {} mm → Current: {} mm\nXYZ movement since issue, mm: {}\nGUID: {} | Element: {}\nKR comment: {}').format(
                len(rows),row['number'],row['status'],row['previous_sizes'],row['sizes'],row['displacement'],row['task_id'],row['uid'],row.get('comment','') or u'—')

    def on_closed(self,sender,event):
        self.closed=True
        _WINDOWS.pop(self.role,None)
        self.event.Dispose()


def show(role,config_mode=False):
    from pyrevit import revit
    manifest.validate_role(role)
    if config_mode:
        cfg.make(role).get_settings_interactive()
        return
    existing=_WINDOWS.get(role)
    if existing and not existing.closed and (getattr(existing,'manifest_version',None)!=manifest.VERSION or existing.document!=revit.doc or existing.role!=role):
        existing.Close()
        existing=None
    if existing and not existing.closed:
        existing.Show()
        existing.Activate()
        return
    window=TaskWindow(role,revit.doc)
    _WINDOWS[role]=window
    window.Show()
