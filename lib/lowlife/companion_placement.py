# -*- coding: utf-8 -*-
"""
Расстановка "компаньонов" рядом с уже стоящими объектами — общая логика
кнопки «Расстановка РМ, АМ, МДУ» (SPA.panel/PlaceCompanionDevices).

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
же значения, что перенеслись бы сейчас — если да, считается, что это уже
обработано, и пропускается. Поэтому перенос хотя бы одного параметра
нужен не только для маркировки, но и для того, чтобы повторный запуск не
наплодил дублей.

Группировка (опционально, на пару): когда рядом стоит несколько (2-4)
базовых объектов одного помещения, вместо компаньона на каждый можно
поставить ОДИН компаньон-на-группу (например, модуль на 4 входа) — см.
place_companions_for_pair(..., pair["group_enabled"]).
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

# Размер группы при группировке базовых объектов: от 2 (иначе смысла нет
# — одиночный объект и так получает свой обычный компаньон) до 4 (столько
# входов у компаньона-на-группу).
GROUP_MIN_SIZE = 2
GROUP_MAX_SIZE = 4


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


def _room_of(doc, point):
    """
    Помещение (Room) текущего документа в точке point, либо None, если
    точка не попадает ни в одно (частый случай для объектов на границе
    помещений — дверь стоит в проёме стены, а не внутри контура комнаты).
    Используется только группировкой: без определённого помещения объект
    в группу не попадает и расставляется по обычному, поштучному пути.
    """
    try:
        room = doc.GetRoomAtPoint(point)
        return room
    except:
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


def _expected_values_for_base(base_element, param_map):
    """[(приёмник, значение)] — то, что перенеслось бы с одного базового
    объекта; параметры без значения в список не попадают."""
    expected = []
    for source, target in param_map:
        value = get_param_any(base_element, source)
        if value:
            expected.append((target, value))
    return expected


def _expected_values_for_group(group_elements, param_map):
    """
    То же самое для группы: значения ВСЕХ базовых объектов группы по
    каждому источнику склеиваются через ", " (по требованию — компаньон на
    группу один, а адресов у него до 4, отдельных полей под каждый вход
    может не быть). Значения сортируются, чтобы результат не зависел от
    порядка обхода базовых объектов группы.
    """
    expected = []
    for source, target in param_map:
        values = [get_param_any(el, source) for el in group_elements]
        values = sorted(v for v in values if v)
        if values:
            expected.append((target, u", ".join(values)))
    return expected


def _matches_existing(candidates, target_point, radius_ft, expected):
    """
    Существующий кандидат из candidates рядом с target_point (в радиусе
    radius_ft), у которого значения параметров совпадают с expected — то
    есть это место уже обработано раньше. None, если такого нет.

    Если expected пуст (ни один параметр источника не заполнен),
    сравнивать не с чем — возвращаем None, иначе первая же проверка (все
    значения пустые == все значения пустые) ошибочно посчитала бы дублем
    вообще любой соседний компаньон того же типа.
    """
    if not expected:
        return None

    for cand in candidates:
        cand_point = get_point(cand)
        if cand_point is None or cand_point.DistanceTo(target_point) > radius_ft:
            continue
        if all(get_param_any(cand, target) == value for target, value in expected):
            return cand

    return None


def _cluster_groups(doc, base_elements, radius_ft):
    """
    Группирует base_elements по 2-4 объекта, взаимно близких (в пределах
    radius_ft от "затравки" группы) И стоящих в одном помещении (Room
    текущего документа в точке объекта). Объекты без определяемого
    помещения, а также те, кому не нашлось пары, уходят в ungrouped — для
    них применяется обычная поштучная расстановка.

    Если рядом оказалось больше 4 кандидатов, берутся 4 ближайших к
    затравке; оставшиеся обрабатываются в следующих итерациях как
    отдельные группы (получится несколько групп по 2-4, а не одна
    переполненная).

    Возвращает (groups, ungrouped): groups — список списков элементов (по
    2-4), ungrouped — список элементов вне групп.
    """
    items = []
    ungrouped = []

    for el in base_elements:
        point = _base_point_of(el)
        if point is None:
            ungrouped.append(el)
            continue
        room = _room_of(doc, point)
        if room is None:
            ungrouped.append(el)
            continue
        items.append({"element": el, "point": point, "room_id": room.Id})

    groups = []
    remaining = list(items)

    while remaining:
        seed = remaining.pop(0)
        candidates = [
            item for item in remaining
            if item["room_id"] == seed["room_id"]
            and seed["point"].DistanceTo(item["point"]) <= radius_ft
        ]
        candidates.sort(key=lambda item: seed["point"].DistanceTo(item["point"]))
        taken = candidates[:GROUP_MAX_SIZE - 1]

        if len(taken) + 1 >= GROUP_MIN_SIZE:
            group_items = [seed] + taken
            for item in taken:
                remaining.remove(item)
            groups.append([item["element"] for item in group_items])
        else:
            ungrouped.append(seed["element"])

    return groups, ungrouped


def _place_one_group(doc, group_elements, pair, sorted_levels, candidates, radius_ft, offsets_ft):
    """
    Ставит один компаньон на группу базовых объектов (2-4). Возвращает
    ("created", элемент), ("duplicate", None) или ("failed", None).

    Точка установки — центр группы (среднее точек базовых объектов) плюс
    смещение из настроек пары; поворот для группы не определён (у
    объектов группы он может быть разным), поэтому смещение здесь
    прикладывается прямо в мировых осях X/Y, а не в местных координатах
    одного объекта, как при поштучной расстановке.
    """
    points = [p for p in (_base_point_of(el) for el in group_elements) if p is not None]
    if not points:
        return "failed", None

    centroid = XYZ(
        sum(p.X for p in points) / len(points),
        sum(p.Y for p in points) / len(points),
        sum(p.Z for p in points) / len(points),
    )
    forward_ft, side_ft, up_ft = offsets_ft
    target_point = XYZ(centroid.X + forward_ft, centroid.Y + side_ft, centroid.Z + up_ft)

    expected = _expected_values_for_group(group_elements, pair["param_map"])

    if _matches_existing(candidates, target_point, radius_ft, expected) is not None:
        return "duplicate", None

    anchor = group_elements[0]
    host = _resolve_host(anchor)
    level = _resolve_level(doc, anchor, sorted_levels, target_point)

    new_el = create_companion_instance(doc, pair["group_companion_symbol"], target_point, host, level)
    if new_el is None:
        return "failed", None

    for target, value in expected:
        set_param_any(new_el, target, value)

    return "created", new_el


def place_companions_for_pair(doc, base_elements, pair, sorted_levels):
    """
    Обрабатывает одну настроенную пару для уже собранного списка базовых
    объектов. pair — {"companion_symbol", "param_map", "offset_forward_mm",
    "offset_side_mm", "offset_up_mm", "group_enabled", "group_companion_symbol",
    "group_radius_mm"} (см. companion_placement_settings).

    Если group_enabled и задан group_companion_symbol — сначала ищутся
    группы по 2-4 близких базовых объекта одного помещения (см.
    _cluster_groups) и на каждую ставится один компаньон-на-группу;
    объекты, не попавшие ни в одну группу, обрабатываются как раньше —
    обычным компаньоном, по одному на объект.

    Возвращает {"created": [...], "created_groups": [...], "groups_found": N,
    "skipped_duplicate": N, "skipped_duplicate_groups": N,
    "skipped_no_point": N, "failed": N, "failed_groups": N}.
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

    created_groups = []
    groups_found = 0
    skipped_duplicate_groups = 0
    failed_groups = 0

    elements_for_solo = base_elements

    if pair.get("group_enabled") and pair.get("group_companion_symbol") is not None:
        group_radius_ft = pair.get("group_radius_mm", 0.0) * MM_TO_FT
        groups, ungrouped = _cluster_groups(doc, base_elements, group_radius_ft)
        groups_found = len(groups)

        group_symbol = pair["group_companion_symbol"]
        group_candidates = _existing_companions_by_symbol(doc, group_symbol.Id)

        for group_elements in groups:
            outcome, new_el = _place_one_group(
                doc, group_elements, pair, sorted_levels,
                group_candidates, radius_ft, (forward_ft, side_ft, up_ft)
            )
            if outcome == "created":
                created_groups.append(new_el)
                group_candidates.append(new_el)
            elif outcome == "duplicate":
                skipped_duplicate_groups += 1
            else:
                failed_groups += 1

        elements_for_solo = ungrouped

    candidates = _existing_companions_by_symbol(doc, symbol.Id)

    created = []
    skipped_duplicate = 0
    skipped_no_point = 0
    failed = 0

    for base_element in elements_for_solo:
        base_point = _base_point_of(base_element)
        if base_point is None:
            skipped_no_point += 1
            continue

        rotation = _rotation_of(base_element)
        target_point = _offset_point(base_point, rotation, forward_ft, side_ft, up_ft)

        expected = _expected_values_for_base(base_element, param_map)

        if _matches_existing(candidates, target_point, radius_ft, expected) is not None:
            skipped_duplicate += 1
            continue

        host = _resolve_host(base_element)
        level = _resolve_level(doc, base_element, sorted_levels, target_point)

        new_el = create_companion_instance(doc, symbol, target_point, host, level)
        if new_el is None:
            failed += 1
            continue

        for target, value in expected:
            set_param_any(new_el, target, value)

        created.append(new_el)
        candidates.append(new_el)

    return {
        "created": created,
        "created_groups": created_groups,
        "groups_found": groups_found,
        "skipped_duplicate": skipped_duplicate,
        "skipped_duplicate_groups": skipped_duplicate_groups,
        "skipped_no_point": skipped_no_point,
        "failed": failed,
        "failed_groups": failed_groups,
    }
