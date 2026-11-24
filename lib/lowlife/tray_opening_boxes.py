# -*- coding: utf-8 -*-
"""Standalone tray-box registry, control views, highlighting and 3D preview."""
try:
    unicode
except NameError:
    unicode = str

from System.Collections.Generic import List
from Autodesk.Revit.DB import (BoundingBoxXYZ, Color, DisplayStyle, ElementId,
    FamilyInstance, FilteredElementCollector, OverrideGraphicSettings, StorageType, XYZ,
    View, View3D, ViewFamily, ViewFamilyType, ViewPlan, Level)
from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler
from pyrevit import forms, revit
from lowlife import ui_theme
from lowlife.i18n import tr
from lowlife import opening_tasks_core as core
from lowlife import opening_tasks_storage as store
from lowlife import opening_tasks_visibility as visibility
from lowlife.opening_tasks_names import safe_name
from lowlife.opening_tasks_views import unique_name
from lowlife.route_preview import zoom_to_fit_points

ROLE = 'tray_box'
REGISTRY_VIEWS = 'tray_control_views'
REGISTRY_PREVIEWS = 'tray_box_previews'
_WINDOWS = {}


def _id_int(eid):
    try:
        return eid.Value
    except Exception:
        return eid.IntegerValue


def _metadata(inst):
    data = store.read(inst)
    return data if data and data.get('role') == ROLE and data.get('owner_uid') == inst.UniqueId else None


def records(doc):
    result = []
    for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
        if _metadata(inst):
            result.append((inst, store.read(inst)))
    return sorted(result, key=lambda pair: _id_int(pair[0].Id))


def _write_box(inst, tray, crossing, doc, settings=None):
    link = crossing.link
    linked = link.GetLinkDocument() if link is not None else None
    model = store.model_id(linked) if linked is not None else store.model_id(doc)
    data = dict(schema=core.VERSION, role=ROLE, owner_uid=inst.UniqueId,
                source_model=store.model_id(doc), source_uid=tray.UniqueId,
                source_name=safe_name(getattr(tray, 'Name', '') or 'Id ' + str(_id_int(tray.Id))),
                host_uid=crossing.host.UniqueId,
                host_link_uid=link.UniqueId if link is not None else '',
                host_model=model,
                host_name=safe_name(getattr(crossing.host, 'Name', '') or
                                   'Id ' + str(_id_int(crossing.host.Id))),
                kind=crossing.kind,
                size_params=dict(width=(settings or {}).get('box_width_param') or u'Ширина',
                                 depth=(settings or {}).get('box_depth_param') or u'Глубина',
                                 height=(settings or {}).get('box_height_param') or u'Высота'))
    store.write(inst, data)


def register_result(doc, result, settings=None):
    """Persist standalone identity without replacing VIS task metadata."""
    for tray, crossing, inst in list(result.created) + list(result.existing):
        old = store.read(inst)
        if old and old.get('role') not in (ROLE, None):
            continue
        _write_box(inst, tray, crossing, doc, settings)


def _points(instances):
    return [point for inst in instances
            for bound in [inst.get_BoundingBox(None)] if bound is not None
            for point in (bound.Min, bound.Max)]


def _crop(points, margin_ft):
    box = BoundingBoxXYZ()
    box.Min = XYZ(min(p.X for p in points) - margin_ft,
                  min(p.Y for p in points) - margin_ft,
                  min(p.Z for p in points) - margin_ft)
    box.Max = XYZ(max(p.X for p in points) + margin_ft,
                  max(p.Y for p in points) + margin_ft,
                  max(p.Z for p in points) + margin_ft)
    return box


def _size_text(inst, data):
    names = data.get('size_params') or dict(width=u'Ширина', depth=u'Глубина', height=u'Высота')
    values = []
    for role in ('width', 'depth', 'height'):
        parameter = inst.LookupParameter(names.get(role, u'')) if names.get(role) else None
        if parameter is None:
            continue
        try:
            if parameter.StorageType == StorageType.Double:
                values.append(u'{:.0f}'.format(float(parameter.AsDouble() * 304.8)))
        except Exception:
            pass
    return u' × '.join(values)


def _remember(registry, key, view):
    registry.setdefault(REGISTRY_VIEWS, {})[key] = view.UniqueId
    return view


def build_control(doc):
    pairs = records(doc)
    if not pairs:
        raise ValueError(tr(u'В модели нет боксов на пересечениях лотков.',
                            u'No standalone tray-opening boxes in the model.'))
    instances = [item[0] for item in pairs]
    registry = store.registry(doc)
    root = store.model_id(doc)
    output = []
    three_d = next((t for t in FilteredElementCollector(doc).OfClass(ViewFamilyType)
                    if t.ViewFamily == ViewFamily.ThreeDimensional), None)
    if three_d is None:
        raise ValueError(tr(u'Не найден тип 3D-вида.', u'No 3D view type.'))
    key = root + '/3d'
    saved = registry.get(REGISTRY_VIEWS, {}).get(key)
    view = doc.GetElement(saved) if saved else None
    if view is None or not isinstance(view, View3D):
        view = _remember(registry, key, View3D.CreateIsometric(doc, three_d.Id))
        view.Name = unique_name(doc, u'LowLife | Боксы на пересечениях | 3D')
    visibility.configure(doc, view, instances, cache={})
    points = _points(instances)
    if points:
        view.SetSectionBox(_crop(points, 500.0 / 304.8))
        view.IsSectionBoxActive = True
    output.append(view)
    plan_type = next((t for t in FilteredElementCollector(doc).OfClass(ViewFamilyType)
                      if t.ViewFamily == ViewFamily.FloorPlan), None)
    levels = sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda x: x.ProjectElevation)
    if plan_type is not None:
        for level in levels:
            pkey = root + '/plan/' + level.UniqueId
            saved = registry.get(REGISTRY_VIEWS, {}).get(pkey)
            plan = doc.GetElement(saved) if saved else None
            if plan is None or not isinstance(plan, ViewPlan):
                plan = _remember(registry, pkey, ViewPlan.Create(doc, plan_type.Id, level.Id))
                plan.Name = unique_name(doc, u'LowLife | Боксы на пересечениях | ' + level.Name)
            visibility.configure(doc, plan, instances, structures=True, cache={})
            output.append(plan)
    store.save_registry(doc, registry)
    return output


def _views(doc):
    prefix = store.model_id(doc) + '/'
    return [doc.GetElement(uid) for key, uid in store.registry(doc).get(REGISTRY_VIEWS, {}).items()
            if key.startswith(prefix) and doc.GetElement(uid) is not None]


def highlight(uidoc, selected):
    if not selected:
        raise ValueError(tr(u'Выберите боксы в списке.', u'Select boxes in the list.'))
    doc = uidoc.Document
    elements = [doc.GetElement(row['uid']) for row in selected]
    if any(element is None for element in elements):
        raise ValueError(tr(u'Часть боксов удалена. Обновите список.', u'Some boxes were deleted. Refresh the list.'))
    wanted = set(_id_int(element.Id) for element in elements)
    candidates = []
    for view in _views(doc):
        if not isinstance(view, View) or view.IsTemplate:
            continue
        visible = set(_id_int(eid) for eid in
                      FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType().ToElementIds())
        if wanted.issubset(visible):
            candidates.append(view)
    if not candidates:
        raise ValueError(tr(u'Создайте виды контроля перед подсветкой.', u'Create control views before highlighting.'))
    current = uidoc.ActiveView
    view = next((item for item in candidates if item.UniqueId == current.UniqueId), candidates[0])
    uidoc.ActiveView = view
    uidoc.Selection.SetElementIds(List[ElementId]([element.Id for element in elements]))
    uidoc.RefreshActiveView()
    points = [point for element in elements
              for bound in [element.get_BoundingBox(view) or element.get_BoundingBox(None)]
              if bound is not None for point in (bound.Min, bound.Max)]
    if points:
        zoom_to_fit_points(uidoc, view, points)


def _new_view(doc):
    typ = next(t for t in FilteredElementCollector(doc).OfClass(ViewFamilyType)
               if t.ViewFamily == ViewFamily.ThreeDimensional)
    return View3D.CreateIsometric(doc, typ.Id)


def focus(doc, inst):
    data = _metadata(inst)
    if not data:
        raise ValueError(tr(u'Выберите бокс, созданный этой кнопкой.',
                            u'Select a box created by this command.'))
    registry = store.registry(doc)
    previews = registry.setdefault(REGISTRY_PREVIEWS, {})
    view = doc.GetElement(previews.get(inst.UniqueId)) if previews.get(inst.UniqueId) else None
    if view is None:
        view = _new_view(doc)
        view.Name = unique_name(doc, u'LowLife | Бокс на пересечении ' + str(_id_int(inst.Id)))
        previews[inst.UniqueId] = view.UniqueId
    bounds = inst.get_BoundingBox(None)
    if bounds is None:
        raise ValueError(tr(u'У бокса нет габарита.', u'Box has no bounding geometry.'))
    crop = _crop([bounds.Min, bounds.Max], 700.0 / 304.8)
    view.SetSectionBox(crop)
    view.IsSectionBoxActive = True
    keep = [inst]
    for uid in (data.get('source_uid'), data.get('host_uid'), data.get('host_link_uid')):
        if uid:
            item = doc.GetElement(uid)
            if item is not None:
                keep.append(item)
    visibility.isolate_preview(doc, view, keep, crop)
    view.ViewTemplateId = ElementId.InvalidElementId
    view.DisplayStyle = DisplayStyle.ShadingWithEdges
    allowed = visibility.structural_categories() | set(_id_int(item.Category.Id) for item in keep if item.Category is not None)
    for category in doc.Settings.Categories:
        if view.CanCategoryBeHidden(category.Id):
            view.SetCategoryHidden(category.Id, _id_int(category.Id) not in allowed)
    blue = Color(30, 100, 240)
    view.SetElementOverrides(inst.Id, OverrideGraphicSettings().SetProjectionLineColor(blue).SetCutLineColor(blue))
    store.save_registry(doc, registry)
    return view, crop


class _WindowHandler(IExternalEventHandler):
    __namespace__ = 'LowLife.TrayOpeningBoxes.' + core.guid().replace('-', '')

    def __init__(self, window):
        self.window = window

    def GetName(self):
        return 'LowLife tray opening boxes'

    def Execute(self, uiapp):
        window = self.window
        action = window.pending
        window.pending = None
        try:
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None or uidoc.Document != window.doc:
                raise ValueError(tr(u'Вернитесь в модель, для которой открыто окно.',
                                    u'Return to the model this window belongs to.'))
            if action == 'views':
                with revit.Transaction(tr(u'Виды боксов на пересечениях',
                                          u'Intersection box control views')):
                    build_control(window.doc)
                window._load()
                forms.alert(tr(u'Виды контроля обновлены.', u'Control views updated.'))
            elif action == 'highlight':
                highlight(uidoc, window._selected())
            elif action == 'focus':
                selected = window._selected()
                if len(selected) != 1:
                    raise ValueError(tr(u'Выберите один бокс.', u'Select one box.'))
                inst = window.doc.GetElement(selected[0]['uid'])
                if inst is None:
                    raise ValueError(tr(u'Бокс удалён. Обновите список.',
                                        u'Box was deleted. Refresh the list.'))
                with revit.Transaction(tr(u'Просмотр бокса', u'Box preview')):
                    view, crop = focus(window.doc, inst)
                uidoc.ActiveView = view
                zoom_to_fit_points(uidoc, view, [crop.Min, crop.Max], min_margin_ft=0.0)
        except Exception as ex:
            message = {
                'views': tr(u'Не удалось создать виды: {}', u'Could not create views: {}'),
                'highlight': tr(u'Не удалось подсветить боксы: {}', u'Could not highlight boxes: {}'),
                'focus': tr(u'Не удалось открыть 3D: {}', u'Could not open 3D preview: {}'),
            }.get(action, u'{}')
            forms.alert(message.format(ex) if '{}' in message else unicode(ex))
        finally:
            if not window.closed:
                window.IsEnabled = True
                ui_theme.apply(window).Show()


class TrayBoxWindow(forms.WPFWindow):
    def __init__(self, doc, uidoc):
        forms.WPFWindow.__init__(self, u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Width="980" Height="560" WindowStartupLocation="CenterScreen">
          <Grid Margin="12"><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
            <TextBlock x:Name="heading" FontSize="16" FontWeight="Bold" Margin="0,0,0,8"/>
            <DataGrid x:Name="items" Grid.Row="1" SelectionMode="Extended" SelectionUnit="FullRow" IsReadOnly="True" AutoGenerateColumns="True"/>
            <WrapPanel Grid.Row="2" Margin="0,8,0,0"><Button x:Name="views" Margin="0,0,6,0" Padding="10,4"/><Button x:Name="highlight" Margin="0,0,6,0" Padding="10,4"/><Button x:Name="focus" Margin="0,0,6,0" Padding="10,4"/><Button x:Name="close" Padding="10,4"/></WrapPanel>
          </Grid></Window>''', literal_string=True)
        self.doc, self.uidoc = doc, uidoc
        self.pending = None
        self.closed = False
        self.handler = _WindowHandler(self)
        self.event = ExternalEvent.Create(self.handler)
        ui_theme.apply(self)
        self.heading.Text = tr(u'Боксы на пересечениях — список', u'Intersection boxes — list')
        self.views.Content = tr(u'Обновить виды', u'Update views')
        self.highlight.Content = tr(u'Подсветить на виде', u'Highlight in view')
        self.focus.Content = tr(u'Бокс в 3D', u'Box in 3D')
        self.close.Content = tr(u'Закрыть', u'Close')
        self._load()
        self.views.Click += lambda sender, event: self.dispatch('views')
        self.highlight.Click += lambda sender, event: self.dispatch('highlight')
        self.focus.Click += lambda sender, event: self.dispatch('focus')
        self.close.Click += lambda sender, event: self.Close()
        self.Closed += self._closed

    def _load(self):
        from System.Data import DataTable
        table = DataTable()
        self.columns = (tr(u'ID', u'ID'), tr(u'Источник', u'Source'), tr(u'Конструкция', u'Host'), tr(u'Размеры, мм', u'Sizes, mm'))
        for name in self.columns:
            table.Columns.Add(name)
        self.rows = []
        for inst, data in records(self.doc):
            self.rows.append(dict(uid=inst.UniqueId, inst=inst))
            row = table.NewRow()
            row[self.columns[0]] = str(_id_int(inst.Id))
            row[self.columns[1]] = u'{} | {}'.format(data.get('source_name', ''), data.get('source_uid', ''))
            row[self.columns[2]] = u'{} | {}'.format(data.get('host_name', ''), data.get('kind', ''))
            row[self.columns[3]] = _size_text(inst, data)
            table.Rows.Add(row)
        self.items.ItemsSource = table.DefaultView

    def _selected(self):
        result = []
        for item in self.items.SelectedItems:
            for row in self.rows:
                if str(_id_int(row['inst'].Id)) == str(item[self.columns[0]]):
                    result.append(row)
        return result

    def dispatch(self, action):
        if self.pending or self.closed:
            return False
        if action in ('highlight', 'focus') and not self._selected():
            forms.alert(tr(u'Выберите боксы в списке.', u'Select boxes in the list.'))
            return False
        if action == 'focus' and len(self._selected()) != 1:
            forms.alert(tr(u'Выберите один бокс.', u'Select one box.'))
            return False
        self.pending = action
        self.IsEnabled = False
        self.Hide()
        try:
            result = self.event.Raise()
            if unicode(result) not in ('Accepted', 'Pending'):
                self.pending = None
                self.IsEnabled = True
                ui_theme.apply(self).Show()
                return False
            return True
        except Exception:
            self.pending = None
            self.IsEnabled = True
            ui_theme.apply(self).Show()
            raise

    def _closed(self, sender, event):
        self.closed = True
        _WINDOWS.pop(store.model_id(self.doc), None)


def show(doc, uidoc):
    key = store.model_id(doc)
    existing = _WINDOWS.get(key)
    if existing is not None and not existing.closed:
        ui_theme.apply(existing).Show()
        return existing
    with revit.Transaction(tr(u'Виды боксов на пересечениях', u'Intersection box control views')):
        build_control(doc)
    window = TrayBoxWindow(doc, uidoc)
    _WINDOWS[key] = window
    ui_theme.apply(window).Show()
    return window
