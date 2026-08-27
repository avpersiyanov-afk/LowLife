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
BUS_DROP_SPACING_MM = 8.0

# Насыщенность/яркость автогенерируемых цветов панелей (HSV) — хорошо
# различимые, не слишком тёмные и не белёсые цвета на тёмном/светлом
# фоне листа. Оттенок (H) берётся равномерно по кругу, по числу панелей.
_PANEL_COLOR_SATURATION = 0.75
_PANEL_COLOR_VALUE = 0.85

_LINE_STYLE_PREFIX = u"СКС схема — "


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


def _get_or_create_line_style(doc, name, rgb):
    """
    Line Style (подкатегория категории «Линии») с этим именем — если уже
    существует (например, с прошлого запуска), просто переиспользуется
    и обновляется цвет; если нет — создаётся. Возвращает GraphicsStyle
    для присвоения DetailCurve.LineStyle, либо None при любой ошибке API
    (тогда линия останется цвета по умолчанию — не критично для работы
    кнопки, только для наглядности).
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

    Возвращает [line_id, ...] для сохранения в state.
    """
    from lowlife.sot_schematic import draw_segment, delete_elements, _iter_state_devices, _node_bottom_y

    delete_elements(doc, old_bus_line_ids)

    all_devices = list(_iter_state_devices(new_state))
    if not all_devices:
        return []

    device_by_uid = dict((uid, (x, y, instance_id)) for uid, x, y, instance_id in all_devices)
    line_style_by_panel = _line_styles_by_panel(doc, panels_order, panel_names)

    new_ids = []

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

    return new_ids
