# -*- coding: utf-8 -*-
"""
Расстановка оборудования СС1 (SS1.panel/SS1Easy, «СС1-Easy»). Revit-часть;
чистая логика — ss1_easy_core.py, настройки — ss1_easy_settings.py.

Сценарий (run):
  1. Удаление старого: все экземпляры выбранных типоразмеров кросса и
     кабельного подвода, стоящие на отмеченных уровнях, удаляются — кнопка
     каждый раз расставляет оборудование заново.
  2. Кроссы: шахты СС — экземпляры «Обобщённой модели» заданного семейства,
     у которых заданный параметр (экземпляра или типа) равен значению
     («СС»; у шахт других систем там «СБ», «СПЗ»…). На каждом отмеченном уровне, через который шахта проходит
     (по высоте её габарита, ss1_easy_core.shaft_spans_level), в центре
     шахты ставятся два кросса на заданных высотах от уровня, повёрнутые
     по шахте + 180°. В параметр «Помещение» пишется «Ниша СС».
  3. Кабельные подводы: в каждой загруженной связи (АР) — двери между
     целевым помещением («Прихожая») и одним из соседних («Коридор»,
     «Вестибюль»), по последней стадии связи. У двухуровневой квартиры
     (одно имя лота на разных уровнях) берётся только нижняя прихожая;
     помещения без имени лота не группируются — подвод ставится в каждое,
     с предупреждением. Подвод ставится в точку двери на уровне модели,
     совпадающем по отметке с уровнем двери (с учётом сдвига связи по Z),
     если этот уровень отмечен; в «Помещение» пишется имя лота.

Высота: экземпляр создаётся NewFamilyInstance(точка, тип, уровень) с
Z точки = смещению от уровня (отметка уровня не прибавляется) — так
работало в исходном скрипте пользователя на его семействах.
"""

import math

from Autodesk.Revit.DB import (
    XYZ, Line, FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    RevitLinkInstance, FamilyInstance, Family, LocationPoint, LocationCurve,
    ElementTransformUtils, ElementId, Level, StorageType
)
from Autodesk.Revit.DB.Structure import StructuralType

from lowlife import ss1_easy_core as core
from lowlife.scs import safe_element_name

MM_TO_FT = 1.0 / 304.8
FT_TO_MM = 304.8

# Кроссы разворачиваются лицом от шахты.
MIRROR_ROTATION = math.pi


def mm_to_ft(value_mm):
    return float(value_mm) * MM_TO_FT


# ------------------------------------------------------------
# Типоразмеры, параметры
# ------------------------------------------------------------

def find_symbol(doc, family_name, type_name):
    """FamilySymbol по имени семейства и типа (без учёта регистра) или None."""
    want_family = core.normalize(family_name)
    want_type = core.normalize(type_name)
    for family in FilteredElementCollector(doc).OfClass(Family):
        if core.normalize(safe_element_name(family)) != want_family:
            continue
        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            if symbol is not None and core.normalize(safe_element_name(symbol)) == want_type:
                return symbol
    return None


def activate_symbol(doc, symbol):
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
    except Exception:
        pass


def _param_text(param):
    """Значение параметра текстом: строка как есть, остальное — как в Revit."""
    value = None
    try:
        if param.StorageType == StorageType.String:
            value = param.AsString()
        else:
            value = param.AsValueString()
    except Exception:
        pass
    return value


def _instance_and_type(element):
    result = [element]
    try:
        symbol = element.Symbol
        if symbol is not None:
            result.append(symbol)
    except Exception:
        pass
    return result


def _param_values(element, param_name):
    values = []
    if not param_name:
        return values
    for obj in _instance_and_type(element):
        try:
            param = obj.LookupParameter(param_name)
        except Exception:
            param = None
        if param is not None and param.HasValue:
            values.append(_param_text(param))
    return values


def set_text_param(element, param_name, value):
    """Пишет строку в параметр экземпляра. True — записано."""
    if not param_name:
        return False
    try:
        param = element.LookupParameter(param_name)
        if param is None or param.IsReadOnly or param.StorageType != StorageType.String:
            return False
        param.Set(u"" if value is None else unicode(value))  # noqa: F821
        return True
    except Exception:
        return False


def _family_name(element):
    try:
        symbol = element.Symbol
        if symbol is not None and symbol.Family is not None:
            return safe_element_name(symbol.Family)
    except Exception:
        pass
    return None


def _instance_level_id(element):
    try:
        level_id = element.LevelId
        if level_id is not None and level_id != ElementId.InvalidElementId:
            return level_id
    except Exception:
        pass
    for bip in (BuiltInParameter.FAMILY_LEVEL_PARAM, BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM):
        try:
            param = element.get_Parameter(bip)
            if param is not None:
                level_id = param.AsElementId()
                if level_id is not None and level_id != ElementId.InvalidElementId:
                    return level_id
        except Exception:
            pass
    return None


# ------------------------------------------------------------
# Уровни и создание экземпляров
# ------------------------------------------------------------

def get_levels(doc):
    levels = list(FilteredElementCollector(doc).OfClass(Level).WhereElementIsNotElementType())
    levels.sort(key=lambda lv: lv.ProjectElevation)
    return levels


def set_instance_level(instance, level):
    """Назначает экземпляру уровень через параметр «Уровень». True — назначен."""
    for bip in (BuiltInParameter.FAMILY_LEVEL_PARAM, BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM):
        try:
            param = instance.get_Parameter(bip)
            if param is not None and not param.IsReadOnly:
                param.Set(level.Id)
                return True
        except Exception:
            pass
    return False


def create_on_level(doc, x, y, offset_mm, symbol, level):
    """
    Экземпляр на уровне со смещением offset_mm. В Z точки передаётся только
    смещение (отметка уровня не прибавляется) — как в исходном скрипте.
    """
    point = XYZ(x, y, mm_to_ft(offset_mm))
    try:
        instance = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
        doc.Regenerate()
        set_instance_level(instance, level)
        return instance
    except Exception:
        pass

    instance = doc.Create.NewFamilyInstance(point, symbol, StructuralType.NonStructural)
    doc.Regenerate()
    if not set_instance_level(instance, level):
        raise Exception(u"не удалось назначить уровень экземпляру Id {}".format(
            instance.Id.IntegerValue))
    doc.Regenerate()
    return instance


def rotate_instance(doc, instance, angle):
    """Поворот вокруг вертикальной оси через точку вставки экземпляра."""
    if abs(angle) < 1e-9:
        return
    location = instance.Location
    if not isinstance(location, LocationPoint):
        return
    point = location.Point
    axis = Line.CreateBound(point, XYZ(point.X, point.Y, point.Z + 10.0))
    ElementTransformUtils.RotateElement(doc, instance.Id, axis, angle)


# ------------------------------------------------------------
# Удаление старого
# ------------------------------------------------------------

def delete_old(doc, symbols, level_ids):
    """
    Удаляет все экземпляры типоразмеров symbols, стоящие на уровнях
    level_ids (множество IntegerValue). Возвращает {symbol_id: число}.
    """
    from System.Collections.Generic import List

    type_ids = set(s.Id.IntegerValue for s in symbols)
    counts = dict((s.Id.IntegerValue, 0) for s in symbols)
    to_delete = List[ElementId]()
    for instance in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            type_id = instance.GetTypeId().IntegerValue
        except Exception:
            continue
        if type_id not in type_ids:
            continue
        level_id = _instance_level_id(instance)
        if level_id is None or level_id.IntegerValue not in level_ids:
            continue
        to_delete.Add(instance.Id)
        counts[type_id] += 1
    if to_delete.Count:
        doc.Delete(to_delete)
    return counts


# ------------------------------------------------------------
# Шахты и кроссы
# ------------------------------------------------------------

def is_ss_shaft(element, settings):
    """
    Шахта СС: параметр shaft_param (экземпляра или типа) равен shaft_value
    («СС»; у шахт других систем там «СБ», «СПЗ»…), см. core.value_matches.
    """
    param_name = (settings.get("shaft_param") or u"").strip()
    wanted = settings.get("shaft_value") or u""
    for value in _param_values(element, param_name):
        if core.value_matches(value, wanted):
            return True
    return False


def facing_angle(element):
    for attr in ("FacingOrientation", "HandOrientation"):
        try:
            vector = getattr(element, attr)
            if vector is not None and (abs(vector.X) > 1e-9 or abs(vector.Y) > 1e-9):
                return math.atan2(vector.Y, vector.X)
        except Exception:
            pass
    return 0.0


def collect_ss_shafts(doc, settings):
    """[(шахта, центр XYZ, низ Z, верх Z)] шахт СС текущей модели."""
    family_name = core.normalize(settings.get("shaft_family_name"))
    result = []
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_GenericModel)
                 .WhereElementIsNotElementType())
    for element in collector:
        if core.normalize(_family_name(element)) != family_name:
            continue
        if not is_ss_shaft(element, settings):
            continue
        bbox = element.get_BoundingBox(None)
        if bbox is None:
            continue
        center = XYZ((bbox.Min.X + bbox.Max.X) / 2.0,
                     (bbox.Min.Y + bbox.Max.Y) / 2.0,
                     (bbox.Min.Z + bbox.Max.Z) / 2.0)
        result.append((element, center, bbox.Min.Z, bbox.Max.Z))
    return result


class Result(object):
    def __init__(self):
        self.shafts = 0
        self.crosses = 0
        self.shaft_levels_skipped = 0
        self.doors = 0
        self.feeds = 0
        self.deleted_crosses = 0
        self.deleted_feeds = 0
        self.diagnostics = []


def place_crosses(doc, shafts, levels, settings, symbol, result):
    tol = mm_to_ft(settings.get("level_tolerance_mm") or 0.0)
    heights = [settings.get("cross_height_1_mm"), settings.get("cross_height_2_mm")]
    room_param = (settings.get("room_target_param") or u"").strip()
    niche_text = settings.get("niche_text") or u""
    seen = set()

    for level in levels:
        level_z = level.ProjectElevation
        for shaft, center, min_z, max_z in shafts:
            if not core.shaft_spans_level(min_z, max_z, level_z, tol):
                result.shaft_levels_skipped += 1
                continue
            key = core.dedupe_key(center.X, center.Y, level.Id.IntegerValue)
            if key in seen:
                result.diagnostics.append(
                    u"Шахта Id {}: на уровне «{}» в той же точке уже есть шахта СС — "
                    u"кроссы не дублируются.".format(shaft.Id.IntegerValue, level.Name))
                continue
            seen.add(key)

            angle = facing_angle(shaft) + MIRROR_ROTATION
            for number, height in enumerate(heights, 1):
                try:
                    instance = create_on_level(doc, center.X, center.Y, height, symbol, level)
                    rotate_instance(doc, instance, angle)
                    if room_param and not set_text_param(instance, room_param, niche_text):
                        result.diagnostics.append(
                            u"Кросс Id {}: не удалось записать «{}».".format(
                                instance.Id.IntegerValue, room_param))
                    result.crosses += 1
                except Exception as ex:
                    result.diagnostics.append(
                        u"Шахта Id {}, уровень «{}»: ошибка установки кросса №{}: {}".format(
                            shaft.Id.IntegerValue, level.Name, number, ex))


# ------------------------------------------------------------
# Двери связей и кабельные подводы
# ------------------------------------------------------------

def _room_name(room):
    if room is None:
        return u""
    try:
        param = room.get_Parameter(BuiltInParameter.ROOM_NAME)
        if param is not None and param.AsString():
            return param.AsString().strip()
    except Exception:
        pass
    try:
        return (safe_element_name(room) or u"").strip()
    except Exception:
        return u""


def _room_text_param(room, param_name):
    try:
        param = room.LookupParameter(param_name)
        if param is not None:
            value = param.AsString()
            if value is None:
                value = param.AsValueString()
            if value:
                return value.strip()
    except Exception:
        pass
    return u""


def _room_elevation(link_doc, room):
    try:
        level = link_doc.GetElement(room.LevelId)
        if isinstance(level, Level):
            return level.ProjectElevation
    except Exception:
        pass
    try:
        location = room.Location
        if isinstance(location, LocationPoint):
            return location.Point.Z
    except Exception:
        pass
    return None


def _door_rooms(door, phase):
    try:
        return door.get_FromRoom(phase), door.get_ToRoom(phase)
    except Exception:
        return None, None


def _door_point(door):
    try:
        location = door.Location
        if isinstance(location, LocationPoint):
            return location.Point
        if isinstance(location, LocationCurve):
            return location.Curve.Evaluate(0.5, True)
    except Exception:
        pass
    try:
        bbox = door.get_BoundingBox(None)
        if bbox is not None:
            return bbox.Min.Add(bbox.Max).Divide(2.0)
    except Exception:
        pass
    return None


def _door_level_z(door, link_doc, transform):
    """Отметка уровня двери в координатах модели (сдвиг связи по Z учтён)."""
    level_id = None
    try:
        param = door.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if param is not None:
            level_id = param.AsElementId()
    except Exception:
        pass
    if level_id is None or level_id == ElementId.InvalidElementId:
        try:
            level_id = door.LevelId
        except Exception:
            level_id = None
    if level_id is not None and level_id != ElementId.InvalidElementId:
        level = link_doc.GetElement(level_id)
        if isinstance(level, Level):
            return transform.OfPoint(XYZ(0, 0, level.ProjectElevation)).Z
    point = _door_point(door)
    if point is not None:
        return transform.OfPoint(point).Z
    return None


def _link_label(link_instance):
    try:
        return safe_element_name(link_instance) or u"связь"
    except Exception:
        return u"связь"


def place_feeds(doc, levels, settings, symbol, offset_mm, result):
    target_name = settings.get("target_room_name") or u""
    neighbors = core.split_names(settings.get("neighbor_room_names"))
    lot_param = (settings.get("lot_param_name") or u"").strip()
    room_param = (settings.get("room_target_param") or u"").strip()
    tol = mm_to_ft(settings.get("level_tolerance_mm") or 0.0)
    level_marks = [(level, level.ProjectElevation) for level in levels]

    links = list(FilteredElementCollector(doc).OfClass(RevitLinkInstance))
    if not links:
        result.diagnostics.append(u"В проекте нет ни одной связи — кабельные подводы не ставятся.")
        return

    for link_instance in links:
        try:
            link_doc = link_instance.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is None:
            continue
        label = _link_label(link_instance)
        transform = link_instance.GetTotalTransform()

        phases = link_doc.Phases
        if phases is None or phases.Size == 0:
            continue
        phase = phases.get_Item(phases.Size - 1)

        # Целевые помещения связи: у дуплекса — только нижнее.
        rooms = []
        room_lots = {}
        room_collector = (FilteredElementCollector(link_doc)
                          .OfCategory(BuiltInCategory.OST_Rooms)
                          .WhereElementIsNotElementType())
        for room in room_collector:
            if core.normalize(_room_name(room)) != core.normalize(target_name):
                continue
            lot = _room_text_param(room, lot_param)
            room_lots[room.Id.IntegerValue] = lot
            rooms.append((room.Id.IntegerValue, lot, _room_elevation(link_doc, room)))
        keep, _ = core.lowest_room_per_lot(rooms)
        warned_rooms = set()

        door_collector = (FilteredElementCollector(link_doc)
                          .OfCategory(BuiltInCategory.OST_Doors)
                          .WhereElementIsNotElementType())
        for door in door_collector:
            try:
                from_room, to_room = _door_rooms(door, phase)
                side = core.door_target_side(
                    _room_name(from_room), _room_name(to_room), target_name, neighbors)
                if side is None:
                    continue
                room = from_room if side == "from" else to_room
                room_id = room.Id.IntegerValue
                if room_id not in keep:
                    continue

                level_z = _door_level_z(door, link_doc, transform)
                level = core.match_level(level_z, level_marks, tol) if level_z is not None else None
                if level is None:
                    continue

                result.doors += 1
                point = _door_point(door)
                if point is None:
                    result.diagnostics.append(
                        u"{}: дверь Id {} — не удалось определить точку.".format(
                            label, door.Id.IntegerValue))
                    continue
                host_point = transform.OfPoint(point)

                lot = room_lots.get(room_id) or u""
                instance = create_on_level(doc, host_point.X, host_point.Y, offset_mm, symbol, level)
                result.feeds += 1
                if not lot:
                    if room_id not in warned_rooms:
                        warned_rooms.add(room_id)
                        result.diagnostics.append(
                            u"ВНИМАНИЕ. {}: у помещения «{}» Id {} не заполнено «{}» — "
                            u"подвод Id {} поставлен без имени лота.".format(
                                label, target_name, room_id, lot_param,
                                instance.Id.IntegerValue))
                elif room_param and not set_text_param(instance, room_param, lot):
                    result.diagnostics.append(
                        u"Подвод Id {}: не удалось записать «{}».".format(
                            instance.Id.IntegerValue, room_param))
            except Exception as ex:
                result.diagnostics.append(u"{}: дверь Id {} — ошибка: {}".format(
                    label, door.Id.IntegerValue, ex))


# ------------------------------------------------------------
# Целиком
# ------------------------------------------------------------

def run(doc, levels, offset_mm, settings, cross_symbol, feed_symbol):
    """Всё внутри уже открытой транзакции. Возвращает Result."""
    result = Result()
    activate_symbol(doc, cross_symbol)
    activate_symbol(doc, feed_symbol)

    level_ids = set(level.Id.IntegerValue for level in levels)
    deleted = delete_old(doc, [cross_symbol, feed_symbol], level_ids)
    result.deleted_crosses = deleted.get(cross_symbol.Id.IntegerValue, 0)
    if feed_symbol.Id != cross_symbol.Id:
        result.deleted_feeds = deleted.get(feed_symbol.Id.IntegerValue, 0)

    shafts = collect_ss_shafts(doc, settings)
    result.shafts = len(shafts)
    place_crosses(doc, shafts, levels, settings, cross_symbol, result)
    place_feeds(doc, levels, settings, feed_symbol, offset_mm, result)
    return result


# ------------------------------------------------------------
# Окно запуска: уровни + смещение подвода
# ------------------------------------------------------------

def ask_levels_and_offset(doc, default_offset_mm):
    """
    Окно выбора уровней и смещения кабельного подвода. Возвращает
    (уровни, смещение_мм) или (None, None) при отмене.
    """
    import clr
    clr.AddReference("PresentationFramework")
    clr.AddReference("PresentationCore")
    clr.AddReference("WindowsBase")
    from System.Windows import (
        Window, Thickness, WindowStartupLocation, ResizeMode, HorizontalAlignment
    )
    from System.Windows.Controls import (
        StackPanel, TextBlock, TextBox, Button, ScrollViewer, CheckBox, Orientation,
        ScrollBarVisibility
    )
    from pyrevit import forms

    levels = get_levels(doc)
    if not levels:
        forms.alert(u"В проекте нет ни одного уровня.", title=u"СС1-Easy")
        return None, None

    window = Window()
    window.Title = u"СС1-Easy — кроссы и кабельные подводы"
    window.Width = 440
    window.Height = 590
    window.MinWidth = 400
    window.MinHeight = 450
    window.ResizeMode = ResizeMode.CanResize
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen

    root = StackPanel()
    root.Margin = Thickness(14)
    window.Content = root

    header = TextBlock()
    header.Text = u"Уровни для установки оборудования:"
    header.Margin = Thickness(0, 0, 0, 8)
    root.Children.Add(header)

    scroll = ScrollViewer()
    scroll.Height = 365
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    level_panel = StackPanel()
    scroll.Content = level_panel
    root.Children.Add(scroll)

    checks = []
    for level in levels:
        try:
            label = u"{}   ({:.0f} мм)".format(level.Name, float(level.Elevation) * FT_TO_MM)
        except Exception:
            label = level.Name
        cb = CheckBox()
        cb.Content = label
        cb.IsChecked = True
        cb.Tag = level
        cb.Margin = Thickness(2, 3, 2, 3)
        level_panel.Children.Add(cb)
        checks.append(cb)

    offset_label = TextBlock()
    offset_label.Text = u"Смещение кабельного подвода от уровня, мм:"
    offset_label.Margin = Thickness(0, 12, 0, 4)
    root.Children.Add(offset_label)

    offset_box = TextBox()
    offset_box.Text = u"{:.0f}".format(float(default_offset_mm))
    offset_box.Margin = Thickness(0, 0, 0, 12)
    root.Children.Add(offset_box)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    root.Children.Add(buttons)

    ok_button = Button()
    ok_button.Content = u"Запустить"
    ok_button.Width = 100
    ok_button.Margin = Thickness(0, 0, 8, 0)
    buttons.Children.Add(ok_button)

    cancel_button = Button()
    cancel_button.Content = u"Отмена"
    cancel_button.Width = 90
    buttons.Children.Add(cancel_button)

    state = {"result": None}

    def on_ok(sender, args):
        checked = [cb.Tag for cb in checks if cb.IsChecked]
        if not checked:
            forms.alert(u"Отметьте хотя бы один уровень.", title=u"СС1-Easy")
            return
        try:
            value = float(offset_box.Text.strip().replace(u",", u"."))
            if value < 0:
                raise ValueError()
        except Exception:
            forms.alert(u"Введите неотрицательное число для смещения подвода.", title=u"СС1-Easy")
            return
        state["result"] = (checked, value)
        window.Close()

    def on_cancel(sender, args):
        window.Close()

    ok_button.Click += on_ok
    cancel_button.Click += on_cancel
    window.ShowDialog()

    if state["result"] is None:
        return None, None
    return state["result"]
