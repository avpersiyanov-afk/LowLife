# -*- coding: utf-8 -*-
"""
Общие константы и логика для инструментов СКС
(структурированная кабельная система / телекоммуникационные трассы).
"""

# Значения по умолчанию НЕ заданы намеренно: имена семейств/параметров —
# соглашение конкретного проекта/компании, и не должны лежать открытым
# текстом в репозитории. Пользователь вводит их в окне настроек
# (scs_settings.py) при первом запуске — там же они и сохраняются
# (в JSON-файле %APPDATA%\pyRevit\LowLifeSCS_settings.json на его машине).
# См. docs/scs-panel.md за инструкцией, что именно нужно указать и какие
# параметры должны быть в семействах.
FAMILY_FILTER = u""

CABLE_PARAM_NAME = u""
ROUTE_PARAM_NAME = u""
ROUTE_PARAM_VALUE = u""
ROUTE_PARAM_VALUE_RISER = u""
# Форсированный тип прокладки кабеля для панелей/стояков (не для
# устройств — устройства больше не отдельная точка вставки, см.
# PlaceRouteNodes/script.py).
DEVICE_CABLE_TYPE_VALUE = u""

OFFSET_PARAM_NAMES = []

# Ключевые слова для распознавания панелей/стояков — это просто общая
# лексика (не привязана к чьим-то внутренним именам параметров), поэтому
# для них оставлены разумные значения по умолчанию.
PANEL_KEYWORDS = [u"панель", u"кросс", u"шкаф"]
PANEL_EXCLUDE_KEYWORDS = []

RISER_KEYWORDS = [u"стояк"]
RISER_EXCLUDE_KEYWORDS = []

# Порядок разрешения категории точки, если она попала сразу в несколько
# (например рядом и панель, и стояк) — первая подошедшая побеждает.
CATEGORY_PRIORITY = ("riser", "panel", "route")


def detect_cable_type(el):
    """Тип прокладки кабеля по имени типоразмера/семейства сегмента трассы."""
    names = []
    try:
        names.append((el.Symbol.Name or "").lower())
    except:
        pass
    try:
        names.append((el.Name or "").lower())
    except:
        pass
    try:
        names.append((el.Symbol.Family.Name or "").lower())
    except:
        pass

    for s in names:
        if (u"трубе" in s or u"труба" in s) and u"открыто" in s:
            return u"Труба открыто"
        if u"лотке" in s or u"лоток" in s:
            return u"Лоток"
        if u"трубе" in s or u"труба" in s:
            return u"Труба"
    return None


def _element_text(el):
    values = []
    try:
        values.append((el.Name or "").lower())
    except:
        pass
    try:
        values.append((el.Symbol.Name or "").lower())
    except:
        pass
    try:
        values.append((el.Symbol.Family.Name or "").lower())
    except:
        pass
    return " | ".join(values)


def classify_element(el, categories):
    """
    Определяет категорию элемента по ключевым словам в его имени/семействе.

    categories — список (name, keywords, exclude_keywords), проверяется
    по порядку; возвращает name первой подошедшей категории или None,
    если не одна не подошла (или подошли только слова-исключения).
    """
    text = _element_text(el)

    for name, keywords, exclude_keywords in categories:
        if any(word in text for word in exclude_keywords):
            continue
        if any(word in text for word in keywords):
            return name

    return None


def resolve_category(categories, priority=CATEGORY_PRIORITY):
    """Из списка категорий, собранных для объединённого узла, выбирает одну по приоритету."""
    present = set(c for c in categories if c)
    for name in priority:
        if name in present:
            return name
    return priority[-1]


def clear_stray_address_params(doc, param_names, allowed_type_ids):
    """
    Находит элементы категорий, где могут стоять маркеры/устройства СКС
    (Обобщённые модели, коммуникационные/электротехнические устройства,
    электрооборудование), у которых заполнен хотя бы один из param_names,
    но чей тип НЕ входит в allowed_type_ids (т.е. это не настоящий
    route/riser маркер) — и очищает эти параметры.

    Нужно, чтобы старые/случайные значения адреса на устройствах не
    попадали в граф маршрута через ADDR_PREV (устройство могло получить
    такое значение до разделения на отдельные семейства панель/устройство/
    маршрут, или было введено вручную).

    Возвращает список задетых элементов. Вызывать внутри revit.Transaction.
    """
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
    from lowlife.params import get_string_param, set_string_param

    categories = [
        BuiltInCategory.OST_GenericModel,
        BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_ElectricalFixtures,
        BuiltInCategory.OST_DataDevices,
        BuiltInCategory.OST_ElectricalEquipment
    ]

    cleared = []

    for cat in categories:
        collector = FilteredElementCollector(doc) \
            .OfCategory(cat) \
            .WhereElementIsNotElementType()

        for el in collector:
            try:
                if el.GetTypeId() in allowed_type_ids:
                    continue
            except:
                continue

            has_stray_value = any(get_string_param(el, name) for name in param_names)

            if has_stray_value:
                for name in param_names:
                    set_string_param(el, name, u"")
                cleared.append(el)

    return cleared


def _point_sort_key(pt):
    return (pt.X, pt.Y, pt.Z)


def _pick_cluster_point(members):
    """
    Точка кластера должна быть детерминированной (не зависеть от порядка
    обхода узлов, который между запусками может отличаться) — иначе
    повторный запуск PlaceRouteNodes мог случайно сместить "эталонную"
    точку кластера на пару мм и пересечь границу допуска дедупа, создав
    копию элемента рядом со старым вместо его обновления.

    Приоритет: точка помеченного узла (панель/стояк), если такой есть в
    кластере — так итоговая точка совпадает с реальным положением
    элемента, а не узла графа линии. Иначе — точка с наименьшими
    координатами (X, затем Y, затем Z), одна и та же при любом порядке.
    """
    marked = [m for m in members if m.get("device") is not None]
    pool = marked if marked else members
    return min((m["point"] for m in pool), key=_point_sort_key)


def merge_nodes(nodes, tol, points_close_fn):
    """
    Объединяет узлы трассы, находящиеся на расстоянии <= tol друг от друга,
    в один узел с суммарными данными (категории, id сегментов, устройство/панель).
    """
    clusters = []

    for n in nodes:
        found = None
        for cl in clusters:
            if points_close_fn(n["point"], cl["point"], tol):
                found = cl
                break

        if found is None:
            clusters.append({"point": n["point"], "members": [n]})
        else:
            found["members"].append(n)

    result = []

    for cl in clusters:
        members = cl["members"]
        point = _pick_cluster_point(members)

        node_key = None
        device = None
        segment_ids = []

        for n in members:
            if node_key is None and n.get("node_key") is not None:
                node_key = n.get("node_key")
            if device is None and n.get("device") is not None:
                device = n.get("device")
            for sid in n.get("segment_ids", []):
                if sid not in segment_ids:
                    segment_ids.append(sid)

        result.append({
            "point": point,
            "node_key": node_key,
            "source_types": [n.get("source_type") for n in members],
            "categories": [n.get("category") for n in members],
            "segment_ids": segment_ids,
            "device": device
        })

    return result
