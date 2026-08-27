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
на одной схеме. Топология НЕ "N независимых шин" (была так в первой
версии) — по требованию пользователя: на каждом этаже один ОБЩИЙ
горизонтальный коллектор, к которому отростками собираются ВСЕ
устройства этажа, независимо от того, к какой панели они идут (это
имитирует физику — на этаже кабели разных панелей часто идут в одном
лотке). Расходятся линии только в стояке — слева от рамок помещений,
по одной отдельной вертикальной линии на каждую панель. Коллектор
конкретного этажа дотягивается по X только до тех стояковых линий,
чьи панели реально имеют устройство на этом этаже — поэтому этаж с
одной панелью визуально даёт один отрезок до одного стояка, а этаж с
двумя панелями — коллектор, дотянутый сразу до двух стояковых линий.

Раз коллектор общий, отросток одного устройства визуально не отличить
от отростка другого без доп. признака — поэтому отростки (устройство ->
коллектор) и стояк каждой панели красятся в свой цвет (свой Line Style,
создаётся/переиспользуется автоматически по имени панели, без настроек)
— один и тот же цвет у отростка и у стояка одной панели позволяет
проследить конкретное устройство до конкретного шкафа глазами, даже
через общий коллектор. Сам коллектор остаётся нейтральным (без
переопределения цвета) — он не принадлежит одной панели.
"""

# lowlife.sot_schematic импортирует Autodesk.Revit.DB на уровне модуля —
# импортируем его функции (и Revit-специфичные тут же, при необходимости)
# ЛЕНИВО, внутри функций, а не здесь наверху (тот же приём, что и в
# scs.py:get_workset_name), чтобы panel_riser_x (чистая функция, без
# Revit API) можно было тестировать вне Revit — см.
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

# Насколько ниже узлов проходит общий горизонтальный коллектор этажа —
# то же значение и тот же смысл, что CABLE_DROP_OFFSET_MM у СОТ.
BUS_DROP_OFFSET_MM = 15.0

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
    функция, без Revit API — можно проверить тестами отдельно от
    геометрии сборки шины.
    """
    return -(RISER_BASE_OFFSET_MM + panel_index * RISER_SPACING_MM) * MM_TO_FT


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


def sync_shared_bus(doc, view, new_state, old_bus_line_ids, panels_order,
                     panel_device_uids, panel_names, drop_offset_mm=BUS_DROP_OFFSET_MM):
    """
    Рисует общую шину: один горизонтальный коллектор на этаж (все
    устройства этажа — общие отростки на одну линию) + по одной отдельной
    вертикальной линии-стояку на каждую панель (свой X — panel_riser_x).
    Коллектор этажа дотягивается по X до стояка каждой панели, у которой
    есть хоть одно устройство на этом этаже — так что этаж с одной
    панелью визуально даёт один отрезок до одного стояка, а этаж с
    несколькими панелями — коллектор, дотянутый сразу до нескольких
    стояковых линий. Стояк каждой панели, в свою очередь, тянется по Y
    только через те этажи, где у неё реально есть устройства.

    Отростки (устройство -> коллектор) и стояк каждой панели красятся в
    свой Line Style (авто, по имени панели, см. _line_styles_by_panel) —
    коллектор остаётся нейтральным, он общий для всех панелей.

    panels_order — [panel_uid, ...], уже в нужном порядке отрисовки
    (например по имени панели) — определяет X стояка каждой панели
    (panel_riser_x(index)), стабильный между запусками, пока порядок
    панелей не меняется.
    panel_device_uids — {panel_uid: set([device_uid, ...])} — устройства
    этой панели (её собственный uid тоже должен быть в своём множестве,
    чтобы стояк дотянулся до самого узла панели на схеме).
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

    # uid -> множество панелей, которым принадлежит устройство (обычно
    # ровно одна — но защищаемся от совпадения на случай, если одно и то
    # же устройство почему-то попало в цепи двух панелей).
    panels_by_device_uid = {}
    for panel_uid, member_uids in panel_device_uids.items():
        for uid in member_uids:
            panels_by_device_uid.setdefault(uid, set()).add(panel_uid)

    riser_x_by_panel = dict((panel_uid, panel_riser_x(i)) for i, panel_uid in enumerate(panels_order))
    line_style_by_panel = _line_styles_by_panel(doc, panels_order, panel_names)

    def _panel_for_device(uid):
        panels = panels_by_device_uid.get(uid)
        if not panels:
            return None
        return sorted(panels)[0]

    drop_offset = drop_offset_mm * MM_TO_FT

    by_level_y = {}
    for uid, x, y, instance_id in all_devices:
        by_level_y.setdefault(y, []).append((uid, x, instance_id))

    new_ids = []
    riser_collector_ys = dict((panel_uid, []) for panel_uid in panels_order)

    for level_y, entries in by_level_y.items():
        collector_y = level_y - drop_offset

        panels_on_floor = set()
        for uid, _x, _iid in entries:
            panels_on_floor |= panels_by_device_uid.get(uid, set())

        riser_xs_needed = [riser_x_by_panel[p] for p in panels_on_floor if p in riser_x_by_panel]
        xs = [x for _uid, x, _iid in entries] + riser_xs_needed

        if not xs:
            continue

        elem = draw_segment(doc, view, min(xs), collector_y, max(xs), collector_y)
        if elem is not None:
            new_ids.append(elem.Id.IntegerValue)

        for uid, x, instance_id in entries:
            drop_top_y = _node_bottom_y(doc, view, instance_id, level_y)
            elem = draw_segment(doc, view, x, drop_top_y, x, collector_y)
            if elem is not None:
                new_ids.append(elem.Id.IntegerValue)
                style = line_style_by_panel.get(_panel_for_device(uid))
                if style is not None:
                    try:
                        elem.LineStyle = style
                    except:
                        pass

        for p in panels_on_floor:
            if p in riser_collector_ys:
                riser_collector_ys[p].append(collector_y)

    for panel_uid in panels_order:
        ys = riser_collector_ys.get(panel_uid) or []
        if not ys:
            continue
        riser_x = riser_x_by_panel[panel_uid]
        elem = draw_segment(doc, view, riser_x, min(ys), riser_x, max(ys))
        if elem is not None:
            new_ids.append(elem.Id.IntegerValue)
            style = line_style_by_panel.get(panel_uid)
            if style is not None:
                try:
                    elem.LineStyle = style
                except:
                    pass

    return new_ids
