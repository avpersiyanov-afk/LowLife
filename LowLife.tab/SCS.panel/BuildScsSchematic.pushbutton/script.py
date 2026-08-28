# -*- coding: utf-8 -*-
__title__ = "Структурная\nсхема"
__doc__ = (
    "Строит/обновляет структурную схему СКС. Сама находит устройства через "
    "уже настроенные цепи и панели (те же критерии, что и «Расчёт длины "
    "цепи»), группирует их по этажу (подпись — «Этаж N (отметка)», порядок "
    "по отметке: отрицательные — внизу схемы, глубже — ниже; положительные "
    "— выше, чем больше отметка) и по помещению — рамки и раскладка "
    "устроены так же, как у структурной схемы СОТ.\n\n"
    "У каждой панели (шкафа/патч-панели) — своя независимая цветная шина: "
    "свой горизонтальный коллектор на каждом этаже, где у неё есть "
    "устройство (только её собственные отростки), свой вертикальный "
    "стояк слева от рамок через все её этажи. Коллекторы и стояки разных "
    "панелей на одном этаже разнесены — по высоте (коллектор) и по X "
    "(стояк), не накладываются друг на друга. Отростки, коллектор и "
    "стояк одной панели окрашены в один и тот же цвет (Line Style, "
    "создаётся автоматически по имени панели) — видно, какое устройство "
    "к какому шкафу идёт. Показаны только розетка и панель, без "
    "промежуточных узлов трассы (без стояков/узлов маршрута из «Адреса "
    "узлов»).\n\n"
    "Магистральные связи шкаф-шкаф (цепь, у которой вместо устройства "
    "оказалась другая целевая панель — например оптическая линия между "
    "двумя шкафами) отходят от собственного узла каждого шкафа (не от "
    "его шины устройств — на видимом расстоянии от неё) до своей "
    "отдельной вертикальной дорожки слева от стояков панелей, ярким "
    "жирным цветом; несколько связей через общий шкаф (цепочка A-B-C) "
    "используют одну общую дорожку на всех.\n\n"
    "Повторный запуск не пересоздаёт схему с нуля: обновляется вид с именем "
    "из настроек, раскладка предыдущего запуска хранится в служебном "
    "параметре этого вида — трогаются (двигаются/перерисовываются) только "
    "этаж/помещение/устройство, где реально что-то изменилось. Линии шины "
    "не редактируются вручную — перерисовываются заново на каждом запуске."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    ElementId, FilteredElementCollector, ViewFamilyType, ViewFamily, ViewDrafting
)
from pyrevit import revit, forms, script as pyrevit_script

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict

from lowlife.params import get_string_param, set_param_any
from lowlife.scs import collect_target_panel_devices, safe_element_name
from lowlife.scs_circuits import norm
from lowlife.skud import category_by_type_id, parse_category_names
from lowlife import scs_settings
from lowlife.scs_settings import (
    get_settings_silent, get_schematic_category_symbols, get_schematic_category_device_type_ids
)
from lowlife.sot_levels import group_elements_by_level, sorted_level_names, get_level_label
from lowlife.sot_schematic import sync_levels, RESERVED_BOTTOM_MM
from lowlife.scs_schematic import (
    sync_panel_buses, sync_trunk_links, BOUNDARY_MARGIN_MM, BUS_DROP_SPACING_MM, ROOM_BOTTOM_MM,
    RISER_BASE_OFFSET_MM, RISER_SPACING_MM, RISER_CORRIDOR_WIDTH_MM, group_trunk_components
)
from lowlife.sot_layout_state import find_layout_view, save_state
from lowlife.room_info import get_point as get_room_point, find_room_info, format_room_value

doc = revit.doc
output = pyrevit_script.get_output()


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

scs_settings.require(settings, [
    "workset_param_name", "workset_filter_key", "circuit_panel_param",
    "excluded_device_keywords", "device_address_param",
    "room_param_name", "room_number_param_name",
    "schematic_view_name", "layout_param_name", "device_uid_param_name",
    "node_label_offset_mm", "schematic_device_categories_text",
])
# addr_param_name/addr_prev_param_name/nearest_segment_param здесь не
# нужны — структурная схема не смотрит на узлы трассы вообще, только на
# устройства и их панели (см. __doc__ выше).

WORKSET_PARAM_NAME = settings["workset_param_name"]
WORKSET_FILTER_KEY = settings["workset_filter_key"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]

ROOM_PARAM_NAME = settings["room_param_name"]
ROOM_NUMBER_PARAM_NAME = settings["room_number_param_name"]
SCHEMATIC_VIEW_NAME = settings["schematic_view_name"]
LAYOUT_PARAM_NAME = settings["layout_param_name"]
DEVICE_UID_PARAM_NAME = settings["device_uid_param_name"]

try:
    NODE_LABEL_OFFSET_MM = float(settings["node_label_offset_mm"].replace(u",", u"."))
except (ValueError, AttributeError):
    NODE_LABEL_OFFSET_MM = 5.0


ANNOTATION_SYMBOL = None
if settings.get("node_annotation_type_id"):
    try:
        ANNOTATION_SYMBOL = doc.GetElement(ElementId(int(settings["node_annotation_type_id"])))
    except:
        ANNOTATION_SYMBOL = None

if ANNOTATION_SYMBOL is None:
    forms.alert(
        u"Не выбрана марка узла в настройках СКС — марки над схемными "
        u"семействами ставиться не будут.\n\n"
        u"Откройте «Параметры СКС» и выберите марку узла, чтобы включить их."
    )

# Категория устройства/панели (для выбора схемного семейства) — по точному
# совпадению ElementId реального типа, как у структурных схем СОТ/СКУД:
# заводится в «Параметры СКС» (список категорий + для каждой — схемное
# семейство и реальные типы устройств/панелей этой категории). Элемент,
# чей тип не сопоставлен ни одной категории, на схему не попадёт (см.
# unmatched_report ниже) — та же логика, что у структурной схемы СОТ.
CATEGORY_SYMBOLS = get_schematic_category_symbols(doc, settings)

if not CATEGORY_SYMBOLS:
    forms.alert(
        u"Не выбрано ни одного схемного семейства для категорий устройств СКС.\n\n"
        u"Откройте «Параметры СКС», заполните «Категории устройств схемы» и для "
        u"каждой нажмите «Обновить список категорий», затем выберите схемное "
        u"семейство.",
        exitscript=True
    )

CATEGORY_DEVICE_TYPE_IDS = get_schematic_category_device_type_ids(settings)

if not CATEGORY_DEVICE_TYPE_IDS:
    forms.alert(
        u"Не выбраны реальные типы устройств/панелей ни для одной категории СКС.\n\n"
        u"Откройте «Параметры СКС» и для каждой категории выберите реальные типы "
        u"устройств/панелей модели.",
        exitscript=True
    )


def category_for_device(el):
    return category_by_type_id(el, CATEGORY_DEVICE_TYPE_IDS)


# ------------------------------------------------------------
# АВТОСБОР УСТРОЙСТВ И ПАНЕЛЕЙ (те же критерии, что «Расчёт длины цепи»)
# ------------------------------------------------------------

panel_devices, trunk_links = collect_target_panel_devices(
    doc, WORKSET_PARAM_NAME, WORKSET_FILTER_KEY, CIRCUIT_PANEL_PARAM,
    EXCLUDED_DEVICE_KEYWORDS, norm
)

if not panel_devices:
    forms.alert(
        u"Не найдено ни одной целевой панели с подключёнными устройствами "
        u"(проверьте те же настройки, что использует «Расчёт длины цепи»: "
        u"рабочий набор панелей, «Параметр цепи «Панель»»).",
        exitscript=True
    )

# Магистральные связи шкаф-шкаф (например оптическая линия между двумя
# панелями) — цепь, где вместо устройства оказалась другая целевая
# панель. Рисуются отдельными линиями (sync_trunk_links) от собственного
# узла шкафа, не через его шину устройств. Панель, у которой из
# подключений есть только такие магистрали (без единого обычного
# устройства), в panel_devices не попадает вовсе (collect_target_panel_devices
# пропускает панели без устройств) — добавляем её отдельно, с пустым
# списком устройств, иначе она не окажется на схеме и магистраль до неё
# не от чего будет вести.
panel_devices_by_uid = dict((p.UniqueId, (p, devs)) for p, devs in panel_devices)
for a, b in trunk_links:
    for p in (a, b):
        if p.UniqueId not in panel_devices_by_uid:
            panel_devices_by_uid[p.UniqueId] = (p, [])

panel_devices = sorted(panel_devices_by_uid.values(), key=lambda pd: norm(pd[0].Name) or u"")

trunk_link_uids = [(a.UniqueId, b.UniqueId) for a, b in trunk_links]

elements = []
seen_ids = set()
panel_device_uids = {}
panel_names = {}
panels_order = []

for panel, devices in panel_devices:
    panels_order.append(panel.UniqueId)
    panel_names[panel.UniqueId] = norm(panel.Name) or panel.UniqueId

    if panel.Id.IntegerValue not in seen_ids:
        seen_ids.add(panel.Id.IntegerValue)
        elements.append(panel)

    member_uids = set([panel.UniqueId])
    for d in devices:
        member_uids.add(d.UniqueId)
        if d.Id.IntegerValue not in seen_ids:
            seen_ids.add(d.Id.IntegerValue)
            elements.append(d)

    panel_device_uids[panel.UniqueId] = member_uids


# ------------------------------------------------------------
# ДИАГНОСТИКА СОПОСТАВЛЕНИЯ КАТЕГОРИЙ: для каждого элемента схемы —
# какой РЕАЛЬНЫЙ тип у него и в какую категорию (значит, в какое схемное
# семейство) он попал по факту. Не влияет на саму схему — только на
# отчёт ниже; нужно, чтобы разница между тем, что настроено, и тем, что
# получилось, была видна сразу, а не терялась внутри sync_levels.
# ------------------------------------------------------------

def _symbol_display(symbol):
    if symbol is None:
        return u"?"
    fam_name = None
    try:
        fam_name = safe_element_name(symbol.Family)
    except:
        pass
    type_name = safe_element_name(symbol)
    return u"{} : {}".format(fam_name or u"?", type_name or symbol.Id.IntegerValue)


def _real_type_display(el):
    try:
        symbol = doc.GetElement(el.GetTypeId())
    except:
        symbol = None
    return _symbol_display(symbol)


CATEGORY_NAMES_ORDER = parse_category_names(settings.get("schematic_device_categories_text", u""))
category_diag = dict((name, {}) for name in CATEGORY_NAMES_ORDER)
uncategorized_diag = {}

for el in elements:
    cat = category_for_device(el)
    real_type = _real_type_display(el)
    bucket = category_diag.get(cat) if cat is not None else None
    if bucket is None:
        uncategorized_diag[real_type] = uncategorized_diag.get(real_type, 0) + 1
    else:
        bucket[real_type] = bucket.get(real_type, 0) + 1


# ------------------------------------------------------------
# ПОМЕЩЕНИЕ И АДРЕС ДЛЯ ПОДПИСИ (панели подписываются своим именем)
# ------------------------------------------------------------

room_counters = {"already_set": 0, "looked_up": 0, "not_found": 0}


def resolve_room_value(doc, el, counters):
    """
    Значение параметра ROOM_PARAM_NAME, если уже заполнено; иначе ищет
    помещение в связанной модели (room_info) и записывает найденное
    значение на элемент, чтобы при повторном запуске не искать снова.
    Тот же приём, что и у структурной схемы СОТ.
    """
    room_value = get_string_param(el, ROOM_PARAM_NAME)

    if room_value and room_value.strip():
        counters["already_set"] += 1
        return room_value.strip()

    point = get_room_point(el)
    room_name, room_number = find_room_info(doc, point, ROOM_NUMBER_PARAM_NAME)
    looked_up_value = format_room_value(room_name, room_number)

    if looked_up_value:
        set_param_any(el, ROOM_PARAM_NAME, looked_up_value)
        counters["looked_up"] += 1
        return looked_up_value

    counters["not_found"] += 1
    return u""


# sync_levels/sync_rooms_in_level читают адрес по одному фиксированному
# имени параметра (DEVICE_ADDRESS_PARAM) у КАЖДОГО элемента, включая
# панель — у панели такого параметра нет, поэтому её адрес для сортировки
# внутри помещения и подписи на марке просто окажется пустым, а имя
# панели всё равно видно по подписи помещения. Отдельный параметр под
# панель не заводим — не усложняем ради одной строки в редком случае.


# ------------------------------------------------------------
# ГРУППИРОВКА ПО ЭТАЖУ
# ------------------------------------------------------------

level_groups = group_elements_by_level(doc, elements, u"")
level_order = sorted_level_names(level_groups)
level_labels = dict((name, get_level_label(name)) for name in level_order)


# ------------------------------------------------------------
# МЕСТО ПОД ШИНЫ: рамка этажа должна вмещать все линии коллекторов —
# на случай, если все панели окажутся на одном этаже (худший случай,
# не по каждому этажу отдельно — проще и одинаковая высота строк).
# ------------------------------------------------------------

# ROOM_BOTTOM_MM — насколько ниже level_y уходит сама рамка помещения
# (см. scs_schematic.ROOM_BOTTOM_MM) — первая линия кабеля отсчитывается
# от ЭТОЙ границы, не от level_y напрямую, иначе линия попадает поверх/
# внутрь рамки помещения (см. panel_collector_y).
if panels_order:
    deepest_bus_offset_mm = (
        ROOM_BOTTOM_MM + BOUNDARY_MARGIN_MM + (len(panels_order) - 1) * BUS_DROP_SPACING_MM
    )
else:
    deepest_bus_offset_mm = 0.0

# Если есть хоть одна магистральная связь — у каждого шкафа-участника
# ещё и собственный отвод магистрали (trunk_drop_y), который проходит
# ЕЩЁ дальше от этажа, чем шина устройств самой глубокой (по индексу)
# панели схемы — на один шаг BUS_DROP_SPACING_MM (та же формула, что и в
# trunk_drop_y — panel_count-я, "виртуальная" позиция panel_collector_y,
# без отдельного увеличенного зазора — между всеми линиями кабелей на
# этаже одно и то же расстояние).
if trunk_link_uids:
    deepest_trunk_offset_mm = ROOM_BOTTOM_MM + BOUNDARY_MARGIN_MM + len(panels_order) * BUS_DROP_SPACING_MM
else:
    deepest_trunk_offset_mm = 0.0

# Запас между самой глубокой линией кабеля и нижней границей рамки —
# тот же BOUNDARY_MARGIN_MM, что и сверху (между узлами и первой линией):
# по требованию пользователя это одно и то же число, а не два разных
# подобранных на глаз значения (было — отдельный, больший запас для
# магистрали, потому что её жирная линия визуально "съедала" узкий запас
# тонких линий шины; тот запас был лишней сложностью, раз этот теперь
# одинаковый и для магистрали, и для шины).
EXTRA_BOTTOM_MM = max(
    0.0,
    deepest_bus_offset_mm + BOUNDARY_MARGIN_MM - RESERVED_BOTTOM_MM,
    deepest_trunk_offset_mm + BOUNDARY_MARGIN_MM - RESERVED_BOTTOM_MM
)


# ------------------------------------------------------------
# МЕСТО ПОД СТОЯКИ/ДОРОЖКИ: коридор между первой и второй линией рамки
# этажа должен вмещать по X все стояки панелей и все дорожки магистралей
# — тот же принцип, что и EXTRA_BOTTOM_MM выше, только влево, а не вниз.
# Расширяется именно этот коридор (см. _draw_level_frame), а не рамка
# целиком — иначе стояки/дорожки залезали бы в соседний коридор подписи
# этажа (за второй линией) или подпись оставалась бы слишком близко к
# ним, не отодвигаясь вместе с расширением.
# ------------------------------------------------------------

if panels_order:
    deepest_riser_offset_mm = RISER_BASE_OFFSET_MM + (len(panels_order) - 1) * RISER_SPACING_MM
else:
    deepest_riser_offset_mm = 0.0

# Число дорожек магистралей — не число связей trunk_link_uids, а число
# независимых ЦЕПОЧЕК после группировки (см. scs_schematic.group_trunk_
# components/sync_trunk_links) — у цепочки из нескольких связей одна
# общая дорожка, не по дорожке на каждую связь.
trunk_components = group_trunk_components(trunk_link_uids) if trunk_link_uids else []
if trunk_components:
    deepest_lane_offset_mm = (
        deepest_riser_offset_mm + BOUNDARY_MARGIN_MM + (len(trunk_components) - 1) * RISER_SPACING_MM
    )
else:
    deepest_lane_offset_mm = 0.0

EXTRA_LEFT_MM = max(
    0.0,
    deepest_riser_offset_mm + BOUNDARY_MARGIN_MM - RISER_CORRIDOR_WIDTH_MM,
    deepest_lane_offset_mm + BOUNDARY_MARGIN_MM - RISER_CORRIDOR_WIDTH_MM
)


# ------------------------------------------------------------
# ЧЕРТЁЖНЫЙ ВИД: ищем вид с именем из настроек (для обновления), иначе создаём
# ------------------------------------------------------------

view, previous_state, name_conflict = find_layout_view(doc, SCHEMATIC_VIEW_NAME, LAYOUT_PARAM_NAME)

if name_conflict:
    forms.alert(
        u"В проекте уже есть вид с именем «{}», но это не чертёжный вид — "
        u"структурную схему СКС туда поставить нельзя.\n\n"
        u"Переименуйте существующий вид либо измените имя вида в «Параметры "
        u"СКС».".format(SCHEMATIC_VIEW_NAME),
        exitscript=True
    )

is_new_view = view is None

if is_new_view:
    drafting_type_id = None

    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements():
        try:
            if vft.ViewFamily == ViewFamily.Drafting:
                drafting_type_id = vft.Id
                break
        except:
            continue

    if drafting_type_id is None:
        forms.alert(u"В проекте не найден ViewFamilyType для чертёжных видов (Drafting).", exitscript=True)

    previous_state = {"v": 1, "levels": {}}


# ------------------------------------------------------------
# СИНХРОНИЗАЦИЯ
# ------------------------------------------------------------

unmatched_report = []
sync_stats = {}

with revit.Transaction(u"Sync SCS Schematic"):
    level_room_groups = OrderedDict()
    # {level_name: {room_key: реальный X (левая граница помещения по
    # плану, min по устройствам в нём)}} — чтобы помещения на схеме шли
    # слева направо в том же порядке, что и на плане, а не по номеру/
    # имени (см. room_sort_values в sync_levels/sync_rooms_in_level).
    room_sort_values = {}

    for level_name in level_order:
        room_groups = OrderedDict()
        room_min_x = {}

        for el in level_groups[level_name]["elements"]:
            room_value = resolve_room_value(doc, el, room_counters)
            room_key = room_value if room_value else u"(пусто)"

            if room_key not in room_groups:
                room_groups[room_key] = []
            room_groups[room_key].append(el)

            pt = get_room_point(el)
            if pt is not None:
                if room_key not in room_min_x or pt.X < room_min_x[room_key]:
                    room_min_x[room_key] = pt.X

        level_room_groups[level_name] = room_groups
        room_sort_values[level_name] = room_min_x

    if is_new_view:
        view = ViewDrafting.Create(doc, drafting_type_id)
        view.Name = SCHEMATIC_VIEW_NAME
        view.Scale = 1

    # У новых чертёжных видов в проекте может быть настроен шаблон по
    # умолчанию — Revit применяет его автоматически при ViewDrafting.Create,
    # без явного участия этого кода. Шаблон вида умеет ограничивать
    # видимость категорий/подкатегорий (в т.ч. только что созданных Line
    # Style для линий шины/магистралей — сам шаблон о них ничего не знает,
    # мог "не пустить" их как непредусмотренные) — из-за этого сами линии
    # в модели создаются нормально, а на виде не видны. У СКС, в отличие
    # от СОТ, настройки шаблона нет вообще — поэтому снимаем шаблон
    # безусловно на каждом запуске, а не только для новых видов.
    try:
        view.ViewTemplateId = ElementId.InvalidElementId
    except:
        pass

    view_name = view.Name

    new_state, all_report_rows = sync_levels(
        doc, view, level_order, level_room_groups, level_labels, CATEGORY_SYMBOLS, category_for_device,
        ROOM_PARAM_NAME, DEVICE_ADDRESS_PARAM, DEVICE_UID_PARAM_NAME, ANNOTATION_SYMBOL,
        NODE_LABEL_OFFSET_MM, previous_state, unmatched_report, sync_stats,
        extra_bottom_mm=EXTRA_BOTTOM_MM, extra_left_mm=EXTRA_LEFT_MM, room_sort_values=room_sort_values
    )

    old_bus_line_ids = list(previous_state.get("bus_line_ids", []))
    # Разовая миграция: до 27.08 линии шины хранились в
    # "panel_bus_line_ids" как {panel_uid: [id, ...]} (независимая шина
    # на каждую панель) — раскладка, сохранённая тем прошлым запуском,
    # всё ещё может нести это старое поле. Новый код смотрит только на
    # "bus_line_ids" и без этой строки никогда не найдёт и не удалит те
    # линии — они остались бы в модели осиротевшими навсегда.
    for ids in previous_state.get("panel_bus_line_ids", {}).values():
        old_bus_line_ids.extend(ids)
    new_state["bus_line_ids"], panel_anchors = sync_panel_buses(
        doc, view, new_state, old_bus_line_ids, panels_order, panel_device_uids, panel_names
    )

    old_trunk_line_ids = list(previous_state.get("trunk_line_ids", []))
    new_state["trunk_line_ids"], trunk_skipped = sync_trunk_links(
        doc, view, new_state, old_trunk_line_ids, trunk_link_uids, panel_anchors, len(panels_order)
    )

    state_saved, state_save_error = save_state(view, LAYOUT_PARAM_NAME, new_state)


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

output.print_md(u"### Структурная схема СКС: {}".format(view_name))

if not state_saved:
    output.print_md(
        u"### ⚠ Раскладка НЕ сохранена в параметр вида «{}»\n\n"
        u"Причина: {}.\n\n"
        u"Без этого параметра повторный запуск не найдёт сегодняшнюю раскладку и "
        u"нарисует все узлы/помещения/этажи заново поверх уже существующих "
        u"(дублирование).".format(LAYOUT_PARAM_NAME, state_save_error)
    )

output.print_md(u"Панелей на схеме: **{}**, линий шины нарисовано: **{}**".format(
    len(panels_order), len(new_state["bus_line_ids"])
))
if trunk_link_uids:
    output.print_md(u"Магистральных связей шкаф-шкаф: **{}**, линий нарисовано: **{}**".format(
        len(trunk_link_uids), len(new_state["trunk_line_ids"])
    ))
    if trunk_skipped:
        skip_labels = {
            "no_riser_a": u"панель A не размещена на схеме (нет линии шины)",
            "no_riser_b": u"панель B не размещена на схеме (нет линии шины)",
            "draw_failed": u"стояки размещены, но саму линию нарисовать не удалось",
        }
        output.print_md(u"### Не нарисовано ({})".format(len(trunk_skipped)))
        for panel_uid_a, panel_uid_b, reason in trunk_skipped:
            name_a = panel_names.get(panel_uid_a, panel_uid_a)
            name_b = panel_names.get(panel_uid_b, panel_uid_b)
            output.print_md(u"- {} <-> {}: {}".format(name_a, name_b, skip_labels.get(reason, reason)))

output.print_md(u"{}, этажей: {}, устройств на схеме: {}".format(
    u"Вид создан заново" if is_new_view else u"Вид обновлён",
    len(level_order), len(all_report_rows)
))
output.print_md(
    u"Помещения: не тронуто {}, сдвинуто {}, создано {}, перерисовано {}, удалено {}".format(
        sync_stats.get("rooms_unchanged", 0), sync_stats.get("rooms_moved", 0),
        sync_stats.get("rooms_created", 0), sync_stats.get("rooms_redrawn", 0),
        sync_stats.get("rooms_removed", 0)
    )
)
if sync_stats.get("tags_added", 0):
    output.print_md(
        u"Добавлено марок задним числом на уже стоявшие узлы: **{}**.".format(sync_stats["tags_added"])
    )
output.print_md(
    u"Этажи: не тронуто {}, сдвинуто {}, создано {}, перерисовано {}, удалено {}".format(
        sync_stats.get("levels_unchanged", 0), sync_stats.get("levels_moved", 0),
        sync_stats.get("levels_created", 0), sync_stats.get("levels_redrawn", 0),
        sync_stats.get("levels_removed", 0)
    )
)
output.print_md(
    u"Помещение (реального устройства/панели): уже было заполнено — {}, найдено в связи — {}, "
    u"не найдено — {}".format(
        room_counters["already_set"], room_counters["looked_up"], room_counters["not_found"]
    )
)

if room_counters["not_found"]:
    output.print_md(
        u"Для элементов без найденного помещения (**{}** шт.) на схеме будет "
        u"группа «(пусто)» — либо точка элемента не попадает ни в один Room "
        u"связанной модели, либо не подключена сама связь.".format(room_counters["not_found"])
    )

output.print_md(u"### Сопоставление категорий (что реально попало на схему)")
if not CATEGORY_NAMES_ORDER:
    output.print_md(u"Категории не заданы («Категории устройств схемы» в «Параметры СКС» пусто).")
for cat_name in CATEGORY_NAMES_ORDER:
    symbol = CATEGORY_SYMBOLS.get(cat_name)
    symbol_display = _symbol_display(symbol) if symbol is not None else u"(схемное семейство не выбрано)"
    counts = category_diag.get(cat_name) or {}
    total = sum(counts.values())
    output.print_md(u"- «{}» -> **{}** — устройств: **{}**".format(cat_name, symbol_display, total))
    for real_type, n in sorted(counts.items()):
        output.print_md(u"  - {}: {}".format(real_type, n))
    if total == 0:
        output.print_md(
            u"  - (ни один реальный тип не сопоставлен этой категории — "
            u"проверьте «Реальные типы устройств/панелей этой категории» "
            u"в «Параметры СКС»)"
        )
if uncategorized_diag:
    output.print_md(u"Реальные типы БЕЗ категории (на схему не попадут):")
    for real_type, n in sorted(uncategorized_diag.items()):
        output.print_md(u"- {}: {}".format(real_type, n))

if unmatched_report:
    output.print_md(u"### Не размещено (нет схемного семейства) — {}".format(len(unmatched_report)))
    for level_label, room_key, device in unmatched_report:
        try:
            device_name = device.Name
        except:
            device_name = u"?"
        output.print_md(u"- {} / {} — {} (ID {})".format(level_label, room_key, device_name, device.Id.IntegerValue))

forms.alert(
    u"{}"
    u"Готово.\n\n"
    u"Вид: {} ({})\n"
    u"Панелей: {}\n"
    u"Этажей: {}\n"
    u"Устройств на схеме: {}\n\n"
    u"Подробности — в окне вывода pyRevit.".format(
        (u"ВНИМАНИЕ: раскладка НЕ сохранена в параметр вида «{}».\nПричина: {}.\n"
         u"Без этого параметра следующий запуск продублирует схему.\n\n".format(
             LAYOUT_PARAM_NAME, state_save_error
         )
         if not state_saved else u""),
        view_name, (u"новый" if is_new_view else u"обновлён"),
        len(panels_order), len(level_order), len(all_report_rows)
    )
)
