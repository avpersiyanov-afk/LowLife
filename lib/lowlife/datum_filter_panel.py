# -*- coding: utf-8 -*-
"""One dockable panel per Revit process, shared across pyRevit engines.

WPF only queues requests. ExternalEvent performs reads and writes; Idling
refreshes a dirty visible pane after view/document/model changes (including undo).
The AppDomain reference keeps the provider, delegates and engine alive on reload.
"""
try:
    unicode
except NameError:
    unicode = str

import os
import uuid
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
from System import AppDomain, Guid
from System.Windows import Thickness
from System.Windows.Controls import CheckBox, TextBlock
from System.Windows.Markup import XamlReader
from Autodesk.Revit.UI import (DockablePane, DockablePaneId, DockablePaneState,
                              DockPosition, IDockablePaneProvider,
                              ExternalEvent, IExternalEventHandler, ExternalEventRequest)
from lowlife import datum_filter_revit as api
from lowlife import datum_filter_settings as cfg
from lowlife import text_search, xaml_i18n
from lowlife.i18n import tr

PANE_GUID = '910a856e-7f71-40e7-bbb9-a60b679d88dc'
STATE_KEY = 'LowLife.DatumFilter.Panel.v1'
_NAMESPACE = 'LowLife.DatumFilter.N' + uuid.uuid4().hex


def pane_id():
    return DockablePaneId(Guid(PANE_GUID))


class Handler(IExternalEventHandler):
    __namespace__ = _NAMESPACE

    def __init__(self, panel):
        self.panel = panel

    def GetName(self):
        return 'LowLife datum visibility'

    def Execute(self, uiapp):
        panel = self.panel
        request = panel.pending
        panel.pending = None
        try:
            if request is None:
                return
            action, document, view_id, items, show = request
            uidoc = uiapp.ActiveUIDocument
            if action == 'visibility':
                if (uidoc is None or uidoc.Document != document
                        or uidoc.ActiveView.Id != view_id):
                    panel.refresh(uiapp)
                    panel.status_label.Text = tr(u'Вид изменился. Повторите действие на нужном виде.')
                    return
                changed, skipped = api.apply_visibility(document, uidoc.ActiveView, items, show)
                panel.refresh(uiapp)
                panel.status_label.Text += u'\n' + tr(u'Изменено: {0}. Пропущено: {1}.').format(changed, skipped)
            else:
                if action == 'settings':
                    panel.edit_settings()
                panel.refresh(uiapp)
        except Exception as exc:
            # Rebuild checkboxes from actual state after a failed transaction.
            try:
                panel.refresh(uiapp)
            except Exception:
                panel.clear()
            panel.status_label.Text = tr(u'Ошибка: {0}').format(unicode(exc))
        finally:
            panel.set_busy(False)


class Panel(IDockablePaneProvider):
    __namespace__ = _NAMESPACE

    def __init__(self, uiapp):
        self.uiapp = uiapp
        self.page = XamlReader.Parse(xaml_i18n.load(
            os.path.join(os.path.dirname(__file__), 'datum_filter.xaml')))
        for name in ('view_label', 'refresh_button', 'settings_button', 'search_box',
                     'mask_label', 'status_label', 'groups_panel'):
            setattr(self, name, self.page.FindName(name))
        self.groups = []
        self.document = None
        self.view_id = None
        self.pending = None
        self.dirty = True
        self.handler = Handler(self)
        self.event = ExternalEvent.Create(self.handler)
        self.refresh_button.Click += self.on_refresh
        self.settings_button.Click += self.on_settings
        self.search_box.TextChanged += self.on_search
        self.page.IsVisibleChanged += self.on_visible

    def SetupDockablePane(self, data):
        data.FrameworkElement = self.page
        data.VisibleByDefault = False
        state = DockablePaneState()
        state.DockPosition = DockPosition.Right
        data.InitialState = state

    def subscribe(self):
        self.uiapp.ViewActivated += self.on_changed
        self.uiapp.Application.DocumentChanged += self.on_changed
        self.uiapp.Application.DocumentClosing += self.on_changed
        self.uiapp.Idling += self.on_idle

    def on_changed(self, sender, args):
        self.dirty = True

    def on_visible(self, sender, args):
        self.dirty = True

    def on_idle(self, sender, args):
        if not self.dirty or self.pending is not None or not self.page.IsVisible:
            return
        try:
            self.refresh(sender)
        except Exception as exc:
            self.clear()
            self.status_label.Text = tr(u'Ошибка: {0}').format(unicode(exc))
            self.dirty = False

    def clear(self):
        self.groups = []
        self.document = None
        self.view_id = None
        self.groups_panel.Children.Clear()
        self.mask_label.Text = u''

    def refresh(self, uiapp):
        self.dirty = False
        uidoc = uiapp.ActiveUIDocument
        self.clear()
        if uidoc is None:
            self.view_label.Text = tr(u'Откройте модель Revit.')
            self.status_label.Text = u''
            return
        doc, view = uidoc.Document, uidoc.ActiveView
        self.view_label.Text = u'{0} — {1}'.format(doc.Title, view.Name)
        if doc.IsFamilyDocument or not api.supported(view):
            self.status_label.Text = tr(u'Выберите план, разрез, фасад или 3D-вид проекта.')
            return
        self.groups, unmatched, mask, is_3d = api.snapshot(doc, view, cfg.SETTINGS.get_settings_silent())
        self.document, self.view_id = doc, view.Id
        self.mask_label.Text = tr(u'{0}. Маска: {1}').format(
            tr(u'Уровни') if is_3d else tr(u'Оси'), mask)
        self.status_label.Text = tr(u'Групп: {0}. Вне маски: {1}.').format(len(self.groups), unmatched)
        self.status_label.Text += u'\n' + tr(u'Галочки управляют скрытием элементов. Категория, шаблон и границы вида могут ограничивать видимость. Только элементы текущей модели.')
        self.render_groups()

    def render_groups(self):
        self.groups_panel.Children.Clear()
        for group in self.groups:
            if not text_search.matches(group['name'] + u' ' + u' '.join(
                    item['name'] for item in group['items']), self.search_box.Text):
                continue
            check = CheckBox()
            group_label = TextBlock()
            group_label.Text = u'{0} ({1})'.format(group['name'], len(group['items']))
            check.Content = group_label
            check.ToolTip = u'\n'.join(item['name'] for item in group['items'])
            check.Margin = Thickness(0, 5, 0, 5)
            check.IsThreeState = True
            check.IsChecked = group['checked']
            check.IsEnabled = any(item['hideable'] for item in group['items'])
            check.Tag = group
            check.Click += self.on_toggle
            self.groups_panel.Children.Add(check)

    def set_busy(self, busy):
        self.groups_panel.IsEnabled = not busy
        self.refresh_button.IsEnabled = not busy
        self.settings_button.IsEnabled = not busy
        self.search_box.IsEnabled = not busy

    def request(self, action, items=None, show=None):
        if self.pending is not None:
            return
        self.pending = (action, self.document, self.view_id, items, show)
        self.set_busy(True)
        try:
            result = self.event.Raise()
        except Exception as exc:
            self.pending = None
            self.set_busy(False)
            self.dirty = True
            self.status_label.Text = tr(u'Ошибка: {0}').format(unicode(exc))
            return
        if result not in (ExternalEventRequest.Accepted, ExternalEventRequest.Pending):
            self.pending = None
            self.set_busy(False)
            self.dirty = True
            self.status_label.Text = tr(u'Revit занят. Повторите действие.')

    def on_toggle(self, sender, args):
        # WPF's three-state cycle includes None. Use the snapshot to make
        # clicks deterministic: checked -> hide; mixed/unchecked -> show.
        group = sender.Tag
        show = group['checked'] is not True
        sender.IsChecked = show
        self.request('visibility', group['items'], show)

    def on_refresh(self, sender, args):
        self.request('refresh')

    def on_settings(self, sender, args):
        self.request('settings')

    def on_search(self, sender, args):
        self.render_groups()

    def edit_settings(self):
        cfg.SETTINGS.get_settings_interactive()


def install(uiapp):
    """Also callable on the first button click after deploying without restart."""
    existing = AppDomain.CurrentDomain.GetData(STATE_KEY)
    if existing is not None:
        return existing
    if DockablePane.PaneIsRegistered(pane_id()):
        raise RuntimeError(tr(u'Для обновления панели перезапустите Revit.'))
    panel = Panel(uiapp)
    try:
        uiapp.RegisterDockablePane(pane_id(), tr(u'Фильтр осей и уровней'), panel)
    except Exception:
        panel.event.Dispose()
        raise
    AppDomain.CurrentDomain.SetData(STATE_KEY, panel)
    panel.subscribe()
    return panel


def show(uiapp, settings=False):
    panel = install(uiapp)
    if settings:
        panel.edit_settings()
    panel.refresh(uiapp)
    if not DockablePane.PaneExists(pane_id()):
        raise RuntimeError(tr(u'Панель зарегистрирована. Перезапустите Revit, чтобы открыть закрепляемую панель.'))
    uiapp.GetDockablePane(pane_id()).Show()
