# -*- coding: utf-8 -*-
"""
Логика кнопки BuildScsSchematic ("Структурная схема СКС").

Раскладка устройств по этажам/помещениям, сами схемные семейства и марки,
инкрементальное обновление вида между запусками — всё это уже есть в
lib/lowlife/sot_schematic.py (написано для СОТ, но ничем не привязано к
дисциплине: category_symbols/category_for_device — просто параметры) и
переиспользуется здесь напрямую, без копирования: sync_levels,
sync_rooms_in_level, draw_segment, delete_elements, _iter_state_devices,
_node_bottom_y и т.д. Уровни (sot_levels.py) и хранение раскладки
(sot_layout_state.py) — тоже полностью общие модули, тоже импортируются
как есть.

Чего нет у СОТ и что нужно СКС — несколько панелей (шкафов/патч-панелей)
на одной схеме, каждая своей независимой шиной: на каждом этаже у каждой
панели, у которой есть на нём устройство, — своя горизонтальная линия
коллектора (только её собственные устройства-отростки), дотянутая до её
собственного стояка. Линии разных панелей на одном этаже разнесены по Y
(следующая панель — дальше от рамки этажа, см. panel_collector_y), чтобы
не накладывались друг на друга. Стояк каждой панели — своя отдельная
вертикальная линия слева от рамок (см. panel_riser_x), тянется по Y
только через те этажи, где у панели реально есть устройства.

И отростки, и коллектор, и стояк одной панели красятся в один и тот же
Line Style (создаётся/переиспользуется автоматически по имени панели,
без настроек) — по цвету видно, какое устройство идёт к какому шкафу,
даже если линии разных панелей визуально пересекаются на схеме.

Магистральные связи шкаф-шкаф (sync_trunk_links) — по СВОЕЙ отдельной
вертикальной "дорожке" (trunk_lane_x, продолжение той же
последовательности X, что и стояки панелей — panel_riser_x), не по X
одного из стояков: иначе магистраль визуально совпадала бы с обычной
шиной той панели и была бы неотличима от неё. Свой яркий жирный стиль
(TRUNK_COLOR_RGB/TRUNK_LINE_WEIGHT), не цвет какой-то одной панели.

У самого шкафа магистраль отходит не от его шины устройств (переход
начинался бы ровно в верхней точке стояка шины и читался бы как
"продолжение" той же линии), а от СОБСТВЕННОГО узла шкафа — своим
отдельным отводом, на видимом расстоянии от вертикального отростка
шины устройств (см. TRUNK_STUB_OFFSET_MM), вниз до своей строки
(глубже шины устройств любой панели этого этажа — trunk_drop_y) и
дальше горизонтально до дорожки.

Если магистральных связей несколько и они образуют ЦЕПОЧКУ (шкаф A —
шкаф B — шкаф C, две связи через общий шкаф B), у всей цепочки —
ОДНА общая дорожка (group_trunk_components), а не отдельная дорожка на
каждую пару связей: иначе дорожки соседних пар (разница в X всего
RISER_SPACING_MM) стояли бы почти вплотную друг к другу и визуально
сливались в подобие "коробки" вместо одной понятной линии. Каждый шкаф
цепочки просто подключается к этой общей дорожке своим отдельным
коротким горизонтальным отводом (trunk_component_segments).
"""

# lowlife.sot_schematic импортирует Autodesk.Revit.DB на уровне модуля —
# импортируем его функции (и Revit-специфичные тут же, при необходимости)
# ЛЕНИВО, внутри функций, а не здесь наверху (тот же приём, что и в
# scs.py:get_workset_name), чтобы panel_riser_x/panel_collector_y (чистые
# функции, без Revit API) можно было тестировать вне Revit — см.
# tests/test_scs_schematic.py.
import colorsys

MM_TO_FT = 1.0 / 304.8

# X первого (index=0) стояка — рядом с самой левой линией рамки этажа
# (LEVEL_LINE_1_OFFSET_MM = 5мм у СОТ; свой стояк у единственного шкафа
# СОТ ставится ровно туда же — CABLE_RISER_OFFSET_MM). У СКС стояков
# может быть несколько — расставляем их вплотную друг к другу, ВНУТРИ
# ширины, которую и так уже занимают три левые линии рамки (35мм), а не
# дальше них: иначе стояк оказывается физически за пределами уже
# нарисованной рамки этажа.
RISER_BASE_OFFSET_MM = 5.0

# Расстояние между стояками разных панелей (в плане, по X) — чтобы стояки
# нескольких панелей на одной схеме не накладывались друг на друга и не
# сливались визуально, но не создавали пустой разрыв: масштаб — как у
# самой схемы (шаг между устройствами STEP_MM=20мм у СОТ), а не как у
# первой версии этой функции (300мм — оказалось на порядок больше
# масштаба схемы, коллектор до дальнего стояка тянулся через пустоту).
RISER_SPACING_MM = 8.0

# Отступ от границы: и сверху (насколько ниже узлов проходит коллектор
# первой, index=0, панели), и снизу (насколько глубже самой нижней линии
# кабеля должна быть нижняя граница рамки этажа) — одно и то же число по
# требованию пользователя ("между линией и границей этажа или стояка
# 8мм"), не два разных подобранных на глаз значения.
BOUNDARY_MARGIN_MM = 8.0

# Насколько дальше от рамки этажа уходит каждая следующая линия кабеля
# на том же этаже относительно предыдущей — между ЛЮБЫМИ двумя соседними
# линиями кабелей, не только коллекторами шин устройств: магистральный
# отвод (trunk_drop_y) — это просто ещё одна такая линия, ровно на этот
# же шаг дальше последней шины устройств, без отдельного увеличенного
# зазора (был — визуально давал не 4, а 10мм, пользователь явно попросил
# без него).
BUS_DROP_SPACING_MM = 4.0

# Насыщенность/яркость автогенерируемых цветов панелей (HSV) — хорошо
# различимые, не слишком тёмные и не белёсые цвета на тёмном/светлом
# фоне листа. Оттенок (H) берётся равномерно по кругу, по числу панелей.
_PANEL_COLOR_SATURATION = 0.75
_PANEL_COLOR_VALUE = 0.85

_LINE_STYLE_PREFIX = u"СКС схема — "

# Магистральные линии шкаф-шкаф (например оптическая связь между
# панелями) рисуются отдельно от обычных шин розеток — не участвуют в
# автогенерации цвета по panel_color_rgb (не связаны с конкретной
# "одной" панелью — соединяют две), поэтому у них один общий,
# фиксированный стиль/цвет: яркий и контрастный (не серый — серый на
# сложной чёрно-белой схеме, среди рамок и текста, легко теряется на
# глаз), да ещё и жирный (TRUNK_LINE_WEIGHT), чтобы точно не потерялась
# среди обычных тонких линий шины.
TRUNK_LINE_STYLE_NAME = _LINE_STYLE_PREFIX + u"Магистраль"
TRUNK_COLOR_RGB = (230, 20, 20)
TRUNK_LINE_WEIGHT = 6

# Зазор между стояком последней панели и первой дорожкой магистрали —
# заметно больше RISER_SPACING_MM (обычного шага МЕЖДУ стояками панелей
# или между дорожками разных магистралей): дорожка магистрали не должна
# стоять вплотную к стоякам панелей, иначе переход к ней выглядит как
# маленький отросток у стояка, а не как отдельная линия.
TRUNK_LANE_GAP_MM = 20.0

# Магистральная линия у самого шкафа отходит не от его обычной шины
# устройств (было так раньше — переход к дорожке начинался ровно в
# верхней точке стояка шины, визуально читалось как "продолжение" той
# же линии, а не отдельная связь), а от СВОЕГО отдельного отвода: узел
# шкафа -> вниз до собственной строки магистрали (ниже строк всех шин
# устройств этого этажа, см. trunk_drop_y) -> горизонтально до дорожки
# (trunk_lane_x). TRUNK_STUB_OFFSET_MM — на сколько этот отвод сдвинут
# по X от самого узла шкафа (и, значит, от его вертикального отростка
# к шине устройств, который идёт от той же точки, но строго по X узла)
# — небольшой сдвиг, чтобы отвод не лёг на ту же вертикаль и не слился
# с ней, а был на видимом расстоянии, как и просили.
TRUNK_STUB_OFFSET_MM = 3.0


def panel_riser_x(panel_index):
    """
    X стояка панели с данным порядковым номером (0, 1, 2...) — левее рамок
    помещений, панели расставлены по возрастанию номера слева направо от
    рамок (первая — ближе всего, на RISER_BASE_OFFSET_MM). Чистая
    функция, без Revit API.
    """
    return -(RISER_BASE_OFFSET_MM + panel_index * RISER_SPACING_MM) * MM_TO_FT


def panel_collector_y(panel_index, level_y):
    """
    Y горизонтального коллектора панели с этим номером на этаже с данным
    level_y — первая панель (index=0) на BOUNDARY_MARGIN_MM ниже узлов,
    каждая следующая ещё на BUS_DROP_SPACING_MM дальше (ниже) — так
    коллекторы нескольких панелей на одном этаже идут параллельно, не
    перекрывая друг друга. Чистая функция, без Revit API.
    """
    return level_y - (BOUNDARY_MARGIN_MM + panel_index * BUS_DROP_SPACING_MM) * MM_TO_FT


def trunk_drop_y(panel_count, level_y):
    """
    Y строки магистрального отвода конкретного шкафа на этаже с этим
    level_y — на panel_count-й "виртуальной" позиции panel_collector_y
    (сразу за последним реальным индексом панели — 0..panel_count-1) —
    ровно на один шаг BUS_DROP_SPACING_MM дальше от этажа, чем строка
    шины устройств ЛЮБОЙ панели схемы, БЕЗ дополнительного зазора сверх
    этого — магистральный отвод для расстановки такая же линия кабеля,
    как и любая другая (между всеми линиями кабелей на этаже — ровно
    BUS_DROP_SPACING_MM, без исключений). panel_count берётся по всей
    схеме, не по конкретному этажу — чтобы отвод не столкнулся с чужой
    шиной, даже если панелей с бОльшим индексом на этом конкретном этаже
    нет. Чистая функция, без Revit API.
    """
    return panel_collector_y(panel_count, level_y)


def trunk_lane_x(trunk_index, panel_count):
    """
    X отдельной вертикальной "дорожки" магистрали с этим порядковым
    номером (0, 1, 2...) — левее ВСЕХ стояков панелей, с заметным
    зазором (TRUNK_LANE_GAP_MM) после последнего из них — не вплотную,
    как было раньше (сразу за panel_riser_x(panel_count-1), тем же
    шагом RISER_SPACING_MM, что и между стояками панелей): переход к
    такой дорожке выглядел как маленький отросток у стояка панели, а не
    как заметная отдельная линия. Между собой дорожки разных магистралей
    по-прежнему расставлены с шагом RISER_SPACING_MM. Чистая функция,
    без Revit API.
    """
    last_panel_x = panel_riser_x(panel_count - 1) if panel_count > 0 else 0.0
    return last_panel_x - (TRUNK_LANE_GAP_MM + trunk_index * RISER_SPACING_MM) * MM_TO_FT


def group_trunk_components(trunk_links):
    """
    Группирует пары магистральных связей [(a, b), ...] в связные цепочки
    (шкаф A - шкаф B - шкаф C через две связи с общим шкафом B — одна
    цепочка из трёх шкафов, а не две отдельные пары) — union-find по
    парам. Порядок компонентов и узлов внутри — по первому появлению во
    входном списке (детерминированно между запусками, пока сам список
    trunk_links не меняется). Чистая функция, без Revit API.

    Возвращает [[panel_uid, ...], ...] — по одному списку узлов на
    компонент, каждый узел встречается только в одном компоненте.
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    order = []
    seen = set()
    for a, b in trunk_links:
        union(a, b)
        for node in (a, b):
            if node not in seen:
                seen.add(node)
                order.append(node)

    components_by_root = {}
    for node in order:
        root = find(node)
        components_by_root.setdefault(root, []).append(node)

    return list(components_by_root.values())


def trunk_component_segments(member_points, lane_x):
    """
    Отрезки магистрали для одной цепочки шкафов, подключённой к одной
    общей дорожке (X=lane_x, см. trunk_lane_x, group_trunk_components):
    у каждого шкафа цепочки — свой короткий горизонтальный отвод от его
    стояка (X=x, Y=y — высота подключения) до дорожки; сама дорожка —
    ОДИН вертикальный участок от самого нижнего до самого верхнего
    отвода цепочки (не по отдельному куску на каждую пару связей — иначе
    при цепочке из 3+ шкафов на одной дорожке появлялись бы наложенные
    друг на друга отрезки).

    member_points — [(x, y), ...] — стояк (X) и высота подключения (Y)
    каждого шкафа цепочки, в любом порядке.

    Возвращает [(x1, y1, x2, y2), ...] — только невырожденные отрезки
    (нулевой длины пропускаются). Чистая функция, без Revit API.
    """
    segments = []

    for x, y in member_points:
        if x != lane_x:
            segments.append((x, y, lane_x, y))

    if len(member_points) >= 2:
        ys = [y for _x, y in member_points]
        y_min, y_max = min(ys), max(ys)
        if y_min != y_max:
            segments.append((lane_x, y_min, lane_x, y_max))

    return segments


def panel_color_rgb(panel_index, panel_count):
    """
    (r, g, b) 0-255 для панели с этим порядковым номером — равномерно
    по кругу HSV, чтобы соседние по индексу панели тоже не были похожи
    по цвету (не просто плавный градиент). Чистая функция, без Revit API.
    """
    if panel_count <= 0:
        panel_count = 1
    hue = (panel_index / float(panel_count)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, _PANEL_COLOR_SATURATION, _PANEL_COLOR_VALUE)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def _get_or_create_line_style(doc, name, rgb, weight=None):
    """
    Line Style (подкатегория категории «Линии») с этим именем — если уже
    существует (например, с прошлого запуска), просто переиспользуется
    и обновляется цвет (и толщина, если weight задан); если нет —
    создаётся. Возвращает GraphicsStyle для присвоения
    DetailCurve.LineStyle, либо None при любой ошибке API (тогда линия
    останется цвета по умолчанию — не критично для работы кнопки, только
    для наглядности).

    weight (1-16, см. Category.SetLineWeight) — задаётся только для
    магистралей шкаф-шкаф (TRUNK_LINE_WEIGHT), чтобы жирная линия точно
    не терялась на глаз среди обычных тонких линий шины; для линий
    отдельной панели не задаётся (weight=None — толщина по умолчанию).
    """
    from Autodesk.Revit.DB import BuiltInCategory, Color, GraphicsStyleType

    try:
        categories = doc.Settings.Categories
        lines_category = categories.get_Item(BuiltInCategory.OST_Lines)

        subcategory = None
        for sub in lines_category.SubCategories:
            if sub.Name == name:
                subcategory = sub
                break

        if subcategory is None:
            subcategory = categories.NewSubcategory(lines_category, name)

        r, g, b = rgb
        try:
            subcategory.LineColor = Color(r, g, b)
        except:
            pass

        if weight is not None:
            try:
                subcategory.SetLineWeight(weight, GraphicsStyleType.Projection)
            except:
                pass

        return subcategory.GetGraphicsStyle(GraphicsStyleType.Projection)
    except:
        return None


def _line_styles_by_panel(doc, panels_order, panel_names):
    """{panel_uid: GraphicsStyle|None} — по одному Line Style на панель,
    имя — "СКС схема — <имя панели>" (или сам uid, если имя не нашлось)."""
    count = len(panels_order)
    styles = {}

    for index, panel_uid in enumerate(panels_order):
        label = panel_names.get(panel_uid) or panel_uid
        style_name = _LINE_STYLE_PREFIX + label
        rgb = panel_color_rgb(index, count)
        styles[panel_uid] = _get_or_create_line_style(doc, style_name, rgb)

    return styles


def _set_style(elem, style):
    if elem is None or style is None:
        return
    try:
        elem.LineStyle = style
    except:
        pass


def sync_panel_buses(doc, view, new_state, old_bus_line_ids, panels_order,
                      panel_device_uids, panel_names):
    """
    Рисует по одной независимой, цветной шине на каждую панель: свой
    горизонтальный коллектор на каждом этаже, где у панели есть
    устройство (только её собственные устройства-отростки — не общий с
    другими панелями), свой стояк через все её этажи. Коллекторы разных
    панелей на одном этаже стоят на разной высоте (panel_collector_y) —
    параллельно, не перекрываясь; стояки разных панелей — на разных X
    (panel_riser_x), тоже параллельно.

    Y коллектора считается по ЛОКАЛЬНОМУ индексу панели — её позиции
    среди панелей, реально присутствующих именно на этом этаже (не по
    её глобальному номеру во всей схеме panels_order) — иначе на этаже,
    где у какой-то панели с меньшим номером устройств нет, между
    реально нарисованными коллекторами появлялся бы разрыв в несколько
    BUS_DROP_SPACING_MM вместо одного (номер пропущенной панели всё
    равно "съедал" бы своё место). X стояка (panel_riser_x) и цвет,
    наоборот, — по ГЛОБАЛЬНОМУ индексу, не зависят от этажа.

    Отростки, коллектор и стояк одной панели красятся в один Line Style
    (авто, по имени панели, см. _line_styles_by_panel) — по цвету видно,
    какое устройство идёт к какому шкафу.

    panels_order — [panel_uid, ...], уже в нужном порядке отрисовки
    (например по имени панели) — определяет X стояка (panel_riser_x) и
    цвет каждой панели, стабильные между запусками, пока порядок
    панелей не меняется.
    panel_device_uids — {panel_uid: set([device_uid, ...])} — устройства
    этой панели (её собственный uid тоже должен быть в своём множестве,
    чтобы шина дотянулась до самого узла панели на схеме).
    panel_names — {panel_uid: имя панели} — для подписи Line Style.
    old_bus_line_ids — [line_id, ...] из состояния предыдущего запуска.

    Как и у СОТ, эти линии не диффятся — полностью удаляются и рисуются
    заново на каждом запуске (они целиком выводятся из уже посчитанных
    sync_levels позиций узлов, диффить их незачем — см. docstring
    sot_schematic.sync_cable_connections).

    Возвращает (line_ids, panel_anchors) — line_ids для сохранения в
    state; panel_anchors — {panel_uid: (panel_x, panel_level_y,
    panel_drop_top_y)} для панелей, у которых реально нарисован хоть
    один участок шины (в т.ч. панель без ни одного обычного устройства
    — узел только самой панели) И которые сами найдены как узел на
    схеме — panel_x/panel_drop_top_y — X и Y нижней границы УГО самого
    узла панели (см. _node_bottom_y), panel_level_y — Y этажа, на
    котором панель размещена; нужен sync_trunk_links, чтобы вести
    магистральные линии от СОБСТВЕННОГО узла панели, а не через её шину
    устройств (шина и магистраль не должны визуально сливаться/
    восприниматься как продолжение друг друга).
    """
    from lowlife.sot_schematic import draw_segment, delete_elements, _iter_state_devices, _node_bottom_y

    delete_elements(doc, old_bus_line_ids)

    all_devices = list(_iter_state_devices(new_state))
    if not all_devices:
        return [], {}

    device_by_uid = dict((uid, (x, y, instance_id)) for uid, x, y, instance_id in all_devices)
    line_style_by_panel = _line_styles_by_panel(doc, panels_order, panel_names)

    # Собственный член (устройство/сама панель) каждой панели, сгруппированный
    # по этажу — сначала по всем панелям, чтобы узнать, СКОЛЬКО и КАКИХ
    # панелей реально присутствует на каждом конкретном этаже. Без этого
    # collector_y считался бы по ГЛОБАЛЬНОМУ индексу панели (её порядковому
    # номеру во всей схеме), и на этаже, где панелей с меньшим индексом нет,
    # между реально нарисованными коллекторами появлялся бы разрыв в
    # несколько BUS_DROP_SPACING_MM вместо одного — коллекторы у панели с
    # индексом, скажем, 0 и 2 (без панели 1 на этом этаже) встали бы через
    # 8мм, а не 4мм. Локальный индекс — позиция панели среди панелей,
    # реально присутствующих именно на этом этаже (в том же порядке, что
    # panels_order) — коллекторы на каждом этаже всегда идут подряд, без
    # пропусков. Riser_x и цвет панели по-прежнему берутся по ГЛОБАЛЬНОМУ
    # индексу — не меняются от этажа к этажу.
    panel_members = {}
    floor_panel_order = {}

    for panel_uid in panels_order:
        member_uids = panel_device_uids.get(panel_uid) or set()
        members = [
            (uid, x, y, instance_id)
            for uid, (x, y, instance_id) in device_by_uid.items()
            if uid in member_uids
        ]
        if not members:
            continue
        panel_members[panel_uid] = members
        for level_y in set(y for _uid, _x, y, _iid in members):
            floor_panel_order.setdefault(level_y, []).append(panel_uid)

    new_ids = []
    panel_anchors = {}

    for index, panel_uid in enumerate(panels_order):
        members = panel_members.get(panel_uid)
        if not members:
            continue

        style = line_style_by_panel.get(panel_uid)
        riser_x = panel_riser_x(index)

        by_level_y = {}
        for uid, x, y, instance_id in members:
            by_level_y.setdefault(y, []).append((x, instance_id))

        collector_ys = []

        for level_y, x_instance_list in by_level_y.items():
            local_index = floor_panel_order[level_y].index(panel_uid)
            collector_y = panel_collector_y(local_index, level_y)
            collector_ys.append(collector_y)

            xs = [x for x, _iid in x_instance_list] + [riser_x]

            elem = draw_segment(doc, view, min(xs), collector_y, max(xs), collector_y)
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)
                _set_style(elem, style)

            for x, instance_id in x_instance_list:
                drop_top_y = _node_bottom_y(doc, view, instance_id, level_y)
                elem = draw_segment(doc, view, x, drop_top_y, x, collector_y)
                if elem is not None:
                    new_ids.append(elem.Id.IntegerValue)
                    _set_style(elem, style)

        if collector_ys:
            elem = draw_segment(doc, view, riser_x, min(collector_ys), riser_x, max(collector_ys))
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)
                _set_style(elem, style)

            panel_self = device_by_uid.get(panel_uid)
            if panel_self is not None:
                panel_x, panel_level_y, panel_instance_id = panel_self
                panel_drop_top_y = _node_bottom_y(doc, view, panel_instance_id, panel_level_y)
                panel_anchors[panel_uid] = (panel_x, panel_level_y, panel_drop_top_y)

    return new_ids, panel_anchors


def sync_trunk_links(doc, view, new_state, old_trunk_line_ids, trunk_links, panel_anchors, panel_count):
    """
    Магистральные связи шкаф-шкаф (например оптическая линия между
    шкафами) отходят от СОБСТВЕННОГО узла каждого шкафа (panel_anchors),
    а не от его шины устройств (была так раньше — переход начинался
    ровно в верхней точке стояка шины, читалось как "продолжение" той
    же линии, а не отдельная связь): от узла шкафа — короткий отвод "на
    расстоянии" от вертикального отростка шины устройств (тот идёт от
    той же точки узла, но строго по её X — см. TRUNK_STUB_OFFSET_MM) вниз
    до СВОЕЙ строки (глубже последней строки шины устройств этого этажа
    — trunk_drop_y), дальше горизонтально до общей дорожки цепочки (см.
    trunk_lane_x), дальше вертикально вдоль дорожки.

    Связи, образующие ЦЕПОЧКУ (шкаф A - шкаф B - шкаф C через две связи с
    общим шкафом B), группируются в одну цепочку с ОДНОЙ общей дорожкой
    на всех (group_trunk_components) — не отдельная дорожка на каждую
    пару связей: иначе дорожки соседних пар стояли бы почти вплотную
    друг к другу (шаг RISER_SPACING_MM) и визуально сливались в подобие
    "коробки" вместо одной понятной линии (см. trunk_component_segments).

    panel_anchors — {panel_uid: (panel_x, panel_level_y,
    panel_drop_top_y)}, из sync_panel_buses (второй элемент её
    возврата) — панель, у которой нет записи (не размещена на схеме
    как узел), из цепочки исключается (для неё просто не рисуется
    отвод, остальные члены цепочки это не затрагивает).
    panel_count — len(panels_order), для trunk_lane_x (дорожки магистралей
    продолжают ту же последовательность X, что и стояки панелей, поэтому
    нужно знать, сколько стояков панелей уже занято).
    trunk_links — [(panel_uid_a, panel_uid_b), ...] (см.
    scs.collect_target_panel_devices) — порядок определяет и группировку
    в цепочки, и то, какая дорожка (X) достанется какой цепочке
    (trunk_lane_x(component_index, panel_count)), стабильно между
    запусками, пока список магистралей не меняется.
    old_trunk_line_ids — [line_id, ...] из состояния предыдущего запуска.

    Как и шины (sync_panel_buses), эти линии не диффятся — полностью
    удаляются и рисуются заново на каждом запуске.

    Возвращает (line_ids, skipped) — line_ids для сохранения в state;
    skipped — [(panel_uid_a, panel_uid_b, reason), ...] для исходных пар
    trunk_links, у которых хотя бы одна панель не размещена на схеме
    (диагностика — почему связь из настроек не попала на схему; reason
    один из "no_riser_a"/"no_riser_b").
    """
    from lowlife.sot_schematic import draw_segment, delete_elements

    delete_elements(doc, old_trunk_line_ids)

    if not trunk_links:
        return [], []

    style = _get_or_create_line_style(doc, TRUNK_LINE_STYLE_NAME, TRUNK_COLOR_RGB, TRUNK_LINE_WEIGHT)

    skipped = []
    for panel_uid_a, panel_uid_b in trunk_links:
        if panel_anchors.get(panel_uid_a) is None:
            skipped.append((panel_uid_a, panel_uid_b, "no_riser_a"))
        elif panel_anchors.get(panel_uid_b) is None:
            skipped.append((panel_uid_a, panel_uid_b, "no_riser_b"))

    new_ids = []

    for component_index, member_uids in enumerate(group_trunk_components(trunk_links)):
        lane_x = trunk_lane_x(component_index, panel_count)

        member_points = []
        for panel_uid in member_uids:
            anchor = panel_anchors.get(panel_uid)
            if anchor is None:
                continue

            panel_x, panel_level_y, panel_drop_top_y = anchor
            stub_x = panel_x - TRUNK_STUB_OFFSET_MM * MM_TO_FT
            drop_y = trunk_drop_y(panel_count, panel_level_y)

            # Отвод "на расстоянии" от узла шкафа: своя вертикаль
            # (X=stub_x, сдвинут от X узла) от границы УГО шкафа вниз до
            # своей строки — не касается вертикального отростка шины
            # устройств того же шкафа (тот идёт от той же точки узла, но
            # строго по X узла, без сдвига).
            elem = draw_segment(doc, view, stub_x, panel_drop_top_y, stub_x, drop_y)
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)
                _set_style(elem, style)

            member_points.append((stub_x, drop_y))

        for x1, y1, x2, y2 in trunk_component_segments(member_points, lane_x):
            elem = draw_segment(doc, view, x1, y1, x2, y2)
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)
                _set_style(elem, style)

    return new_ids, skipped
