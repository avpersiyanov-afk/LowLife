# -*- coding: utf-8 -*-
"""
Общие константы и логика для инструментов СКС
(структурированная кабельная система / телекоммуникационные трассы).
"""

# Значения по умолчанию НЕ заданы намеренно: имена семейств/параметров —
# соглашение конкретного проекта/компании, и не должны лежать открытым
# текстом в репозитории. Пользователь вводит их в окне настроек
# (scs_settings.py) при первом запуске — там же они и сохраняются
# (в pyRevit_config.ini на его машине). См. docs/scs-place-route-nodes.md
# за инструкцией, что именно нужно указать и какие параметры должны быть
# в семействах.
FAMILY_FILTER = u""

CABLE_PARAM_NAME = u""
ROUTE_PARAM_NAME = u""
ROUTE_PARAM_VALUE = u""
ROUTE_PARAM_VALUE_RISER = u""
DEVICE_CABLE_TYPE_VALUE = u""

OFFSET_PARAM_NAMES = []

# Ключевые слова для распознавания устройств/панелей/стояков — это просто
# общая лексика (не привязана к чьим-то внутренним именам параметров),
# поэтому для них оставлены разумные значения по умолчанию.
DEVICE_KEYWORDS = [u"коннектор", u"розетка", u"датчик", u"задание"]
DEVICE_EXCLUDE_KEYWORDS = [u"резервный"]

PANEL_KEYWORDS = [u"панель", u"кросс", u"шкаф"]
PANEL_EXCLUDE_KEYWORDS = []

RISER_KEYWORDS = [u"стояк"]
RISER_EXCLUDE_KEYWORDS = []

# Порядок разрешения категории точки, если она попала сразу в несколько
# (например рядом и панель, и устройство) — первая подошедшая побеждает.
CATEGORY_PRIORITY = ("riser", "panel", "device", "route")


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


def text_match_device(el, device_keywords=DEVICE_KEYWORDS, device_exclude_keywords=DEVICE_EXCLUDE_KEYWORDS):
    """Похож ли элемент на оконечное устройство трассы по имени/семейству."""
    return classify_element(el, [("device", device_keywords, device_exclude_keywords)]) == "device"


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


def merge_nodes(nodes, tol, points_close_fn):
    """
    Объединяет узлы трассы, находящиеся на расстоянии <= tol друг от друга,
    в один узел с суммарными данными (категории, id сегментов, устройство/панель).
    """
    result = []

    for n in nodes:
        found = None
        for r in result:
            if points_close_fn(n["point"], r["point"], tol):
                found = r
                break

        if found is None:
            result.append({
                "point": n["point"],
                "node_key": n.get("node_key"),
                "source_types": [n.get("source_type")],
                "categories": [n.get("category")],
                "segment_ids": list(set(n.get("segment_ids", []))),
                "device": n.get("device")
            })
        else:
            found["source_types"].append(n.get("source_type"))
            found["categories"].append(n.get("category"))

            for sid in n.get("segment_ids", []):
                if sid not in found["segment_ids"]:
                    found["segment_ids"].append(sid)

            if found.get("node_key") is None and n.get("node_key") is not None:
                found["node_key"] = n.get("node_key")

            if found.get("device") is None and n.get("device") is not None:
                found["device"] = n.get("device")

    return result
