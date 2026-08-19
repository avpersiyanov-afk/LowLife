# -*- coding: utf-8 -*-
__title__ = "Структурная\nсхема"
__doc__ = (
    "Строит структурную схему СОТ (охранное телевидение): создаёт новый "
    "чертёжный вид, сама находит на модели все устройства, тип которых "
    "сопоставлен категории в настройках СОТ, группирует их по этажу "
    "(подземные этажи — внизу схемы, глубже — ниже) и по помещению, "
    "рисует рамку на каждую группу, вставляет схемное семейство на месте "
    "каждого устройства и копирует на него адрес и помещение."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, ViewFamilyType, ViewFamily, ViewDrafting
from pyrevit import revit, forms, script as pyrevit_script

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict

from lowlife.params import get_string_param
from lowlife.skud import category_by_type_id
from lowlife import sot_settings
from lowlife.sot_settings import (
    get_settings_silent, get_schematic_category_symbols, get_schematic_category_device_type_ids,
    SOURCE_CATEGORIES
)
from lowlife.sot_levels import group_elements_by_level, sorted_level_names
from lowlife.sot_schematic import build_level_block, get_unique_view_name

doc = revit.doc
output = pyrevit_script.get_output()


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

sot_settings.require(settings, [
    "underground_prefix", "room_param_name", "address_param_name",
    "schematic_device_categories_text"
])

LEVEL_PARAM_NAME = settings["level_param_name"]
UNDERGROUND_PREFIX = settings["underground_prefix"]
ROOM_PARAM_NAME = settings["room_param_name"]
ADDRESS_PARAM_NAME = settings["address_param_name"]

CATEGORY_SYMBOLS = get_schematic_category_symbols(doc, settings)

if not CATEGORY_SYMBOLS:
    forms.alert(
        u"Не выбран ни один тип схемного семейства для категорий устройств СОТ.\n\n"
        u"Откройте «Параметры СОТ», обновите список категорий и выберите "
        u"схемное семейство для каждой из них.",
        exitscript=True
    )

CATEGORY_DEVICE_TYPE_IDS = get_schematic_category_device_type_ids(settings)

if not CATEGORY_DEVICE_TYPE_IDS:
    forms.alert(
        u"Не выбраны реальные типы устройств ни для одной категории СОТ.\n\n"
        u"Откройте «Параметры СОТ» и выберите типы устройств модели для "
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

for cat_key in SOURCE_CATEGORIES:
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
        u"в настройках СОТ.",
        exitscript=True
    )


# ------------------------------------------------------------
# ГРУППИРОВКА ПО ЭТАЖУ И ПОМЕЩЕНИЮ
# ------------------------------------------------------------

level_groups = group_elements_by_level(doc, elements, LEVEL_PARAM_NAME)
level_order = sorted_level_names(level_groups, UNDERGROUND_PREFIX)

level_room_groups = OrderedDict()

for level_name in level_order:
    room_groups = OrderedDict()

    for el in level_groups[level_name]["elements"]:
        room_value = get_string_param(el, ROOM_PARAM_NAME)
        room_key = room_value.strip() if room_value and room_value.strip() else u"(пусто)"

        if room_key not in room_groups:
            room_groups[room_key] = []
        room_groups[room_key].append(el)

    level_room_groups[level_name] = room_groups


# ------------------------------------------------------------
# ЧЕРТЁЖНЫЙ ВИД
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# ПОСТРОЕНИЕ
# ------------------------------------------------------------

unmatched_report = []
all_report_rows = []

with revit.Transaction(u"Build SOT Schematic"):
    view_name = get_unique_view_name(doc, u"Структурная схема СОТ")
    view = ViewDrafting.Create(doc, drafting_type_id)
    view.Name = view_name
    view.Scale = 1

    current_level_y = 0.0

    for level_name in level_order:
        room_groups = level_room_groups[level_name]

        current_level_y, report_rows = build_level_block(
            doc, view, level_name, room_groups, CATEGORY_SYMBOLS, category_for_device,
            current_level_y, ROOM_PARAM_NAME, ADDRESS_PARAM_NAME, unmatched_report
        )

        all_report_rows.extend(report_rows)


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

output.print_md(u"### Структурная схема СОТ: {}".format(view_name))
output.print_md(u"Этажей: {}, устройств размещено: {}".format(len(level_order), len(all_report_rows)))

if unmatched_report:
    output.print_md(u"### Не размещено (нет категории/схемного семейства) — {}".format(len(unmatched_report)))
    for level_name, room_key, device in unmatched_report:
        try:
            device_name = device.Name
        except:
            device_name = u"?"
        output.print_md(u"- {} / {} — {} (ID {})".format(level_name, room_key, device_name, device.Id.IntegerValue))

forms.alert(
    u"Готово.\n\n"
    u"Вид: {}\n"
    u"Этажей: {}\n"
    u"Устройств размещено: {}\n"
    u"Не размещено (нет категории/схемного семейства): {}\n\n"
    u"Подробности — в окне вывода pyRevit.".format(
        view_name, len(level_order), len(all_report_rows), len(unmatched_report)
    )
)
