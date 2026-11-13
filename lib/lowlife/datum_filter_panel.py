# -*- coding: utf-8 -*-
"""One dockable panel per Revit process, shared across pyRevit engines.

WPF only queues requests. ExternalEvent performs reads and writes; Idling
refreshes a dirty visible pane after view/document/model changes (including undo).
The AppDomain reference keeps the provider, delegates and engine alive on reload.
User presets (named masks + per-group visibility) are stored per model in the
button's settings file and edited by the WPF thread directly (file IO only).
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
from System.Windows import Thickness, Visibility
from System.Windows.Controls import CheckBox, TextBlock
from System.Windows.Input import Keyboard, ModifierKeys
from System.Windows.Markup import XamlReader
from System.Windows.Media import Brushes
from Autodesk.Revit.UI import (DockablePane, DockablePaneId, DockablePaneState,
                              DockPosition, IDockablePaneProvider,
                              ExternalEvent, IExternalEventHandler, ExternalEventRequest)
from pyrevit import forms
from lowlife import datum_filter_core as core
from lowlife import datum_filter_revit as api
from lowlife import datum_filter_presets as presets
from lowlife import datum_filter_settings as cfg
from lowlife import select_list, text_search, xaml_i18n
from lowlife.i18n import N_, tr

PANE_GUID = '910a856e-7f71-40e7-bbb9-a60b679d88dc'
STATE_KEY = 'LowLife.DatumFilter.Panel.v1'
_NAMESPACE = 'LowLife.DatumFilter.N' + uuid.uuid4().hex

NONE_ITEM_INDEX = 0


class FilterDefinition(object):
    """Shared dockable UI with a separate adapter, settings and pane identity."""
    def __init__(self, adapter=api, settings=cfg, mask_keys=presets.MASK_KEYS,
                 guid=PANE_GUID, state_key=STATE_KEY,
                 title=N_(u'Фильтр осей и уровней'), hint=None, manage=False, snapshot_caption=False):
        self.api = adapter
        self.cfg = settings
        self.mask_keys = mask_keys
        self.guid = guid
        self.state_key = state_key
        self.title = title
        self.hint = hint
        self.manage = manage
        self.snapshot_caption = snapshot_caption


DEFAULT_FILTER = FilterDefinition()


def pane_id(definition=None):
    return DockablePaneId(Guid((definition or DEFAULT_FILTER).guid))


class Handler(IExternalEventHandler):
    __namespace__ = _NAMESPACE

    def __init__(self, panel):
        self.panel = panel

    def GetName(self):
        return 'LowLife visibility filter'

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
                changed, skipped = panel.api.apply_visibility(document, uidoc.ActiveView, items, show)
                panel.refresh(uiapp)
                panel.status_label.Text += u'\n' + tr(u'Изменено: {0}. Пропущено: {1}.').format(changed, skipped)
            elif action == 'visibility_map':
                # items — [(items, show), ...] от клика с Shift/Ctrl по списку групп.
                if (uidoc is None or uidoc.Document != document
                        or uidoc.ActiveView.Id != view_id):
                    panel.refresh(uiapp)
                    panel.status_label.Text = tr(u'Вид изменился. Повторите действие на нужном виде.')
                    return
                changed, skipped = panel.api.apply_visibility_map(document, uidoc.ActiveView, items)
                panel.refresh(uiapp)
                panel.status_label.Text += u'\n' + tr(u'Изменено: {0}. Пропущено: {1}.').format(changed, skipped)
            elif action == 'apply_preset':
                # items carries the preset dict; the write targets the current view.
                if (uidoc is None or uidoc.Document != document
                        or uidoc.ActiveView.Id != view_id):
                    panel.refresh(uiapp)
                    panel.status_label.Text = tr(u'Модель изменилась. Повторите действие.')
                    return
                view = uidoc.ActiveView
                panel.masks = tuple(items[key] for key in panel.mask_keys)
                settings = panel.cfg.SETTINGS.get_settings_silent()
                settings.update(zip(panel.mask_keys, panel.masks))
                groups, _, _, _ = panel.api.snapshot(document, view, settings)
                changed, skipped = panel.api.apply_visibility_map(
                    document, view, presets.plan_changes(groups, items['visibility']))
                panel.refresh(uiapp)
                panel.status_label.Text += u'\n' + tr(
                    u'Группа «{0}» применена. Изменено: {1}. Пропущено: {2}.').format(
                    items['name'], changed, skipped)
            elif action == 'apply_views':
                # items — (grid_mask, level_mask, saved_map): текущие маски и
                # видимость групп переносятся на выбранные пользователем виды.
                if uidoc is None or uidoc.Document != document:
                    panel.refresh(uiapp)
                    panel.status_label.Text = tr(u'Модель изменилась. Повторите действие.')
                    return
                grid_mask, level_mask, saved_map = items
                settings = panel.cfg.SETTINGS.get_settings_silent()
                settings.update(zip(panel.mask_keys, (grid_mask, level_mask)))
                views = select_list.select_views(
                    title=N_(u'Виды, на которых применить видимость'),
                    button_name=N_(u'Применить'),
                    multiple=True, doc=document,
                    filterfunc=panel.api.supported)
                if not views:
                    panel.status_label.Text = tr(u'Виды не выбраны.')
                    return
                changed = skipped = failed = 0
                for view in views:
                    try:
                        groups, _, _, _ = panel.api.snapshot(document, view, settings)
                        c, s = panel.api.apply_visibility_map(
                            document, view, presets.plan_changes(groups, saved_map))
                        changed += c
                        skipped += s
                    except Exception:
                        failed += 1
                panel.refresh(uiapp)
                panel.status_label.Text += u'\n' + tr(
                    u'Видимость применена к {0} видам. Изменено элементов: {1}. '
                    u'Пропущено: {2}. Не удалось: {3}.').format(
                    len(views), changed, skipped, failed)
            else:
                if action == 'settings':
                    panel.edit_settings()
                elif action == 'manage':
                    if uidoc is None or uidoc.Document != document:
                        panel.refresh(uiapp)
                        panel.status_label.Text = tr(u'Модель изменилась. Повторите действие.')
                        return
                    panel.api.manage(document)
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

    def __init__(self, uiapp, definition=None):
        self.definition = definition or DEFAULT_FILTER
        self.api = self.definition.api
        self.cfg = self.definition.cfg
        self.mask_keys = self.definition.mask_keys
        self.uiapp = uiapp
        self.page = XamlReader.Parse(xaml_i18n.load(
            os.path.join(os.path.dirname(__file__), 'datum_filter.xaml')))
        for name in ('view_label', 'refresh_button', 'settings_button', 'search_box',
                     'mask_label', 'status_label', 'groups_panel',
                     'presets_combo', 'preset_save_button',
                     'preset_save_as_button', 'preset_delete_button',
                     'apply_views_button', 'manage_button'):
            setattr(self, name, self.page.FindName(name))
        self.groups = []
        self.document = None
        self.view_id = None
        self.pending = None
        self.dirty = True
        self.handler = Handler(self)
        self.event = ExternalEvent.Create(self.handler)
        self.doc_key = u''
        self.presets = []
        self.masks = None          # None — masks from settings; tuple — preset masks
        self.selected_preset = None
        self._loading_presets = False
        self._anchor = None        # якорь диапазона для Shift+клик
        self._selected = set()     # индексы групп, выделенных Ctrl+кликом
        self._checks = {}          # индекс группы -> CheckBox
        self._visible = []         # отображаемые (индекс, группа) по порядку
        self.refresh_button.Click += self.on_refresh
        self.settings_button.Click += self.on_settings
        self.apply_views_button.Click += self.on_apply_views
        self.manage_button.Click += self.on_manage
        self.manage_button.Visibility = Visibility.Visible if self.definition.manage else Visibility.Collapsed
        self.search_box.TextChanged += self.on_search
        self.presets_combo.SelectionChanged += self.on_preset_selected
        self.preset_save_button.Click += self.on_preset_save
        self.preset_save_as_button.Click += self.on_preset_save_as
        self.preset_delete_button.Click += self.on_preset_delete
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
        new_key = presets.document_key(doc.Title, doc.PathName)
        if new_key != self.doc_key:
            self.masks = None
            self.selected_preset = None
        if (doc, view.Id) != getattr(self, '_selection_context', None):
            self._selected = set()
            self._anchor = None
        self._selection_context = (doc, view.Id)
        self.view_label.Text = u'{0} — {1}'.format(doc.Title, view.Name)
        self.doc_key = presets.document_key(doc.Title, doc.PathName)
        self.presets = presets.list_presets(self._read_presets(), self.doc_key, self.mask_keys)
        self._render_presets()
        if doc.IsFamilyDocument or not self.api.supported(view):
            self.status_label.Text = tr(u'Выберите план, разрез, фасад или 3D-вид проекта.')
            return
        settings = dict(self.cfg.SETTINGS.get_settings_silent())
        if self.masks:
            settings.update(zip(self.mask_keys, self.masks))
        self.groups, unmatched, mask, is_3d = self.api.snapshot(doc, view, settings)
        self.document, self.view_id = doc, view.Id
        self.mask_label.Text = (mask if self.definition.snapshot_caption else
            tr(u'{0}. Маска: {1}').format(tr(u'Уровни') if is_3d else tr(u'Оси'), mask))
        if self.selected_preset:
            self.mask_label.Text += u' ' + tr(u'Группа: {0}').format(self.selected_preset)
        self.status_label.Text = tr(u'Групп: {0}. Вне маски: {1}.').format(len(self.groups), unmatched)
        self.status_label.Text += u'\n' + tr(self.definition.hint or u'Галочки управляют скрытием элементов. Категория, шаблон и границы вида могут ограничивать видимость. Только элементы текущей модели.')
        self.render_groups()

    def render_groups(self):
        self.groups_panel.Children.Clear()
        self._checks = {}
        self._visible = []
        section = None
        for index, group in enumerate(self.groups):
            if not text_search.matches(group['name'] + u' ' + u' '.join(
                    item['name'] for item in group['items']), self.search_box.Text):
                continue
            if group.get('section') and group['section'] != section:
                section = group['section']
                heading = TextBlock()
                heading.Text = tr(section)
                heading.Margin = Thickness(0, 10, 0, 4)
                self.groups_panel.Children.Add(heading)
            check = CheckBox()
            group_label = TextBlock()
            group_label.Text = u'{0} ({1})'.format(group['name'], len(group['items']))
            check.Content = group_label
            check.ToolTip = u'\n'.join(item['name'] + (u' — ' + item['reason'] if item.get('reason') else u'') for item in group['items'])
            check.Margin = Thickness(0, 5, 0, 5)
            check.IsThreeState = True
            check.IsChecked = group['checked']
            check.IsEnabled = any(item['hideable'] for item in group['items'])
            check.Tag = (index, group)
            check.Click += self.on_toggle
            self.groups_panel.Children.Add(check)
            self._checks[index] = check
            self._visible.append((index, group))
        self._highlight_selection()

    def _highlight_selection(self):
        for index, check in self._checks.items():
            check.Background = (Brushes.LightSteelBlue if index in self._selected
                                else Brushes.Transparent)

    def set_busy(self, busy):
        self.groups_panel.IsEnabled = not busy
        self.refresh_button.IsEnabled = not busy
        self.settings_button.IsEnabled = not busy
        self.apply_views_button.IsEnabled = not busy
        self.manage_button.IsEnabled = not busy
        self.search_box.IsEnabled = not busy
        self.presets_combo.IsEnabled = not busy
        self.preset_save_button.IsEnabled = not busy
        self.preset_save_as_button.IsEnabled = not busy
        self.preset_delete_button.IsEnabled = not busy

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
        # Ctrl+клик добавляет группу к выделению, Shift+клик — диапазон
        # от последней нажатой; действие применяется ко всем выделенным.
        index, group = sender.Tag
        show = group['checked'] is not True
        sender.IsChecked = show
        modifiers = Keyboard.Modifiers
        targets = core.selection_targets(
            [visible_index for visible_index, _ in self._visible],
            self._anchor, index,
            bool(modifiers & ModifierKeys.Shift))
        if modifiers & ModifierKeys.Control:
            self._selected = self._selected.union(targets)
        else:
            self._selected = targets
        if not modifiers & ModifierKeys.Shift:
            self._anchor = index
        self._highlight_selection()
        changes = [(visible_group['items'], show)
                   for visible_index, visible_group in self._visible
                   if visible_index in self._selected]
        self.request('visibility_map', changes)

    def on_refresh(self, sender, args):
        self.request('refresh')

    def on_settings(self, sender, args):
        self.request('settings')

    def on_manage(self, sender, args):
        self.request('manage')

    def on_apply_views(self, sender, args):
        if not self.groups:
            self.status_label.Text = tr(u'Сначала обновите список на поддерживаемом виде.')
            return
        grid_mask, level_mask = self._current_masks()
        saved_map = presets.visibility_map(self.groups)
        self.request('apply_views', (grid_mask, level_mask, saved_map))

    def on_search(self, sender, args):
        self.render_groups()

    # --- user presets (per model) -----------------------------------------

    def _read_presets(self):
        try:
            raw = self.cfg.SETTINGS.store.read().get(presets.PRESETS_KEY, {})
        except Exception:
            raw = {}
        return raw if isinstance(raw, dict) else {}

    def _write_presets(self, raw):
        self.cfg.SETTINGS.store.update({presets.PRESETS_KEY: raw})
        self.presets = presets.list_presets(raw, self.doc_key, self.mask_keys)
        self._render_presets()

    def _render_presets(self):
        self._loading_presets = True
        try:
            self.presets_combo.Items.Clear()
            self.presets_combo.Items.Add(tr(u'(без группы — маски из настроек)'))
            index = NONE_ITEM_INDEX
            for position, preset in enumerate(self.presets, start=1):
                self.presets_combo.Items.Add(preset['name'])
                if preset['name'] == self.selected_preset:
                    index = position
            if self.selected_preset and index == NONE_ITEM_INDEX:
                self.selected_preset = None
            self.presets_combo.SelectedIndex = index
        finally:
            self._loading_presets = False

    def _selected_preset_dict(self):
        for preset in self.presets:
            if preset['name'] == self.selected_preset:
                return preset
        return None

    def _current_masks(self):
        if self.masks:
            return self.masks
        settings = self.cfg.SETTINGS.get_settings_silent()
        return tuple(settings[key] for key in self.mask_keys)

    def on_preset_selected(self, sender, args):
        if self._loading_presets:
            return
        if self.presets_combo.SelectedIndex <= NONE_ITEM_INDEX:
            self.selected_preset = None
            if self.masks is not None:
                self.masks = None
                self.request('refresh')
            return
        name = self.presets_combo.SelectedItem
        preset = None
        for candidate in self.presets:
            if candidate['name'] == name:
                preset = candidate
                break
        if preset is None:
            return
        self.selected_preset = preset['name']
        self.request('apply_preset', preset)

    def on_preset_save(self, sender, args):
        preset = self._selected_preset_dict()
        if preset is None:
            self.status_label.Text = tr(
                u'Сначала выберите группу в списке или используйте «Сохранить как…».')
            return
        self._save_preset(preset['name'])

    def on_preset_save_as(self, sender, args):
        name = forms.ask_for_string(
            prompt=tr(u'Имя группы настроек:'), title=tr(u'Группы настроек'))
        if not name or not name.strip():
            return
        name = name.strip()
        if any(preset['name'] == name for preset in self.presets):
            if not forms.alert(tr(u'Группа «{0}» уже есть. Перезаписать?').format(name),
                               ok=False, yes=True, no=True):
                return
        self.selected_preset = name
        self._save_preset(name)

    def _save_preset(self, name):
        grid_mask, level_mask = self._current_masks()
        try:
            presets.validate_masks(grid_mask, level_mask)
        except ValueError:
            self.status_label.Text = tr(
                u'Проверьте маски: фигурные скобки должны быть парными, названия частей — непустыми и разными.')
            return
        raw = presets.save_preset(self._read_presets(), self.doc_key, name,
                                  grid_mask, level_mask,
                                  presets.visibility_map(self.groups), self.mask_keys)
        self._write_presets(raw)
        self.status_label.Text = tr(u'Группа «{0}» сохранена.').format(name)

    def on_preset_delete(self, sender, args):
        preset = self._selected_preset_dict()
        if preset is None:
            self.status_label.Text = tr(u'Сначала выберите группу в списке.')
            return
        if not forms.alert(
                tr(u'Удалить группу «{0}»? Видимость на видах не изменится.').format(preset['name']),
                ok=False, yes=True, no=True):
            return
        raw = presets.delete_preset(self._read_presets(), self.doc_key, preset['name'])
        self.selected_preset = None
        self._write_presets(raw)
        self.status_label.Text = tr(u'Группа «{0}» удалена.').format(preset['name'])

    def edit_settings(self):
        self.cfg.SETTINGS.get_settings_interactive()


def install(uiapp, definition=None):
    """Also callable on the first button click after deploying without restart."""
    definition = definition or DEFAULT_FILTER
    existing = AppDomain.CurrentDomain.GetData(definition.state_key)
    if existing is not None:
        return existing
    if DockablePane.PaneIsRegistered(pane_id(definition)):
        raise RuntimeError(tr(u'Для обновления панели перезапустите Revit.'))
    panel = Panel(uiapp, definition)
    try:
        uiapp.RegisterDockablePane(pane_id(definition), tr(definition.title), panel)
    except Exception:
        panel.event.Dispose()
        raise
    AppDomain.CurrentDomain.SetData(definition.state_key, panel)
    panel.subscribe()
    return panel


def show(uiapp, settings=False, definition=None):
    definition = definition or DEFAULT_FILTER
    panel = install(uiapp, definition)
    if settings:
        panel.edit_settings()
    panel.refresh(uiapp)
    if not DockablePane.PaneExists(pane_id(definition)):
        raise RuntimeError(tr(u'Панель зарегистрирована. Перезапустите Revit, чтобы открыть закрепляемую панель.'))
    uiapp.GetDockablePane(pane_id(definition)).Show()
