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


def trunk_jump_geometry(min_y_a, max_y_a, min_y_b, max_y_b):
    """
    Геометрия перехода магистрали шкаф-шкаф между двумя стояками с
    Y-диапазонами [min_y_a, max_y_a] и [min_y_b, max_y_b] (единицы —
    любые, лишь бы одинаковые для обеих панелей и порядок min<=max).
    Чистая функция, без Revit API — можно проверить тестами.

    Возвращает (jump_y, ext_a, ext_b):
    - jump_y — высота горизонтального перехода;
    - ext_a/ext_b — None (стояк и так касается перехода) либо (from_y, to_y)
      — какой отрезок достроить у этого стояка, чтобы он дотянулся до
      jump_y.

    Если диапазоны пересекаются — jump_y на верхней границе пересечения
    (касается обоих стояков напрямую, ext_a=ext_b=None). Если нет —
    jump_y ПОСЕРЕДИНЕ разрыва между диапазонами, и оба стояка достраиваются
    коротким продолжением до неё — а не один стояк на всю длину разрыва
    (у панелей на далёких друг от друга этажах разрыв может быть длиной
    во много этажей, отрезок вышел бы аномально длинным).
    """
    overlap_lo = max(min_y_a, min_y_b)
    overlap_hi = min(max_y_a, max_y_b)

    if overlap_lo <= overlap_hi:
        jump_y = overlap_hi
    else:
        jump_y = (overlap_hi + overlap_lo) / 2.0

    def _extension(min_y, max_y):
        if jump_y > max_y:
            return max_y, jump_y
        if jump_y < min_y:
            return min_y, jump_y
        return None

    return jump_y, _extension(min_y_a, max_y_a), _extension(min_y_b, max_y_b)


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


def sync_trunk_links(doc, view, new_state, old_trunk_line_ids, trunk_links, riser_info):
    """
    Магистральная связь шкаф-шкаф (например оптическая линия между двумя
    панелями) ведётся через уже нарисованные стояки этих панелей
    (riser_info из sync_panel_buses), а не прямой линией напрямую через
    рамки помещений — так магистраль визуально идёт по тому же "коридору
    стояков" слева от схемы, что и обычные шины, а не пересекает её
    насквозь по диагонали:

    - горизонтальный "переход" между стояком панели A (X = riser_a) и
      стояком панели B (X = riser_b) на высоте jump_y;
    - если Y-диапазоны стояков пересекаются — jump_y на верхней границе
      пересечения (касается обоих стояков напрямую, без достройки);
    - если не пересекаются вовсе (например, у панелей нет общих этажей —
      это НЕ редкий случай, магистраль шкаф-шкаф как раз обычно связывает
      далёкие друг от друга этажи) — jump_y ПОСЕРЕДИНЕ разрыва между
      диапазонами, и оба стояка достраиваются коротким продолжением до
      неё (не один стояк на всю длину разрыва — иначе при далёких друг
      от друга этажах получался бы один аномально длинный отрезок вместо
      короткого заметного перехода).

    riser_info — {panel_uid: (riser_x, min_y, max_y)}, из
    sync_panel_buses (второй элемент её возврата) — панель, у которой
    нет записи (шина не нарисована — например panels_order/panel_names
    рассинхронизированы), пропускается.
    trunk_links — [(panel_uid_a, panel_uid_b), ...] (см.
    scs.collect_target_panel_devices).
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

    def _draw_extension(x, ext, out_ids):
        if ext is None:
            return
        from_y, to_y = ext
        elem = draw_segment(doc, view, x, from_y, x, to_y)
        if elem is not None:
            out_ids.append(elem.Id.IntegerValue)
            _set_style(elem, style)

    new_ids = []
    skipped = []

    for panel_uid_a, panel_uid_b in trunk_links:
        riser_a = riser_info.get(panel_uid_a)
        riser_b = riser_info.get(panel_uid_b)
        if riser_a is None:
            skipped.append((panel_uid_a, panel_uid_b, "no_riser_a"))
            continue
        if riser_b is None:
            skipped.append((panel_uid_a, panel_uid_b, "no_riser_b"))
            continue

        x_a, min_y_a, max_y_a = riser_a
        x_b, min_y_b, max_y_b = riser_b
        jump_y, ext_a, ext_b = trunk_jump_geometry(min_y_a, max_y_a, min_y_b, max_y_b)

        pair_ids = []

        elem = draw_segment(doc, view, x_a, jump_y, x_b, jump_y)
        if elem is not None:
            pair_ids.append(elem.Id.IntegerValue)
            _set_style(elem, style)

        _draw_extension(x_a, ext_a, pair_ids)
        _draw_extension(x_b, ext_b, pair_ids)

        if pair_ids:
            new_ids.extend(pair_ids)
        else:
            skipped.append((panel_uid_a, panel_uid_b, "draw_failed"))

    return new_ids, skipped
