# -*- coding: utf-8 -*-
__title__ = "Структурная\nсхема СПС"
__doc__ = (
    "Строит/обновляет структурную схему СПС (пожарная сигнализация и "
    "электрооборудование — панели/изоляторы). Сама находит на модели все "
    "устройства, тип которых сопоставлен категории в настройках СПС, "
    "группирует их по этажу (подпись — «Этаж N (отметка)», порядок по "
    "отметке: отрицательные — внизу схемы, глубже — ниже; положительные — "
    "выше, чем больше отметка) и по помещению.\n\n"
    "Повторный запуск не пересоздаёт схему с нуля: обновляется вид с именем "
    "из настроек СПС (создаётся с этим именем, если его ещё нет), раскладка "
    "предыдущего запуска хранится в служебном параметре этого вида — "
    "обновляются только этаж/помещение/устройство, где реально что-то "
    "изменилось (добавилось/пропало/переехало), остальное остаётся как было, "
    "теми же элементами. Соседи справа/ниже места изменения сдвигаются, "
    "чтобы закрыть/освободить место. Шаблон вида (если выбран в настройках) "
    "применяется на каждом запуске."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    ElementId, FilteredElementCollector, BuiltInCategory, ViewFamilyType, ViewFamily, ViewDrafting
)
from pyrevit import revit, forms, script as pyrevit_script

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict

from lowlife.params import get_string_param, set_param_any
from lowlife.skud import category_by_type_id
from lowlife import fire_alarm_settings
from lowlife.fire_alarm_settings import (
    get_settings_silent, get_schematic_category_symbols, get_schematic_category_device_type_ids,
    get_node_annotation_symbol, get_view_template, SCHEMATIC_SOURCE_CATEGORIES
)
from lowlife.sot_levels import group_elements_by_level, sorted_level_names, get_level_label
from lowlife.sot_schematic import sync_levels
from lowlife.sot_layout_state import find_layout_view, save_state
from lowlife.room_info import get_point as get_room_point, find_room_info, format_room_value

fire_alarm_settings.set_system("SPS")

doc = revit.doc
output = pyrevit_script.get_output()


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

fire_alarm_settings.require(settings, [
    "room_param_name", "room_number_param_name", "device_address_param",
    "node_label_offset_mm", "schematic_view_name", "layout_param_name", "device_uid_param_name",
    "schematic_device_categories_text",
])

LEVEL_PARAM_NAME = settings["level_param_name"]
ROOM_PARAM_NAME = settings["room_param_name"]
ROOM_NUMBER_PARAM_NAME = settings["room_number_param_name"]
ADDRESS_PARAM_NAME = settings["device_address_param"]
SCHEMATIC_VIEW_NAME = settings["schematic_view_name"]
LAYOUT_PARAM_NAME = settings["layout_param_name"]
DEVICE_UID_PARAM_NAME = settings["device_uid_param_name"]

try:
    NODE_LABEL_OFFSET_MM = float(settings["node_label_offset_mm"].replace(u",", u"."))
except (ValueError, AttributeError):
    NODE_LABEL_OFFSET_MM = 5.0

ANNOTATION_SYMBOL = get_node_annotation_symbol(doc, settings)
VIEW_TEMPLATE = get_view_template(doc, settings)

if ANNOTATION_SYMBOL is None:
    forms.alert(
        u"Не выбрана марка узла в настройках СПС — марки над схемными "
        u"семействами ставиться не будут.\n\n"
        u"Откройте «Параметры СПС» и выберите марку узла, чтобы включить их."
    )

CATEGORY_SYMBOLS = get_schematic_category_symbols(doc, settings)

if not CATEGORY_SYMBOLS:
    forms.alert(
        u"Не выбран ни один тип схемного семейства для категорий устройств "
        u"структурной схемы СПС.\n\n"
        u"Откройте «Параметры СПС», обновите список категорий и выберите "
        u"схемное семейство для каждой из них.",
        exitscript=True
    )

CATEGORY_DEVICE_TYPE_IDS = get_schematic_category_device_type_ids(settings)

if not CATEGORY_DEVICE_TYPE_IDS:
    forms.alert(
        u"Не выбраны реальные типы устройств ни для одной категории "
        u"структурной схемы СПС.\n\n"
        u"Откройте «Параметры СПС» и выберите типы устройств модели для "
        u"каждой категории.",
        exitscript=True
    )


def category_for_device(el):
    return category_by_type_id(el, CATEGORY_DEVICE_TYPE_IDS)


# ------------------------------------------------------------
# АВТОСБОР УСТРОЙСТВ
# ------------------------------------------------------------

all_mapped_type_ids = set()
for ids in CATEGORY_DEVICE_TYPE_IDS.values():
    all_mapped_type_ids |= ids

elements = []

for cat_key in SCHEMATIC_SOURCE_CATEGORIES:
    collected = FilteredElementCollector(doc) \
        .OfCategory(getattr(BuiltInCategory, cat_key)) \
        .WhereElementIsNotElementType() \
        .ToElements()

    for el in collected:
        try:
            type_id = el.GetTypeId().IntegerValue
        except:
            continue
        if type_id in all_mapped_type_ids:
            elements.append(el)

if not elements:
    forms.alert(
        u"Не найдено ни одного устройства с типом, сопоставленным категории "
        u"в настройках СПС.",
        exitscript=True
    )


# ------------------------------------------------------------
# ГРУППИРОВКА ПО ЭТАЖУ
# ------------------------------------------------------------

level_groups = group_elements_by_level(doc, elements, LEVEL_PARAM_NAME)
level_order = sorted_level_names(level_groups)
level_labels = dict((name, get_level_label(name)) for name in level_order)


def resolve_room_value(doc, el, counters):
    """
    Значение параметра ROOM_PARAM_NAME на устройстве, если оно уже
    заполнено; если пусто — ищет помещение в связанной модели сам и
    записывает найденное значение на устройство, чтобы при повторном
    запуске схемы и других кнопках оно уже было под рукой.
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


# ------------------------------------------------------------
# ЧЕРТЁЖНЫЙ ВИД: ищем вид с именем из настроек (для обновления), иначе создаём
# ------------------------------------------------------------

view, previous_state, name_conflict = find_layout_view(doc, SCHEMATIC_VIEW_NAME, LAYOUT_PARAM_NAME)

if name_conflict:
    forms.alert(
        u"В проекте уже есть вид с именем «{}», но это не чертёжный вид — "
        u"структурную схему СПС туда поставить нельзя.\n\n"
        u"Переименуйте существующий вид либо измените имя вида в «Параметры "
        u"СПС».".format(SCHEMATIC_VIEW_NAME),
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
room_counters = {"already_set": 0, "looked_up": 0, "not_found": 0}
sync_stats = {}

with revit.Transaction(u"Sync SPS Schematic"):
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

    try:
        view.ViewTemplateId = VIEW_TEMPLATE.Id if VIEW_TEMPLATE is not None else ElementId.InvalidElementId
    except:
        pass

    new_state, all_report_rows = sync_levels(
        doc, view, level_order, level_room_groups, level_labels, CATEGORY_SYMBOLS, category_for_device,
        ROOM_PARAM_NAME, ADDRESS_PARAM_NAME, DEVICE_UID_PARAM_NAME, ANNOTATION_SYMBOL,
        NODE_LABEL_OFFSET_MM, previous_state, unmatched_report, sync_stats
    )

    save_state(view, LAYOUT_PARAM_NAME, new_state)


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

output.print_md(u"### Структурная схема СПС: {}".format(view_name))
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
        u"Добавлено марок задним числом на уже стоявшие узлы (раньше не было — "
        u"например, марка не была выбрана в настройках при первом запуске): "
        u"**{}**.".format(sync_stats["tags_added"])
    )
output.print_md(
    u"Этажи: не тронуто {}, сдвинуто {}, создано {}, перерисовано {}, удалено {}".format(
        sync_stats.get("levels_unchanged", 0), sync_stats.get("levels_moved", 0),
        sync_stats.get("levels_created", 0), sync_stats.get("levels_redrawn", 0),
        sync_stats.get("levels_removed", 0)
    )
)
output.print_md(
    u"Помещение (реального устройства): уже было заполнено — {}, найдено в связи — {}, не найдено — {}".format(
        room_counters["already_set"], room_counters["looked_up"], room_counters["not_found"]
    )
)

if room_counters["not_found"]:
    output.print_md(
        u"Для устройств без найденного помещения (**{}** шт.) на схеме будет "
        u"группа «(пусто)» — либо точка устройства не попадает ни в один Room "
        u"связанной модели, либо не подключена сама связь.".format(room_counters["not_found"])
    )

if unmatched_report:
    output.print_md(u"### Не размещено (нет категории/схемного семейства) — {}".format(len(unmatched_report)))
    for level_label, room_key, device in unmatched_report:
        try:
            device_name = device.Name
        except:
            device_name = u"?"
        output.print_md(u"- {} / {} — {} (ID {})".format(level_label, room_key, device_name, device.Id.IntegerValue))

forms.alert(
    u"Готово.\n\n"
    u"Вид: {} ({})\n"
    u"Этажей: {}\n"
    u"Устройств на схеме: {}\n"
    u"Не размещено (нет категории/схемного семейства): {}\n\n"
    u"Подробности (включая статистику "
    u"не тронуто/сдвинуто/создано/перерисовано/удалено) — в окне вывода pyRevit.".format(
        view_name, (u"новый" if is_new_view else u"обновлён"),
        len(level_order), len(all_report_rows), len(unmatched_report)
    )
)
