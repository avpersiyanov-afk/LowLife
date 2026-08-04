# -*- coding: utf-8 -*-
__title__ = "Структурная\nсхема"
__doc__ = (
    "Строит структурную схему СКУД по цепям контроллеров (от точки, "
    "указанной кликом на виде): вставляет схемные семейства контроллеров и "
    "их устройств (тип семейства и координаты — по категории устройства, "
    "из настроек СКУД), копирует адреса и соединяет контроллер с "
    "устройствами линиями детализации."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.geometry import get_element_level
from lowlife.params import get_string_param, set_param_any
from lowlife.scs import is_excluded_device
from lowlife.scs_circuits import norm, clean_text_value
from lowlife.skud import is_controller, parse_category_names, category_by_type_id
from lowlife.skud_schematic import layout_points_by_level, device_layout_point
from lowlife import skud_settings
from lowlife.skud_settings import (
    get_settings_silent, get_schematic_category_symbols,
    get_schematic_category_device_type_ids, get_schematic_category_layout_ft
)

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

FT_TO_M = 0.3048
M_TO_FT = 1.0 / FT_TO_M
MM_TO_FT = M_TO_FT / 1000.0


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param", "device_address_param",
    "schematic_address_param",
    "schematic_layout_gap_m", "schematic_layout_step_mm",
    "schematic_device_categories_text"
])

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]

CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]

SCHEMATIC_ADDRESS_PARAM = settings["schematic_address_param"]
LAYOUT_GAP_FT = float(settings["schematic_layout_gap_m"]) * M_TO_FT
CATEGORY_STEP_FT = float(settings["schematic_layout_step_mm"]) * MM_TO_FT

DEVICE_CATEGORY_NAMES = parse_category_names(settings["schematic_device_categories_text"])

if not DEVICE_CATEGORY_NAMES:
    forms.alert(
        u"Не заданы категории устройств схемы.\n\n"
        u"Заполните поле «Категории устройств схемы» в настройках СКУД "
        u"(по одному имени категории на строку).",
        exitscript=True
    )

CATEGORY_SYMBOLS = get_schematic_category_symbols(doc, settings)

if not CATEGORY_SYMBOLS:
    forms.alert(
        u"Не выбран ни один тип семейства для категорий устройств схемы.\n\n"
        u"Откройте «Параметры СКУД», обновите список категорий и выберите "
        u"схемное семейство для каждой из них (включая категорию «контроллер»).",
        exitscript=True
    )

CATEGORY_DEVICE_TYPE_IDS = get_schematic_category_device_type_ids(settings)
CATEGORY_LAYOUT_FT = get_schematic_category_layout_ft(settings)

CONTROLLER_CATEGORY_NAME = next(
    (n for n in DEVICE_CATEGORY_NAMES if n.lower() == u"контроллер"), None
)

if not CONTROLLER_CATEGORY_NAME or CONTROLLER_CATEGORY_NAME not in CATEGORY_SYMBOLS:
    forms.alert(
        u"Не задан тип семейства для категории «контроллер».\n\n"
        u"Добавьте в «Категории устройств схемы» строку «контроллер» и "
        u"выберите для неё схемное семейство в настройках СКУД.",
        exitscript=True
    )

CONTROLLER_SYMBOL = CATEGORY_SYMBOLS[CONTROLLER_CATEGORY_NAME]


# ------------------------------------------------------------
# КОНТРОЛЛЕРЫ И ИХ УСТРОЙСТВА
# ------------------------------------------------------------

all_equipment = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
    .WhereElementIsNotElementType() \
    .ToElements()

controllers = [
    e for e in all_equipment
    if is_controller(e, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD)
]

if not controllers:
    forms.alert(
        u"Не найдено ни одного контроллера (рабочий набор содержит «{}», "
        u"имя типа содержит «{}»).".format(CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD),
        exitscript=True
    )

all_circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()

circuits_by_controller_name = {}
for c in all_circuits:
    panel_name = norm(get_string_param(c, CIRCUIT_PANEL_PARAM))
    if panel_name:
        circuits_by_controller_name.setdefault(panel_name, []).append(c)

controllers_with_devices = []
controllers_without_address = []

for controller in controllers:
    controller_addr = clean_text_value(get_string_param(controller, DEVICE_ADDRESS_PARAM))
    if not controller_addr:
        controllers_without_address.append(controller.Name)
        continue

    controller_name = norm(controller.Name)
    devices = []

    for c in circuits_by_controller_name.get(controller_name, []):
        try:
            raw_devs = [x for x in c.Elements if x.Id != controller.Id]
        except:
            continue

        normal_devs = [d for d in raw_devs if not is_excluded_device(d, EXCLUDED_DEVICE_KEYWORDS)]
        devices.extend(normal_devs)

    if devices:
        devices.sort(key=lambda d: clean_text_value(get_string_param(d, DEVICE_ADDRESS_PARAM)) or u"")
        level = get_element_level(doc, controller)
        elevation = level.Elevation if level is not None else 0.0
        controllers_with_devices.append((controller, controller_addr, devices, elevation))

if not controllers_with_devices:
    forms.alert(u"Не найдено ни одного контроллера с адресом и подключёнными устройствами.", exitscript=True)

controllers_with_devices.sort(key=lambda item: (item[3], item[1]))


# ------------------------------------------------------------
# ТОЧКА ВСТАВКИ (клик на виде — начало координат схемы)
# ------------------------------------------------------------

try:
    base_point = uidoc.Selection.PickPoint(u"Укажите точку вставки структурной схемы")
except:
    forms.alert(u"Операция отменена.", exitscript=True)

level_elevations = [item[3] for item in controllers_with_devices]
insert_points = layout_points_by_level(base_point, level_elevations, LAYOUT_GAP_FT)


# ------------------------------------------------------------
# ВСТАВКА КОНТРОЛЛЕРОВ И УСТРОЙСТВ + АДРЕСА + ЛИНИИ
# ------------------------------------------------------------

controllers_placed = 0
devices_placed = 0
addresses_copied = 0
lines_created = 0
unmatched_report = []

if not CONTROLLER_SYMBOL.IsActive:
    CONTROLLER_SYMBOL.Activate()

with revit.Transaction("Build SKUD Schematic"):

    for (controller, controller_addr, devices, _elevation), insert_pt in zip(controllers_with_devices, insert_points):
        controller_el = doc.Create.NewFamilyInstance(insert_pt, CONTROLLER_SYMBOL, view)
        if controller_el is None:
            continue

        controllers_placed += 1
        if set_param_any(controller_el, SCHEMATIC_ADDRESS_PARAM, controller_addr):
            addresses_copied += 1

        unmatched_devices = []
        device_points = []
        index_by_category = {}

        for device in devices:
            category = category_by_type_id(device, CATEGORY_DEVICE_TYPE_IDS)
            symbol = CATEGORY_SYMBOLS.get(category) if category else None

            if symbol is None:
                unmatched_devices.append(device)
                continue

            if not symbol.IsActive:
                symbol.Activate()

            index_in_category = index_by_category.get(category, 0)
            device_pt = device_layout_point(
                insert_pt, CATEGORY_LAYOUT_FT, category, index_in_category, CATEGORY_STEP_FT
            )
            index_by_category[category] = index_in_category + 1

            device_el = doc.Create.NewFamilyInstance(device_pt, symbol, view)
            if device_el is None:
                unmatched_devices.append(device)
                continue

            devices_placed += 1
            device_points.append(device_pt)

            real_addr = clean_text_value(get_string_param(device, DEVICE_ADDRESS_PARAM))
            if real_addr and set_param_any(device_el, SCHEMATIC_ADDRESS_PARAM, real_addr):
                addresses_copied += 1

        if unmatched_devices:
            unmatched_report.append(
                u"Контроллер {} — не найдена категория/тип семейства для {} устройств.".format(
                    controller_addr, len(unmatched_devices)
                )
            )

        for device_pt in device_points:
            try:
                line = Line.CreateBound(insert_pt, device_pt)
                doc.Create.NewDetailCurve(view, line)
                lines_created += 1
            except:
                pass


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

from pyrevit import script as pyrevit_script
output = pyrevit_script.get_output()

if controllers_without_address:
    output.print_md(u"### Контроллеры без адреса, пропущены ({})".format(len(controllers_without_address)))
    for name in controllers_without_address:
        output.print_md(u"- {}".format(name))

if unmatched_report:
    output.print_md(u"### Не найдена категория/тип семейства для устройств ({})".format(len(unmatched_report)))
    for line in unmatched_report:
        output.print_md(u"- {}".format(line))

forms.alert(
    u"Готово.\n\n"
    u"Контроллеров с адресом и устройствами: {}\n"
    u"Контроллеров без адреса (пропущено): {}\n"
    u"Контроллеров размещено: {}\n"
    u"Устройств размещено: {}\n"
    u"Адресов скопировано: {}\n"
    u"Линий создано: {}\n"
    u"Предупреждений (не найдена категория/тип): {}\n\n"
    u"Подробности — в окне вывода pyRevit.".format(
        len(controllers_with_devices),
        len(controllers_without_address),
        controllers_placed,
        devices_placed,
        addresses_copied,
        lines_created,
        len(unmatched_report)
    )
)
