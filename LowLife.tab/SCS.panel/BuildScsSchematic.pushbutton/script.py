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
from lowlife.scs import collect_target_panel_devices
from lowlife.scs_circuits import norm
from lowlife.skud import category_by_type_id
from lowlife import scs_settings
from lowlife.scs_settings import (
    get_settings_silent, get_schematic_category_symbols, get_schematic_category_device_type_ids
)
from lowlife.sot_levels import group_elements_by_level, sorted_level_names, get_level_label
from lowlife.sot_schematic import sync_levels
from lowlife.scs_schematic import sync_panel_buses
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

panel_devices = collect_target_panel_devices(
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

panel_devices.sort(key=lambda pd: norm(pd[0].Name) or u"")

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

    for level_name in level_order:
        room_groups = OrderedDict()

        for el in level_groups[level_name]["elements"]:
            room_value = resolve_room_value(doc, el, room_counters)
            room_key = room_value if room_value else u"(пусто)"

            if room_key not in room_groups:
                room_groups[room_key] = []
            room_groups[room_key].append(el)

        level_room_groups[level_name] = room_groups

    if is_new_view:
        view = ViewDrafting.Create(doc, drafting_type_id)
        view.Name = SCHEMATIC_VIEW_NAME
        view.Scale = 1

    view_name = view.Name

    new_state, all_report_rows = sync_levels(
        doc, view, level_order, level_room_groups, level_labels, CATEGORY_SYMBOLS, category_for_device,
        ROOM_PARAM_NAME, DEVICE_ADDRESS_PARAM, DEVICE_UID_PARAM_NAME, ANNOTATION_SYMBOL,
        NODE_LABEL_OFFSET_MM, previous_state, unmatched_report, sync_stats
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
    new_state["bus_line_ids"] = sync_panel_buses(
        doc, view, new_state, old_bus_line_ids, panels_order, panel_device_uids, panel_names
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
