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
шиной той панели и была бы неотличима от нею. Свой яркий жирный стиль
(TRUNK_COLOR_RGB/TRUNK_LINE_WEIGHT), не цвет какой-то одной панели.
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

# Насколько ниже узлов проходит коллектор первой (index=0) панели —
# то же значение и тот же смысл, что CABLE_DROP_OFFSET_MM у СОТ.
BUS_DROP_OFFSET_MM = 15.0

# Насколько дальше от рамки этажа уходит коллектор каждой следующей
# панели на том же этаже — чтобы коллекторы нескольких панелей не легли
# друг на друга по Y, а стояли параллельно, один под другим.
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
    level_y — первая панель (index=0) на BUS_DROP_OFFSET_MM ниже узлов,
    каждая следующая ещё на BUS_DROP_SPACING_MM дальше (ниже) — так
    коллекторы нескольких панелей на одном этаже идут параллельно, не
    перекрывая друг друга. Чистая функция, без Revit API.
    """
    return level_y - (BUS_DROP_OFFSET_MM + panel_index * BUS_DROP_SPACING_MM) * MM_TO_FT


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


def trunk_link_segments(x_a, y_a, x_b, y_b, lane_x):
    """
    Отрезки магистрали шкаф-шкаф между стояком панели A (X=x_a, высота
    подключения Y=y_a) и стояком панели B (X=x_b, Y=y_b) через отдельную
    дорожку (X=lane_x, см. trunk_lane_x) — не через сами стояки панелей,
    чтобы магистраль не совпадала по X ни с одной из их линий шины:
    короткий горизонтальный переход от стояка A до дорожки, вертикальный
    участок вдоль дорожки (может быть длинным — у панелей на далёких
    друг от друга этажах это и есть настоящая длина магистрали, ничего
    аномального), короткий горизонтальный переход от дорожки до стояка B.

    Возвращает [(x1, y1, x2, y2), ...] — только невырожденные отрезки
    (нулевой длины пропускаются). Чистая функция, без Revit API.
    """
    segments = []
    if x_a != lane_x:
        segments.append((x_a, y_a, lane_x, y_a))
    if y_a != y_b:
        segments.append((lane_x, y_a, lane_x, y_b))
    if lane_x != x_b:
        segments.append((lane_x, y_b, x_b, y_b))
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

    Отростки, коллектор и стояк одной панели красятся в один Line Style
    (авто, по имени панели, см. _line_styles_by_panel) — по цвету видно,
    какое устройство идёт к какому шкафу.

    panels_order — [panel_uid, ...], уже в нужном порядке отрисовки
    (например по имени панели) — определяет и X стояка (panel_riser_x),
    и Y коллектора (panel_collector_y) каждой панели, стабильные между
    запусками, пока порядок панелей не меняется.
    panel_device_uids — {panel_uid: set([device_uid, ...])} — устройства
    этой панели (её собственный uid тоже должен быть в своём множестве,
    чтобы шина дотянулась до самого узла панели на схеме).
    panel_names — {panel_uid: имя панели} — для подписи Line Style.
    old_bus_line_ids — [line_id, ...] из состояния предыдущего запуска.

    Как и у СОТ, эти линии не диффятся — полностью удаляются и рисуются
    заново на каждом запуске (они целиком выводятся из уже посчитанных
    sync_levels позиций узлов, диффить их незачем — см. docstring
    sot_schematic.sync_cable_connections).

    Возвращает (line_ids, riser_info) — line_ids для сохранения в state;
    riser_info — {panel_uid: (riser_x, min_y, max_y)} для панелей, у
    которых реально нарисован хоть один участок шины (в т.ч. панель без
    ни одного обычного устройства — узел только самой панели), нужен
    sync_trunk_links, чтобы вести магистральные линии через уже
    нарисованные стояки, а не отдельной линией напрямую.
    """
    from lowlife.sot_schematic import draw_segment, delete_elements, _iter_state_devices, _node_bottom_y

    delete_elements(doc, old_bus_line_ids)

    all_devices = list(_iter_state_devices(new_state))
    if not all_devices:
        return [], {}

    device_by_uid = dict((uid, (x, y, instance_id)) for uid, x, y, instance_id in all_devices)
    line_style_by_panel = _line_styles_by_panel(doc, panels_order, panel_names)

    new_ids = []
    riser_info = {}

    for index, panel_uid in enumerate(panels_order):
        member_uids = panel_device_uids.get(panel_uid) or set()
        members = [
            (uid, x, y, instance_id)
            for uid, (x, y, instance_id) in device_by_uid.items()
            if uid in member_uids
        ]

        if not members:
            continue

        style = line_style_by_panel.get(panel_uid)
        riser_x = panel_riser_x(index)

        by_level_y = {}
        for uid, x, y, instance_id in members:
            by_level_y.setdefault(y, []).append((x, instance_id))

        collector_ys = []

        for level_y, x_instance_list in by_level_y.items():
            collector_y = panel_collector_y(index, level_y)
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
            riser_info[panel_uid] = (riser_x, min(collector_ys), max(collector_ys))

    return new_ids, riser_info


def sync_trunk_links(doc, view, new_state, old_trunk_line_ids, trunk_links, riser_info, panel_count):
    """
    Магистральная связь шкаф-шкаф (например оптическая линия между двумя
    панелями) ведётся через СВОЮ ОТДЕЛЬНУЮ вертикальную "дорожку" (см.
    trunk_lane_x) — не по X стояка одной из панелей (была так в прошлой
    версии — визуально сливалось с обычной шиной той панели, магистраль
    была неотличима от неё): короткий горизонтальный переход от стояка
    панели A до дорожки, вертикальный участок вдоль дорожки (может быть
    длинным — у панелей на далёких друг от друга этажах это настоящая
    длина магистрали, не баг), короткий горизонтальный переход от дорожки
    до стояка панели B (см. trunk_link_segments). Подключение к каждому
    стояку — по его верхней точке (max_y).

    riser_info — {panel_uid: (riser_x, min_y, max_y)}, из
    sync_panel_buses (второй элемент её возврата) — панель, у которой
    нет записи (шина не нарисована — например panels_order/panel_names
    рассинхронизированы), пропускается.
    panel_count — len(panels_order), для trunk_lane_x (дорожки магистралей
    продолжают ту же последовательность X, что и стояки панелей, поэтому
    нужно знать, сколько стояков панелей уже занято).
    trunk_links — [(panel_uid_a, panel_uid_b), ...] (см.
    scs.collect_target_panel_devices) — порядок определяет, какая
    дорожка (X) достанется какой паре (trunk_lane_x(index, panel_count)),
    стабильно между запусками, пока список магистралей не меняется.
    old_trunk_line_ids — [line_id, ...] из состояния предыдущего запуска.

    Как и шины (sync_panel_buses), эти линии не диффятся — полностью
    удаляются и рисуются заново на каждом запуске.

    Возвращает (line_ids, skipped) — line_ids для сохранения в state;
    skipped — [(panel_uid_a, panel_uid_b, reason), ...] для пар, для
    которых не нарисовано НИ ОДНОГО отрезка (диагностика — почему связь
    из настроек не попала на схему; reason один из "no_riser_a"/
    "no_riser_b"/"draw_failed").
    """
    from lowlife.sot_schematic import draw_segment, delete_elements

    delete_elements(doc, old_trunk_line_ids)

    if not trunk_links:
        return [], []

    style = _get_or_create_line_style(doc, TRUNK_LINE_STYLE_NAME, TRUNK_COLOR_RGB, TRUNK_LINE_WEIGHT)

    new_ids = []
    skipped = []

    for trunk_index, (panel_uid_a, panel_uid_b) in enumerate(trunk_links):
        riser_a = riser_info.get(panel_uid_a)
        riser_b = riser_info.get(panel_uid_b)
        if riser_a is None:
            skipped.append((panel_uid_a, panel_uid_b, "no_riser_a"))
            continue
        if riser_b is None:
            skipped.append((panel_uid_a, panel_uid_b, "no_riser_b"))
            continue

        x_a, _min_y_a, max_y_a = riser_a
        x_b, _min_y_b, max_y_b = riser_b
        lane_x = trunk_lane_x(trunk_index, panel_count)

        pair_ids = []
        for x1, y1, x2, y2 in trunk_link_segments(x_a, max_y_a, x_b, max_y_b, lane_x):
            elem = draw_segment(doc, view, x1, y1, x2, y2)
            if elem is not None:
                pair_ids.append(elem.Id.IntegerValue)
                _set_style(elem, style)

        if pair_ids:
            new_ids.extend(pair_ids)
        else:
            skipped.append((panel_uid_a, panel_uid_b, "draw_failed"))

    return new_ids, skipped
