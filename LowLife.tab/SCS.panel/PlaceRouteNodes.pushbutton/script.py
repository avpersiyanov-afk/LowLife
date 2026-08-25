# -*- coding: utf-8 -*-
__title__ = "Узлы\nтрассы"
__doc__ = "Расставляет панели/узлы маршрута/стояки в точках трассы кабеля"
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralType
from System.Collections.Generic import List
from pyrevit import revit, forms

from lowlife.geometry import (
    get_point, get_curve_data, point_key, points_close,
    is_point_on_curve, sort_points, get_document_levels, find_level_for_elevation,
    get_element_level
)
from lowlife.params import get_double_param, set_double_param, set_string_param
from lowlife.scs import classify_element, merge_nodes, resolve_category
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

tolerance = 0.01
point_on_curve_tolerance = 0.05
merge_tolerance = 0.1


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

scs_settings.require(settings, [
    "panel_type_id", "route_type_id", "riser_type_id",
    "family_filter", "route_param_value", "route_param_value_riser",
    "device_cable_type_value"
])
# Имена параметров (cable_param_name, route_param_name,
# offset_param_names) здесь не проверяются — их наличие/привязку в
# проекте проверяет и чинит кнопка «Параметры СКС» (SetupParameters).

FAMILY_FILTER = settings["family_filter"]
CABLE_PARAM_NAME = settings["cable_param_name"]
ROUTE_PARAM_NAME = settings["route_param_name"]
ROUTE_PARAM_VALUE = settings["route_param_value"]
ROUTE_PARAM_VALUE_RISER = settings["route_param_value_riser"]
# Форсированный тип прокладки для панелей/стояков (точек-концов, а не
# узлов посреди трассы) — устройства больше не отдельная категория,
# семейство в их точках не ставится, поэтому DEVICE в названии не осталось.
ENDPOINT_CABLE_TYPE_VALUE = settings["device_cable_type_value"]
PANEL_KEYWORDS = settings["panel_keywords"]
PANEL_EXCLUDE_KEYWORDS = settings["panel_exclude_keywords"]
RISER_KEYWORDS = settings["riser_keywords"]
RISER_EXCLUDE_KEYWORDS = settings["riser_exclude_keywords"]
RISER_ANNOTATION_KEYWORDS = settings["riser_annotation_keywords"]
OFFSET_PARAM_NAMES = settings["offset_param_names"]

TYPE_ID_BY_CATEGORY = {
    "panel": ElementId(int(settings["panel_type_id"])),
    "route": ElementId(int(settings["route_type_id"])),
    "riser": ElementId(int(settings["riser_type_id"])),
}

symbols_by_category = {}
for category_name, type_id in TYPE_ID_BY_CATEGORY.items():
    symbol = doc.GetElement(type_id)
    if symbol is None:
        forms.alert(
            u"Не найден выбранный тип для категории «{}». "
            u"Откройте настройки и выберите тип заново.".format(category_name),
            exitscript=True
        )
    symbols_by_category[category_name] = symbol

placed_type_ids = set(t.IntegerValue for t in TYPE_ID_BY_CATEGORY.values())


# ------------------------------------------------------------
# ОСНОВНОЙ КОД
# ------------------------------------------------------------

generic = FilteredElementCollector(doc, view.Id) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType() \
    .ToElements()

segments = []
segments_by_id = {}

for el in generic:
    try:
        fam_name = el.Symbol.Family.Name
    except:
        continue

    if FAMILY_FILTER not in fam_name:
        continue

    curve, p1, p2 = get_curve_data(el, view)
    if curve is None:
        continue

    data = {
        "element": el,
        "id": el.Id.IntegerValue,
        "curve": curve,
        "p1": p1,
        "p2": p2
    }
    segments.append(data)
    segments_by_id[data["id"]] = data

if not segments:
    forms.alert("Сегменты трассы не найдены.", exitscript=True)

all_endpoints = []
for s in segments:
    all_endpoints.append(s["p1"])
    all_endpoints.append(s["p2"])

split_points_by_segment = {}

for s in segments:
    pts = [s["p1"], s["p2"]]
    for pt in all_endpoints:
        ok, projected = is_point_on_curve(s["curve"], pt, point_on_curve_tolerance)
        if ok and projected is not None:
            exists = False
            for ex in pts:
                if ex.DistanceTo(projected) <= tolerance:
                    exists = True
                    break
            if not exists:
                pts.append(projected)

    split_points_by_segment[s["id"]] = sort_points(s["curve"], pts)

graph = {}
node_points = {}
segment_ids_by_node = {}

for s in segments:
    pts = split_points_by_segment[s["id"]]
    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]

        if a.DistanceTo(b) <= tolerance:
            continue

        k1 = point_key(a, tolerance)
        k2 = point_key(b, tolerance)

        node_points[k1] = a
        node_points[k2] = b

        if k1 not in graph:
            graph[k1] = []
        if k2 not in graph:
            graph[k2] = []

        if k2 not in graph[k1]:
            graph[k1].append(k2)
        if k1 not in graph[k2]:
            graph[k2].append(k1)

        if k1 not in segment_ids_by_node:
            segment_ids_by_node[k1] = set()
        if k2 not in segment_ids_by_node:
            segment_ids_by_node[k2] = set()

        segment_ids_by_node[k1].add(s["id"])
        segment_ids_by_node[k2].add(s["id"])

# Панели и стояки ищем среди одних и тех же категорий элементов,
# различаем по ключевым словам (classify_element). Устройства отдельной
# точкой вставки больше не считаются — им достаточно ближайшего узла
# маршрута, а линию к ним подводят прямо (см. SyncCircuitsAndLengths).
candidate_categories = [
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_ElectricalEquipment
]

all_candidates = []

for cat in candidate_categories:
    all_candidates.extend(
        FilteredElementCollector(doc, view.Id)
        .OfCategory(cat)
        .WhereElementIsNotElementType()
        .ToElements()
    )

classify_rules = [
    ("riser", RISER_KEYWORDS, RISER_EXCLUDE_KEYWORDS),
    ("panel", PANEL_KEYWORDS, PANEL_EXCLUDE_KEYWORDS),
]

marked_points = []


def add_marked_point(el, pt, category, level_override=None):
    nearest_key = None
    nearest_dist = None

    for k, p in node_points.items():
        try:
            d = pt.DistanceTo(p)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest_key = k
        except:
            pass

    marked_points.append({
        "element": el,
        "point": pt,
        "node_key": nearest_key,
        "category": category,
        "level_override": level_override
    })


for el in all_candidates:
    category = classify_element(el, classify_rules)
    if category is None:
        continue

    pt = get_point(el)
    if pt is None:
        continue

    add_marked_point(el, pt, category)

# Стояки на этом виде МОГУТ отмечаться типовой аннотацией (со стрелкой
# подъёма/опуска) вместо реального устройства — аннотация не имеет
# собственной высоты в модели (видна только на виде), поэтому узел
# стояка ставится в её точке на плане (X/Y) на условной высоте 3000мм
# от уровня активного вида.
#
# "Вместо" — это ожидание, а не гарантия: если для одного и того же
# стояка в проекте есть И реальное устройство (уже отмечено выше, на
# своей настоящей высоте), И эта аннотация, получаются 2 точки с
# одинаковым X/Y, но разной высотой (аннотация — искусственные +3000мм
# от уровня, устройство — реальная отметка) — merge_nodes их не сливает
# (проверяет полное 3D-расстояние), и на плане ставится 2 маркера друг
# на друге. Поэтому аннотацию пропускаем, если рядом в плане уже есть
# точка реального устройства-стояка — её высота настоящая, ей и
# доверяем.
RISER_ANNOTATION_OFFSET_MM = 3000.0
RISER_ANNOTATION_OFFSET_FT = RISER_ANNOTATION_OFFSET_MM / 304.8

RISER_ANNOTATION_DEDUP_RADIUS_MM = 500.0
RISER_ANNOTATION_DEDUP_RADIUS_FT = RISER_ANNOTATION_DEDUP_RADIUS_MM / 304.8

view_level = None
try:
    if hasattr(view, "GenLevel") and view.GenLevel:
        view_level = view.GenLevel
except:
    pass

riser_annotations_skipped = 0

if view_level is not None:
    annotation_elevation = view_level.Elevation + RISER_ANNOTATION_OFFSET_FT

    riser_annotations = FilteredElementCollector(doc, view.Id) \
        .OfCategory(BuiltInCategory.OST_GenericAnnotation) \
        .WhereElementIsNotElementType() \
        .ToElements()

    # Точки уже отмеченных РЕАЛЬНЫХ устройств-стояков (marked_points на
    # этот момент содержит только их — аннотации добавляются ниже, в
    # этом же цикле) — с ними и сверяем каждую аннотацию.
    real_riser_points = [m["point"] for m in marked_points if m["category"] == "riser"]

    for el in riser_annotations:
        if not RISER_ANNOTATION_KEYWORDS:
            continue
        if classify_element(el, [("riser", RISER_ANNOTATION_KEYWORDS, [])]) != "riser":
            continue

        pt = get_point(el)
        if pt is None:
            continue

        dedup_radius_sq = RISER_ANNOTATION_DEDUP_RADIUS_FT ** 2
        already_marked_nearby = any(
            (rp.X - pt.X) ** 2 + (rp.Y - pt.Y) ** 2 <= dedup_radius_sq
            for rp in real_riser_points
        )
        if already_marked_nearby:
            riser_annotations_skipped += 1
            continue

        riser_pt = XYZ(pt.X, pt.Y, annotation_elevation)
        # Аннотация — Annotation-элемент, не Model, у неё нет LevelId
        # (get_element_level(doc, el) ничего не найдёт) — передаём
        # уровень вида явно, а не полагаемся на резервный поиск по Z.
        add_marked_point(el, riser_pt, "riser", level_override=view_level)

raw_nodes = []

for nk, neighbors in graph.items():
    # Включая узлы с одним соседом — иначе свободные концы линий
    # (не примыкающие ни к другой линии, ни к панели/стояку)
    # не получают узел маршрута вообще.
    raw_nodes.append({
        "point": node_points[nk],
        "node_key": nk,
        "source_type": "graph_node",
        "category": "route",
        "segment_ids": list(segment_ids_by_node.get(nk, []))
    })

for m in marked_points:
    raw_nodes.append({
        "point": m["point"],
        "node_key": m["node_key"],
        "source_type": "marked_point",
        "category": m["category"],
        "segment_ids": list(segment_ids_by_node.get(m["node_key"], [])) if m["node_key"] in segment_ids_by_node else [],
        "device": m
    })

# Сегменты трассы (линии) ищутся только на активном виде (generic выше)
# — это верно, кнопка расставляет узлы по трассе, видимой на текущем
# виде. НО проверка "маркер уже стоит" раньше тоже была ограничена этим
# же view.Id-коллектором — а это НЕВЕРНО: маркер, поставленный раньше на
# ДРУГОМ виде (например на другом уровне, или на отдельном тестовом виде
# того же уровня), физически существует в документе и никуда не делся,
# просто не виден в текущем view.Id-запросе (или скрыт настройками
# видимости этого вида) — из-за чего find_existing_element его не
# находил и создавал дубль ровно в той же точке. Найдено по факту: Revit
# ругался на "идентичные экземпляры" при 0 пропущенных этой кнопкой и
# largest_cluster_size=1 (то есть новый узел ни с чем не сливался и не
# распознавался как уже существующий) — сходится только если "старый"
# партнёр дубля просто не входил в это view.Id-множество.
#
# Поэтому проверка "уже существует" — по ВСЕМУ документу, без view.Id
# (в отличие от поиска сегментов трассы, который остаётся по активному
# виду).
#
# Собираем существующие маркеры ДО merge_nodes — их точки участвуют в
# выборе итоговой точки каждого кластера (см. _pick_cluster_point в
# scs.py): если новый узел графа рядом с уже вставленным маркером
# (например, из-за только что добавленного сегмента трассы) — кластер
# должен "прилипнуть" к точке существующего маркера, а не к min(X,Y,Z)
# среди узлов графа, иначе итоговая точка могла сместиться на новую и
# дедуп не находил старый маркер, создавая дубль рядом с ним.
existing_list = []
for el in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_GenericModel).WhereElementIsNotElementType():
    try:
        if el.GetTypeId().IntegerValue in placed_type_ids:
            pt = get_point(el)
            if pt is not None:
                existing_list.append((el, pt))
    except:
        pass

existing_points = [pt for el, pt in existing_list]

insert_nodes = merge_nodes(raw_nodes, merge_tolerance, points_close, existing_points=existing_points)

for node in insert_nodes:
    node["category"] = resolve_category(node.get("categories", []))


# ------------------------------------------------------------
# ДИАГНОСТИКА: КРУПНЫЕ КЛАСТЕРЫ (много элементов слито в одну точку)
# ------------------------------------------------------------
# merge_nodes сливает узлы по ТРАНЗИТИВНОЙ близости (см. scs.merge_nodes):
# если рядом идёт цепочка узлов, каждый на расстоянии <= merge_tolerance
# (30мм) от соседнего, весь ряд становится ОДНИМ кластером — у такого
# слияния нет верхнего предела на общий разброс, если сама цепочка длинная
# (например, узлы через каждые 20-25мм на протяжении нескольких метров).
# Это не обязательно баг: если 46 узлов реально сошлись в одной физической
# точке (например разброс всего 10-50мм) — это верно, просто плотная
# развязка. А если разброс — метры, то это, скорее всего, "цепочка"
# близко идущих, но РАЗНЫХ узлов, которая не должна была схлопнуться в
# одну точку — тогда см. ID сегментов ниже, чтобы найти этот участок
# трассы в модели и разобраться, откуда там столько близких узлов.
LARGE_CLUSTER_THRESHOLD = 3
MM_PER_FT = 304.8


def _mm(v):
    return u"{:.0f}".format(v * MM_PER_FT)


def _count_by(values):
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return u", ".join(u"{}: {}".format(k, v) for k, v in sorted(counts.items()))


large_clusters = [n for n in insert_nodes if len(n.get("source_types", [])) >= LARGE_CLUSTER_THRESHOLD]
_cluster_sizes = [len(n.get("source_types", [])) for n in insert_nodes]
largest_cluster_size = max(_cluster_sizes) if _cluster_sizes else 0

if large_clusters:
    from pyrevit import script as pyrevit_script
    output = pyrevit_script.get_output()

    output.print_md(
        u"### Крупные кластеры узлов — {} и более элементов в одной точке ({})".format(
            LARGE_CLUSTER_THRESHOLD, len(large_clusters)
        )
    )
    output.print_md(
        u"«Разброс X x Y x Z» — размер условного параллелепипеда вокруг всех "
        u"узлов кластера ДО слияния в одну точку. Единицы-десятки мм — "
        u"реально одна точка, просто неточно начерчено. Метры — вероятно, "
        u"цепочка близко идущих, но разных узлов; см. ID сегментов трассы."
    )

    large_clusters_table = []
    for n in sorted(large_clusters, key=lambda n: -len(n.get("source_types", []))):
        member_points = n.get("member_points") or []
        xs = [p.X for p in member_points]
        ys = [p.Y for p in member_points]
        zs = [p.Z for p in member_points]
        spread = u"{} x {} x {}".format(
            _mm(max(xs) - min(xs)) if xs else u"0",
            _mm(max(ys) - min(ys)) if ys else u"0",
            _mm(max(zs) - min(zs)) if zs else u"0"
        )

        segment_ids = n.get("segment_ids", [])
        segment_ids_text = u", ".join(str(sid) for sid in segment_ids[:30])
        if len(segment_ids) > 30:
            segment_ids_text += u", ... ещё {}".format(len(segment_ids) - 30)

        large_clusters_table.append([
            _mm(n["point"].X), _mm(n["point"].Y), _mm(n["point"].Z),
            len(n.get("source_types", [])),
            spread,
            n.get("category") or u"-",
            _count_by(n.get("source_types", [])),
            _count_by(n.get("categories", [])),
            segment_ids_text or u"-"
        ])

    output.print_table(
        table_data=large_clusters_table,
        columns=[
            u"X, мм", u"Y, мм", u"Z, мм", u"Элементов", u"Разброс X x Y x Z, мм",
            u"Итог. категория", u"Источники", u"Категории членов", u"ID сегментов трассы"
        ]
    )


# Если в точке уже стоит любой маркер нужного типа (panel/route/riser)
# — точка полностью пропускается, ничего не создаётся и не
# перезаписывается (см. цикл ниже). Дедуп нужен только чтобы не
# создать дубль поверх уже расставленного узла.
#
# Простой линейный перебор без разбивки по сетке — медленнее (O(n²)
# вместо O(n) на сетке), но однозначно надёжный: раньше сетка/деление
# на ячейки где-то давало сбой (репортилось как дубль ровно в той же
# точке, где уже стоял маркер), и разбираться в причине сложнее, чем
# просто убрать промежуточную структуру данных.
consumed_ids = set()


def find_existing_element(point):
    """Ближайший ещё не использованный существующий элемент нужного типа в пределах merge_tolerance."""
    best_el = None
    best_dist = None

    for el, pt in existing_list:
        if el.Id in consumed_ids:
            continue
        try:
            d = point.DistanceTo(pt)
        except:
            continue
        if d <= merge_tolerance and (best_dist is None or d < best_dist):
            best_dist = d
            best_el = el

    return best_el

created = []
skipped = []
counts_by_category = {"panel": 0, "route": 0, "riser": 0}
# ElementId.IntegerValue созданного элемента -> кластер insert_nodes, из
# которого он создан — нужно для диагностики дублей ниже (см. блок
# "ЭЛЕМЕНТЫ, РЕАЛЬНО ОКАЗАВШИЕСЯ РЯДОМ"): показать, из каких сегментов/
# скольки исходных узлов получилась именно эта точка.
created_origin_by_id = {}

document_levels = get_document_levels(doc)
if not document_levels:
    forms.alert(u"В проекте нет ни одного уровня.", exitscript=True)

with revit.Transaction("Place Route Nodes"):

    for node in insert_nodes:
        point = node["point"]
        category = node["category"]
        target_symbol = symbols_by_category[category]

        # Если в этой точке уже стоит маркер нужного типа — точку
        # полностью пропускаем: ничего не создаём и не обновляем.
        existing = find_existing_element(point)

        if existing is not None:
            consumed_ids.add(existing.Id)
            skipped.append(existing)
            continue

        if not target_symbol.IsActive:
            target_symbol.Activate()

        counts_by_category[category] += 1

        route_value = ROUTE_PARAM_VALUE_RISER if category == "riser" else ROUTE_PARAM_VALUE

        line_offset_value = None
        cable_type_value = None
        level = None

        device = node.get("device")
        is_marked = device is not None and category in ("panel", "riser")

        if is_marked:
            cable_type_value = ENDPOINT_CABLE_TYPE_VALUE
            dev_el = device.get("element")
            if dev_el is not None:
                line_offset_value = get_double_param(dev_el, OFFSET_PARAM_NAMES)
                # Панель/стояк — уровень берём с самого элемента
                # (его параметр «Уровень»), а не по высоте точки. Кроме
                # аннотации стояка (level_override) — у неё нет LevelId.
                level = device.get("level_override") or get_element_level(doc, dev_el)

        # Тип прокладки для route-узла НЕ определяется здесь — на стыке
        # двух сегментов с разным способом прокладки (труба/лоток) нужно
        # направление "к устройствам", а оно известно только после
        # построения дерева адресации в RenumberAddresses (см. там же).
        # Здесь для route оставляем параметр пустым до следующего
        # запуска «Адреса узлов» — он и перезапишет верное значение.
        for sid in node.get("segment_ids", []):
            if sid not in segments_by_id:
                continue

            seg_el = segments_by_id[sid]["element"]

            if line_offset_value is None:
                line_offset_value = get_double_param(seg_el, OFFSET_PARAM_NAMES)

            if line_offset_value is not None:
                break

        if level is None:
            # Уровень рабочей плоскости самой линии ненадёжен (line-based
            # семейство не всегда привязано к реальному этажу через
            # LevelId) — берём уровень ближайшей панели/стояка.
            nearest_marked = None
            nearest_marked_dist = None

            for m in marked_points:
                try:
                    d = point.DistanceTo(m["point"])
                except:
                    continue
                if nearest_marked_dist is None or d < nearest_marked_dist:
                    nearest_marked_dist = d
                    nearest_marked = m

            if nearest_marked is not None:
                level = nearest_marked.get("level_override") or get_element_level(doc, nearest_marked["element"])

        if level is None:
            # Нет ни одной панели/стояка с уровнем — резервный
            # вариант по высоте точки.
            level = find_level_for_elevation(point.Z, document_levels)

        el = doc.Create.NewFamilyInstance(point, target_symbol, level, StructuralType.NonStructural)

        if el:
            if line_offset_value is not None:
                set_double_param(el, OFFSET_PARAM_NAMES, line_offset_value)

            if cable_type_value is not None:
                set_string_param(el, CABLE_PARAM_NAME, cable_type_value)

            set_string_param(el, ROUTE_PARAM_NAME, route_value)
            created.append(el)
            created_origin_by_id[el.Id.IntegerValue] = node


# ------------------------------------------------------------
# ДИАГНОСТИКА: ЭЛЕМЕНТЫ, РЕАЛЬНО ОКАЗАВШИЕСЯ РЯДОМ ПОСЛЕ РАССТАНОВКИ
# ------------------------------------------------------------
# Отчёт по кластерам выше (largest_cluster_size) показывает только то, что
# видел merge_nodes ДО создания — если он посчитал каждую точку своим
# кластером из 1 элемента, крупных кластеров там не будет, даже если по
# факту два РАЗНЫХ кластера в итоге создали элементы почти/точно друг на
# друге (например, оба "прилипли" к одной уже существующей точке — тогда
# find_existing_element находит и пропускает только первый из них,
# consumed_ids не даёт второму найти тот же существующий элемент второй
# раз, и второй создаётся заново рядом/поверх). Поэтому здесь — прямая
# проверка ПОСЛЕ расстановки: перебираются все маркеры нужных типов,
# реально стоящие на виде (и новые, и уже бывшие), и находятся пары точек
# ближе DUPLICATE_SCAN_RADIUS_MM друг к другу — это как раз то, что видит
# Revit в предупреждении "В одном и том же месте имеются идентичные
# экземпляры".
#
# ВАЖНО: сканируем ВЕСЬ ДОКУМЕНТ, а не только активный вид — предупреждение
# Revit "идентичные экземпляры" не привязано к виду, оно про весь проект
# целиком (в отличие от расстановки/дедупа самой кнопки, которые
# намеренно ограничены активным видом). Если раньше отчёт считал только
# по текущему виду, его число пар могло не совпадать с числом
# предупреждений Revit — не потому что расчёт неверный, а потому что
# они считали разные множества элементов.
DUPLICATE_SCAN_RADIUS_MM = 150.0
DUPLICATE_SCAN_RADIUS_FT = DUPLICATE_SCAN_RADIUS_MM / MM_PER_FT

# Пары в пределах этого допуска считаются "точным" совпадением (похоже
# на то, что реально видит Revit под "идентичные экземпляры") — отдельно
# от более широкого DUPLICATE_SCAN_RADIUS_MM, который ловит и просто
# "подозрительно близко", не обязательно то же самое предупреждение.
EXACT_DUPLICATE_RADIUS_MM = 5.0
EXACT_DUPLICATE_RADIUS_FT = EXACT_DUPLICATE_RADIUS_MM / MM_PER_FT

all_placed_after = []
for el in FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_GenericModel) \
        .WhereElementIsNotElementType():
    try:
        if el.GetTypeId().IntegerValue in placed_type_ids:
            pt = get_point(el)
            if pt is not None:
                all_placed_after.append((el, pt))
    except:
        continue

created_ids_set = set(el.Id.IntegerValue for el in created)

duplicate_pairs = []
exact_duplicate_pairs = []
count_placed = len(all_placed_after)
for i in range(count_placed):
    el_i, pt_i = all_placed_after[i]
    for j in range(i + 1, count_placed):
        el_j, pt_j = all_placed_after[j]
        try:
            d = pt_i.DistanceTo(pt_j)
        except:
            continue
        if d <= DUPLICATE_SCAN_RADIUS_FT:
            duplicate_pairs.append((el_i, el_j, d))
            if d <= EXACT_DUPLICATE_RADIUS_FT:
                exact_duplicate_pairs.append((el_i, el_j, d))

if duplicate_pairs:
    from pyrevit import script as pyrevit_script
    output = pyrevit_script.get_output()

    def _link(el):
        """Кликабельная ссылка на элемент (выделяет и показывает его в Revit
        при клике в окне вывода pyRevit) — если linkify недоступен в этой
        версии pyRevit, откатывается на обычный текст с ID."""
        try:
            return output.linkify([el.Id], title=str(el.Id.IntegerValue))
        except:
            return str(el.Id.IntegerValue)

    output.print_md(
        u"### Элементы почти/точно в одной точке после расстановки — весь документ ({})".format(
            len(duplicate_pairs)
        )
    )
    output.print_md(
        u"Считано по ВСЕМУ документу (все виды/уровни), не только по активному "
        u"виду — предупреждение Revit «идентичные экземпляры» тоже не привязано "
        u"к виду, так что числа теперь должны быть сравнимы. Из них ближе "
        u"{:.0f}мм (похоже на то, что видит сам Revit): **{}**.\n\n"
        u"Пары ближе {:.0f}мм друг к другу — независимо от того, из какого "
        u"кластера merge_nodes они пришли. «Новый»/«уже был» — создан этим "
        u"запуском кнопки или существовал до него. Клик по ID — выделяет и "
        u"показывает элемент в модели. Все элементы из пар ниже также сразу "
        u"выделены в модели — используйте «Zoom to Fit Selection», чтобы "
        u"увидеть их расположение целиком.".format(
            EXACT_DUPLICATE_RADIUS_MM, len(exact_duplicate_pairs), DUPLICATE_SCAN_RADIUS_MM
        )
    )

    def _origin_text(el):
        """Из какого(их) сегмента(ов) трассы и скольки исходных узлов
        получилась точка этого элемента — только для созданных этим
        запуском (для "уже был" происхождение неизвестно, элемент не из
        insert_nodes этого прогона)."""
        node = created_origin_by_id.get(el.Id.IntegerValue)
        if node is None:
            return u"-"
        seg_ids = node.get("segment_ids", [])
        seg_text = u", ".join(str(s) for s in seg_ids[:10])
        if len(seg_ids) > 10:
            seg_text += u", ..."
        return u"{} узл. / сегм.: {}".format(len(node.get("source_types", [])), seg_text or u"-")

    def _raw_distance_text(el_i, el_j):
        """Расстояние между ИСХОДНЫМИ точками (node["point"] ДО создания
        элемента) — если обе стороны пары из этого запуска. Отличие от
        итогового расстояния покажет, изменилась ли точка между
        кластеризацией (merge_nodes) и фактическим созданием элемента
        (NewFamilyInstance) — то есть где именно две разные точки
        "слиплись" в одну."""
        node_i = created_origin_by_id.get(el_i.Id.IntegerValue)
        node_j = created_origin_by_id.get(el_j.Id.IntegerValue)
        if node_i is None or node_j is None:
            return u"-"
        try:
            raw_d = node_i["point"].DistanceTo(node_j["point"])
        except:
            return u"?"
        return u"{:.1f}".format(raw_d * MM_PER_FT)

    duplicate_pairs_table = []
    for el_i, el_j, d in sorted(duplicate_pairs, key=lambda t: t[2]):
        duplicate_pairs_table.append([
            _link(el_i),
            u"новый" if el_i.Id.IntegerValue in created_ids_set else u"уже был",
            _origin_text(el_i),
            _link(el_j),
            u"новый" if el_j.Id.IntegerValue in created_ids_set else u"уже был",
            _origin_text(el_j),
            u"{:.1f}".format(d * MM_PER_FT),
            _raw_distance_text(el_i, el_j),
            u"точно" if d <= EXACT_DUPLICATE_RADIUS_FT else u"рядом"
        ])

    output.print_table(
        table_data=duplicate_pairs_table,
        columns=[
            u"ID 1", u"1", u"Происхождение 1",
            u"ID 2", u"2", u"Происхождение 2",
            u"Расстояние, мм", u"Расстояние ДО создания, мм", u"Точно/рядом"
        ]
    )

    # Выделяем разом все элементы, участвующие хоть в одной близкой паре —
    # чтобы посмотреть их расположение целиком (Zoom to Fit Selection),
    # а не переходить по ссылкам одну пару за раз.
    dup_selection_ids = List[ElementId]()
    seen_dup_ids = set()
    for el_i, el_j, _d in duplicate_pairs:
        for el in (el_i, el_j):
            if el.Id.IntegerValue not in seen_dup_ids:
                seen_dup_ids.add(el.Id.IntegerValue)
                dup_selection_ids.Add(el.Id)
    try:
        uidoc.Selection.SetElementIds(dup_selection_ids)
    except:
        pass


forms.alert(
    u"Готово.\n\n"
    u"Создано элементов: {}\n"
    u"Пропущено (уже стоял маркер): {}\n"
    u"Пропущено аннотаций стояка (рядом уже отмечено реальное устройство): {}\n\n"
    u"Панелей: {}\n"
    u"Стояков: {}\n"
    u"Узлов маршрута: {}\n\n"
    u"Наибольший кластер (элементов слито в одну точку): {}\n"
    u"Пар маркеров рядом (весь документ, до {:.0f}мм): {}\n"
    u"— из них точных совпадений (до {:.0f}мм, как у Revit): {}\n\n"
    u"{}".format(
        len(created),
        len(skipped),
        riser_annotations_skipped,
        counts_by_category["panel"],
        counts_by_category["riser"],
        counts_by_category["route"],
        largest_cluster_size,
        DUPLICATE_SCAN_RADIUS_MM,
        len(duplicate_pairs),
        EXACT_DUPLICATE_RADIUS_MM,
        len(exact_duplicate_pairs),
        u"Подробности — в окне вывода pyRevit." if (large_clusters or duplicate_pairs) else u""
    )
)
