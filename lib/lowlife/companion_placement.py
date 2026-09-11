# -*- coding: utf-8 -*-
"""
Расстановка "компаньонов" рядом с уже стоящими объектами — общая логика
кнопки «Расстановка РМ, АМ, МДУ» (SPS.panel/PlaceCompanionDevices).

Задача: в проекте уже стоят одни объекты (например, двери эвакуационных
выходов, клапаны ДУ), и рядом с каждым нужно поставить своё устройство —
ручной пожарный извещатель (РМ), адресный модуль (АМ), модуль
дистанционного управления (МДУ) и т.п. — со смещением на фиксированное
расстояние, и перенести на него значения нужных параметров с базового
объекта (адрес, обозначение и т.п.; можно несколько параметров сразу).

Что ставить рядом с чем, смещение и список переносимых параметров —
настраиваются отдельно для каждой пары через
lowlife.companion_placement_settings (Shift+клик по кнопке). Здесь —
только сама расстановка по уже готовому списку пар.

Защита от повторной расстановки: перед созданием компаньона проверяется,
нет ли уже рядом (в пределах разумного радиуса от точки установки)
экземпляра компаньона, у которого переносимые параметры УЖЕ содержат те
же значения, что перенеслись бы с этого базового объекта сейчас — если
да, объект считается уже обработанным и пропускается. Поэтому перенос
хотя бы одного параметра нужен не только для маркировки, но и для того,
чтобы повторный запуск не наплодил дублей.
"""

import math

from Autodesk.Revit.DB import XYZ, LocationPoint, FilteredElementCollector
from Autodesk.Revit.DB.Structure import StructuralType

from lowlife.geometry import get_point, get_element_level, find_level_for_elevation
from lowlife.params import get_param_any, set_param_any

MM_TO_FT = 1.0 / 304.8

# Радиус поиска уже стоящего компаньона при проверке на дубль — берём с
# запасом относительно самого смещения (компаньон мог быть подвинут
# вручную после расстановки), но не безграничный: иначе одноимённый
# компаньон у похожего базового объекта в другом конце здания мог бы
# ложно засчитаться как "уже стоящий здесь".
DEDUPE_RADIUS_MARGIN_FT = 1.0
DEDUPE_RADIUS_MIN_FT = 1000.0 * MM_TO_FT


def _rotation_of(el):
    """Угол поворота экземпляра вокруг вертикальной оси (радианы), 0 — если недоступен."""
    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            return loc.Rotation
    except:
        pass
    return 0.0


def _base_point_of(el):
    """Точка базового объекта: LocationPoint, иначе центр bounding box."""
    point = get_point(el)
    if point is not None:
        return point
    try:
        bbox = el.get_BoundingBox(None)
        if bbox is not None:
            return (bbox.Min + bbox.Max) * 0.5
    except:
        pass
    return None


def _offset_point(base_point, rotation, forward_ft, side_ft, up_ft):
    """
    Точка установки компаньона в мировых координатах. forward/side заданы
    в местной системе координат базового объекта (по направлению его
    поворота на плане), up — по вертикали. Так смещение "вперёд на 300 мм"
    остаётся "вперёд" независимо от того, как базовый объект повёрнут на
    плане.
    """
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    dx = forward_ft * cos_r - side_ft * sin_r
    dy = forward_ft * sin_r + side_ft * cos_r
    return XYZ(base_point.X + dx, base_point.Y + dy, base_point.Z + up_ft)


def _resolve_host(base_element):
    """Хост базового объекта (например, стена), если он на чём-то размещён."""
    try:
        return base_element.Host
    except:
        return None


def _resolve_level(doc, base_element, sorted_levels, point):
    level = get_element_level(doc, base_element)
    if level is not None:
        return level
    if point is not None and sorted_levels:
        return find_level_for_elevation(point.Z, sorted_levels)
    return None


def create_companion_instance(doc, symbol, point, host, level):
    """
    Создаёт экземпляр компаньона в точке point — первое, что примет Revit
    для этого семейства: сначала хостовое размещение с уровнем (если у
    базового объекта есть хост, например стена), затем просто хостовое,
    затем по уровню без хоста, и в крайнем случае вовсе без привязки.
    Возвращает созданный элемент либо None, если ни один вариант не
    подошёл (например, семейство требует размещения на грани, а не в
    точке/на хосте — такие компаньоны эта кнопка пока не умеет).
    """
    if not symbol.IsActive:
        symbol.Activate()

    if host is not None and level is not None:
        try:
            return doc.Create.NewFamilyInstance(point, symbol, host, level, StructuralType.NonStructural)
        except:
            pass

    if host is not None:
        try:
            return doc.Create.NewFamilyInstance(point, symbol, host, StructuralType.NonStructural)
        except:
            pass

    if level is not None:
        try:
            return doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
        except:
            pass

    try:
        return doc.Create.NewFamilyInstance(point, symbol, StructuralType.NonStructural)
    except:
        return None


def collect_elements_by_type_ids(doc, view, type_ids):
    """Экземпляры на view, чей тип входит в type_ids (набор ElementId)."""
    result = []
    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    for el in collector:
        try:
            if el.GetTypeId() in type_ids:
                result.append(el)
        except:
            continue
    return result


def _existing_companions_by_symbol(doc, symbol_id):
    """Все экземпляры документа выбранного типа — кандидаты на "уже стоит"."""
    result = []
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            if el.GetTypeId() == symbol_id:
                result.append(el)
        except:
            continue
    return result


def _already_placed(candidates, target_point, radius_ft, param_map, base_element):
    """
    True, если среди candidates рядом с target_point уже есть компаньон, у
    которого значения параметров из param_map совпадают с тем, что
    перенеслось бы с base_element сейчас — то есть этот базовый объект уже
    был обработан раньше.

    Если ни один параметр базового объекта из param_map не заполнен,
    сравнивать не с чем: считаем, что компаньона ещё нет, иначе первая же
    проверка (все значения пустые == все значения пустые) ошибочно
    посчитала бы дублем вообще любой соседний компаньон того же типа.
    """
    expected = []
    for source, target in param_map:
        value = get_param_any(base_element, source)
        if value:
            expected.append((target, value))

    if not expected:
        return False

    for cand in candidates:
        cand_point = get_point(cand)
        if cand_point is None or cand_point.DistanceTo(target_point) > radius_ft:
            continue
        if all(get_param_any(cand, target) == value for target, value in expected):
            return True

    return False


def place_companions_for_pair(doc, base_elements, pair, sorted_levels):
    """
    Обрабатывает одну настроенную пару для уже собранного списка базовых
    объектов. pair — {"companion_symbol", "param_map", "offset_forward_mm",
    "offset_side_mm", "offset_up_mm"} (см. companion_placement_settings).

    Возвращает {"created": [элементы], "skipped_duplicate": N,
    "skipped_no_point": N, "failed": N}.
    """
    symbol = pair["companion_symbol"]
    param_map = pair["param_map"]
    forward_ft = pair["offset_forward_mm"] * MM_TO_FT
    side_ft = pair["offset_side_mm"] * MM_TO_FT
    up_ft = pair["offset_up_mm"] * MM_TO_FT

    radius_ft = max(
        abs(forward_ft) + abs(side_ft) + abs(up_ft) + DEDUPE_RADIUS_MARGIN_FT,
        DEDUPE_RADIUS_MIN_FT
    )

    candidates = _existing_companions_by_symbol(doc, symbol.Id)

    created = []
    skipped_duplicate = 0
    skipped_no_point = 0
    failed = 0

    for base_element in base_elements:
        base_point = _base_point_of(base_element)
        if base_point is None:
            skipped_no_point += 1
            continue

        rotation = _rotation_of(base_element)
        target_point = _offset_point(base_point, rotation, forward_ft, side_ft, up_ft)

        if _already_placed(candidates, target_point, radius_ft, param_map, base_element):
            skipped_duplicate += 1
            continue

        host = _resolve_host(base_element)
        level = _resolve_level(doc, base_element, sorted_levels, target_point)

        new_el = create_companion_instance(doc, symbol, target_point, host, level)
        if new_el is None:
            failed += 1
            continue

        for source, target in param_map:
            value = get_param_any(base_element, source)
            if value is not None:
                set_param_any(new_el, target, value)

        created.append(new_el)
        candidates.append(new_el)

    return {
        "created": created,
        "skipped_duplicate": skipped_duplicate,
        "skipped_no_point": skipped_no_point,
        "failed": failed,
    }
