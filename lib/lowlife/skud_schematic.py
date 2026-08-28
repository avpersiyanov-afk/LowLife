# -*- coding: utf-8 -*-
"""
Логика кнопки BuildSkudSchematic ("Структурная схема СКУД").

Основной путь — по типовым группам деталей: узел-контроллер ставится один
раз на контроллер, а на каждую его точку прохода подбирается группа, чей
состав устройств (по категориям, skud.category_by_type_id) совпадает с
составом точки прохода. Группа вставляется, разгруппировывается, её
схемным элементам проставляются адрес/марка по сопоставленным реальным
устройствам.

Резервный путь (no-match: для состава точки прохода нет подходящей группы)
— старая раскладка: каждое устройство отдельным схемным семейством
категории в точке, вычисленной от точки контроллера (device_layout_point).
"""

from collections import OrderedDict

from lowlife.scs_circuits import clean_text_value

# params.py тянет Autodesk.Revit.DB — вне Revit (юнит-тесты) недоступен.
# Пусть модуль остаётся импортируемым для чистых функций (см. tests/README).
try:
    from lowlife.params import get_string_param as _get_string_param
except Exception:  # pragma: no cover - только вне Revit
    _get_string_param = None


def _param_value(el, name):
    """Строковое значение параметра. В Revit — через params.get_string_param;
    вне Revit (тесты) — из el.params[name] у fake-элемента."""
    if _get_string_param is not None:
        return _get_string_param(el, name)
    try:
        return el.params.get(name)
    except Exception:
        return None


def category_of_from_type_map(type_id_to_category):
    """
    Возвращает функцию category_of(el) -> имя категории или None по плоской
    карте {int(id типа): имя категории}. Используется двумя способами:
      - для реальных устройств карта строится из
        skud_settings.get_schematic_category_device_type_ids (реальные типы);
      - для схемных элементов внутри группы — из
        skud_settings.load_schematic_category_type_ids (схемные семейства).
    """
    def category_of(el):
        try:
            type_id = el.GetTypeId().IntegerValue
        except:
            return None
        return type_id_to_category.get(type_id)

    return category_of


def _address_key(el, address_param):
    return clean_text_value(_param_value(el, address_param)) or u""


def passage_points_of(devices, passage_point_param, address_param):
    """
    Разбивает устройства одного контроллера по точкам прохода — значению
    параметра passage_point_param. Пустое/отсутствующее значение → ключ
    "1" (у контроллера одна точка прохода). Внутри каждой точки прохода
    устройства отсортированы по адресу. Ключи упорядочены по первому
    появлению. Возвращает OrderedDict{key: [devices]}.
    """
    buckets = OrderedDict()

    for d in devices:
        raw = _param_value(d, passage_point_param) if passage_point_param else None
        key = clean_text_value(raw) if raw else u""
        if not key:
            key = u"1"
        buckets.setdefault(key, []).append(d)

    for key in buckets:
        buckets[key].sort(key=lambda el: _address_key(el, address_param))

    return buckets


def _signature_from_counts(counts):
    return tuple(sorted(counts.items()))


def signature_of(devices, category_of):
    """
    Сигнатура набора устройств — кортеж отсортированных пар
    (категория, количество). Устройства, для которых category_of вернул
    None, в сигнатуру не входят; их число возвращается вторым элементом.
    (signature, uncategorized_count).
    """
    counts = {}
    uncategorized = 0

    for d in devices:
        cat = category_of(d)
        if not cat:
            uncategorized += 1
            continue
        counts[cat] = counts.get(cat, 0) + 1

    return _signature_from_counts(counts), uncategorized


def classify_members(doc, member_ids, category_of):
    """
    {категория: [элементы]} для списка ElementId (членов группы или
    разгруппированных элементов). Члены без категории (рамка, линии)
    отбрасываются. Возвращает (by_category, signature).
    """
    by_category = {}

    for mid in member_ids:
        el = doc.GetElement(mid)
        if el is None:
            continue
        cat = category_of(el)
        if not cat:
            continue
        by_category.setdefault(cat, []).append(el)

    signature = _signature_from_counts(
        dict((cat, len(els)) for cat, els in by_category.items())
    )
    return by_category, signature


def group_signature(doc, group_type, category_of):
    """
    Сигнатура типовой группы по первому её размещённому экземпляру.
    Возвращает (signature, by_category) либо (None, None), если у типа
    группы нет ни одного размещённого экземпляра (её нельзя прочитать —
    пользователь должен один раз вставить группу в проект).
    """
    member_ids = None
    for g in group_type.Groups:
        try:
            member_ids = list(g.GetMemberIds())
        except:
            member_ids = None
        break

    if member_ids is None:
        return None, None

    by_category, signature = classify_members(doc, member_ids, category_of)
    return signature, by_category


def invert_category_device_type_ids(category_to_ids):
    """
    {категория: set(int)} -> {int: категория}. Для построения category_of
    реальных устройств из get_schematic_category_device_type_ids.
    """
    flat = {}
    for name, ids in category_to_ids.items():
        for i in ids:
            flat[int(i)] = name
    return flat


def invert_category_type_id_strings(category_to_id_str):
    """
    {категория: "id"} -> {int: категория}. Для построения category_of
    схемных элементов из load_schematic_category_type_ids.
    """
    flat = {}
    for name, id_str in category_to_id_str.items():
        if not id_str:
            continue
        try:
            flat[int(id_str)] = name
        except:
            continue
    return flat


def passage_point_layout_point(insert_pt, index, gap_ft):
    """
    Точка вставки origin группы точки прохода: под контроллером, каждая
    следующая точка прохода ниже предыдущей. index — 0 для первой.
    """
    from Autodesk.Revit.DB import XYZ

    return XYZ(
        insert_pt.X + gap_ft / 3.0,
        insert_pt.Y - (index + 1) * (gap_ft / 3.0),
        insert_pt.Z
    )


def match_group_name(signature, group_signatures):
    """
    Имя группы, чья сигнатура точно равна signature, либо None.
    group_signatures — {имя: signature}. При нескольких совпадениях —
    первое по порядку словаря (вызывающий подаёт OrderedDict).
    """
    for name, sig in group_signatures.items():
        if sig == signature:
            return name
    return None


def majority_value(values):
    """
    Самое частое непустое значение из списка. При равенстве частот —
    первое по порядку появления (вызывающий подаёт устройства уже
    отсортированными по адресу, поэтому результат детерминирован).
    Возвращает "" если все значения пустые.
    """
    counts = {}
    order = []
    for v in values:
        if not v:
            continue
        if v not in counts:
            counts[v] = 0
            order.append(v)
        counts[v] += 1

    if not order:
        return u""

    best = order[0]
    for v in order:
        if counts[v] > counts[best]:
            best = v
    return best


def signature_text(signature):
    """"считыватель x2 + замок + геркон" — человекочитаемая сигнатура."""
    if not signature:
        return u"(пусто)"
    parts = []
    for cat, cnt in signature:
        parts.append(u"{} x{}".format(cat, cnt) if cnt > 1 else cat)
    return u" + ".join(parts)


def layout_points_by_level(base_point, level_elevations, gap_ft):
    """
    Точки вставки для контроллеров, сгруппированных по этажам:
    level_elevations — список elevation (float, в футах), один элемент на
    контроллер, в том же порядке, что и сам список контроллеров.

    Этажи сортируются по elevation по возрастанию; первый (нижний) этаж
    располагается в base_point, следующие — со сдвигом вверх по Y на
    gap_ft за каждый этаж. Внутри одного этажа все точки идут единым
    горизонтальным рядом по X с шагом gap_ft, без ограничения длины ряда
    — контроллеров на одном этаже может быть сколько угодно.
    """
    from Autodesk.Revit.DB import XYZ

    distinct_elevations = sorted(set(level_elevations))
    row_index_by_elevation = {elev: row for row, elev in enumerate(distinct_elevations)}

    points = []
    col_by_row = {}
    for elev in level_elevations:
        row = row_index_by_elevation[elev]
        col = col_by_row.get(row, 0)
        col_by_row[row] = col + 1
        points.append(XYZ(
            base_point.X + col * gap_ft,
            base_point.Y + row * gap_ft,
            base_point.Z
        ))
    return points


def device_layout_point(insert_pt, category_layout, category, index_in_category, step_ft):
    """
    Точка вставки схемного устройства: insert_pt (точка контроллера) +
    смещение (dx, dy) категории из category_layout (в футах) + шаг
    вправо по X на каждый следующий экземпляр той же категории у этого
    же контроллера (index_in_category — 0 для первого).

    category_layout — {имя_категории: (dx_ft, dy_ft)}. Категория без
    записи в layout получает нулевое смещение (в точке контроллера).
    """
    from Autodesk.Revit.DB import XYZ

    dx, dy = category_layout.get(category, (0.0, 0.0))
    return XYZ(
        insert_pt.X + dx + index_in_category * step_ft,
        insert_pt.Y + dy,
        insert_pt.Z
    )
