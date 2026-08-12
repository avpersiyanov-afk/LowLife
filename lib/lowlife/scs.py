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

# Ключевые слова для распознавания типовой аннотации стояка (стрелка
# подъёма/опуска) — отдельные от RISER_KEYWORDS, т.к. имя типа
# аннотации обычно не содержит слова "стояк" (см. PlaceRouteNodes).
RISER_ANNOTATION_KEYWORDS = []

# Порядок разрешения категории точки, если она попала сразу в несколько
# (например рядом и панель, и стояк) — первая подошедшая побеждает.
CATEGORY_PRIORITY = ("riser", "panel", "route")


def safe_element_name(el):
    """
    Имя элемента через Element.Name.GetValue(el) — прямой доступ el.Name
    в IronPython у некоторых типов Revit-элементов (в т.ч. FamilySymbol)
    падает с ошибкой неоднозначного связывания свойства и уходит в
    except, поэтому используем статическое свойство через рефлексию.
    Возвращает None, если имя получить не удалось никаким способом.
    """
    from Autodesk.Revit.DB import Element

    try:
        return Element.Name.GetValue(el)
    except:
        try:
            return el.Name
        except:
            return None


def detect_cable_type(el):
    """Тип прокладки кабеля по имени типоразмера/семейства сегмента трассы."""
    names = []
    try:
        names.append((safe_element_name(el.Symbol) or "").lower())
    except:
        pass
    try:
        names.append((safe_element_name(el) or "").lower())
    except:
        pass
    try:
        names.append((safe_element_name(el.Symbol.Family) or "").lower())
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
        values.append((safe_element_name(el) or "").lower())
    except:
        pass
    try:
        values.append((safe_element_name(el.Symbol) or "").lower())
    except:
        pass
    try:
        values.append((safe_element_name(el.Symbol.Family) or "").lower())
    except:
        pass
    return " | ".join(values)


def classify_element(el, categories):
    """
    Определяет категорию элемента по ключевым словам в его имени/семействе.

    categories — список (name, keywords, exclude_keywords), проверяется
    по порядку; возвращает name первой подошедшей категории или None,
    если не одна не подошла (или подошли только слова-исключения).

    Ключевые слова приводятся к нижнему регистру здесь же (а не только
    "text", который уже lower()) — они часто приходят из пользовательских
    настроек (например «Ключевое слово изолятора») и могут быть введены с
    большой буквы; без этого сравнение "Слово" in "текст в нижнем
    регистре" никогда не совпадает, и классификация молча не срабатывает
    ни для одного элемента.
    """
    text = _element_text(el)

    for name, keywords, exclude_keywords in categories:
        if any(word.lower() in text for word in exclude_keywords if word):
            continue
        if any(word.lower() in text for word in keywords if word):
            return name

    return None


def resolve_category(categories, priority=CATEGORY_PRIORITY):
    """Из списка категорий, собранных для объединённого узла, выбирает одну по приоритету."""
    present = set(c for c in categories if c)
    for name in priority:
        if name in present:
            return name
    return priority[-1]


def is_excluded_device(el, excluded_keywords):
    """Резервный (исключаемый из расчёта) порт — по ключевым словам в имени семейства."""
    try:
        fam_name = safe_element_name(el.Symbol.Family)
    except:
        return False
    return any(w.lower() in (fam_name or u"").lower() for w in excluded_keywords if w)


def get_workset_name(el, workset_param_name):
    """
    Имя рабочего набора элемента: сперва по имени параметра
    (workset_param_name — на случай проектов, где рабочий набор продублирован
    в обычный параметр), иначе — через нативный BuiltInParameter.ELEM_PARTITION_PARAM.
    """
    from Autodesk.Revit.DB import BuiltInParameter
    from lowlife.params import get_param_any

    val = get_param_any(el, workset_param_name)
    if val:
        return val
    try:
        p = el.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
        if p and p.HasValue:
            v = p.AsValueString()
            if v:
                return v
    except:
        pass
    return None


def panel_matches(panel, workset_param_name, workset_filter_key, norm_fn):
    """Целевая панель — по ключевому слову в имени её рабочего набора."""
    ws = norm_fn(get_workset_name(panel, workset_param_name))
    if not ws:
        return False
    return workset_filter_key.lower() in ws.lower()


def clear_stray_address_params(doc, param_names, allowed_type_ids,
                                workset_param_name=None, workset_filter_key=None):
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

    workset_param_name/workset_filter_key — ограничить очистку одним
    рабочим набором. Нужно, когда несколько дисциплин делят одни и те же
    имена параметров адреса (например СКС и СКУД на общем SMNX_Сегмент):
    без этого очистка одной дисциплины стёрла бы адреса другой. Если не
    заданы, поведение прежнее — по всему документу.

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

            if workset_filter_key:
                ws = get_workset_name(el, workset_param_name)
                if not ws or workset_filter_key.lower() not in ws.lower():
                    continue

            has_stray_value = any(get_string_param(el, name) for name in param_names)

            if has_stray_value:
                for name in param_names:
                    set_string_param(el, name, u"")
                cleared.append(el)

    return cleared


def _point_sort_key(pt):
    return (pt.X, pt.Y, pt.Z)


def _pick_cluster_point(members, existing_points, tol, points_close_fn):
    """
    Точка кластера должна быть детерминированной (не зависеть от порядка
    обхода узлов, который между запусками может отличаться) — иначе
    повторный запуск PlaceRouteNodes мог случайно сместить "эталонную"
    точку кластера на пару мм и пересечь границу допуска дедупа, создав
    копию элемента рядом со старым вместо его обновления.

    Приоритет:
    1. Точка уже существующего на виде маркера (existing_points), если
       хотя бы один из членов кластера физически рядом с ним — иначе при
       появлении нового близкого узла графа (например, от только что
       добавленного сегмента трассы) кластер мог "утянуть" итоговую точку
       на новый узел вместо уже занятой существующим маркером точки,
       из-за чего дедуп её не находил и создавал дубль рядом.
    2. Точка помеченного узла (панель/стояк), если такой есть в кластере
       — совпадает с реальным положением элемента, а не узла графа линии.
    3. Иначе — точка с наименьшими координатами (X, затем Y, затем Z),
       одна и та же при любом порядке обхода.
    """
    if existing_points:
        for m in members:
            for ex_point in existing_points:
                if points_close_fn(m["point"], ex_point, tol):
                    return ex_point

    marked = [m for m in members if m.get("device") is not None]
    pool = marked if marked else members
    return min((m["point"] for m in pool), key=_point_sort_key)


def merge_nodes(nodes, tol, points_close_fn, existing_points=None):
    """
    Объединяет узлы трассы, находящиеся на расстоянии <= tol друг от друга,
    в один узел с суммарными данными (категории, id сегментов, устройство/панель).

    existing_points — координаты уже вставленных на виде маркеров
    (panel/route/riser); если задано, приоритет при выборе итоговой точки
    кластера (см. _pick_cluster_point).
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
        point = _pick_cluster_point(members, existing_points, tol, points_close_fn)

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
