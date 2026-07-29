# -*- coding: utf-8 -*-
__title__ = "Структурная схема"
__doc__ = (
    "Размножает типовую группу-эталон структурной схемы по числу "
    "контроллеров СКУД (от точки, указанной кликом на виде), сопоставляет "
    "схемные семейства с реальными устройствами по категории и копирует "
    "адрес; соединяет контроллер с устройствами линиями детализации."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.geometry import get_point
from lowlife.params import get_string_param, set_param_any
from lowlife.scs import is_excluded_device
from lowlife.scs_circuits import norm, clean_text_value
from lowlife.skud import is_controller, parse_device_categories
from lowlife.skud_schematic import (
    find_template_group_type, group_member_elements, layout_points,
    match_devices_by_category, device_category_key
)
from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

FT_TO_M = 0.3048
M_TO_FT = 1.0 / FT_TO_M


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param", "device_address_param",
    "schematic_template_group_name", "schematic_address_param",
    "schematic_layout_gap_m", "schematic_layout_per_row",
    "schematic_device_categories_text"
])

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]

CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]

TEMPLATE_GROUP_NAME = settings["schematic_template_group_name"]
SCHEMATIC_ADDRESS_PARAM = settings["schematic_address_param"]
LAYOUT_GAP_FT = float(settings["schematic_layout_gap_m"]) * M_TO_FT
LAYOUT_PER_ROW = max(1, int(settings["schematic_layout_per_row"]))

DEVICE_CATEGORIES = parse_device_categories(settings["schematic_device_categories_text"])

if not DEVICE_CATEGORIES:
    forms.alert(
        u"Не заданы категории устройств для сопоставления схема-модель.\n\n"
        u"Заполните поле «Категории устройств для сопоставления» в настройках СКУД "
        u"(формат «имя:ключевые_слова», по одному на строку).",
        exitscript=True
    )


# ------------------------------------------------------------
# ТИПОВАЯ ГРУППА
# ------------------------------------------------------------

template_group_type = find_template_group_type(doc, TEMPLATE_GROUP_NAME)

if template_group_type is None:
    forms.alert(
        u"Не найден тип группы «{}» в проекте.\n\n"
        u"Соберите эталонную группу (устройства + рамка) и укажите её точное "
        u"имя в настройках СКУД.".format(TEMPLATE_GROUP_NAME),
        exitscript=True
    )


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

for controller in controllers:
    controller_addr = clean_text_value(get_string_param(controller, DEVICE_ADDRESS_PARAM))
    if not controller_addr:
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
        controllers_with_devices.append((controller, controller_addr, devices))

if not controllers_with_devices:
    forms.alert(u"Не найдено ни одного контроллера с адресом и подключёнными устройствами.", exitscript=True)


# ------------------------------------------------------------
# ТОЧКА ВСТАВКИ (клик на виде)
# ------------------------------------------------------------

try:
    base_point = uidoc.Selection.PickPoint(u"Укажите точку вставки структурной схемы")
except:
    forms.alert(u"Операция отменена.", exitscript=True)

insert_points = layout_points(base_point, len(controllers_with_devices), LAYOUT_GAP_FT, LAYOUT_PER_ROW)


# ------------------------------------------------------------
# РАЗМНОЖЕНИЕ ГРУППЫ + СОПОСТАВЛЕНИЕ + КОПИРОВАНИЕ АДРЕСА + ЛИНИИ
# ------------------------------------------------------------

groups_placed = 0
addresses_copied = 0
lines_created = 0
unmatched_report = []

with revit.Transaction("Build SKUD Schematic"):

    for (controller, controller_addr, devices), insert_pt in zip(controllers_with_devices, insert_points):
        group_instance = doc.Create.PlaceGroup(insert_pt, template_group_type)
        if group_instance is None:
            continue

        groups_placed += 1
        template_members = group_member_elements(doc, group_instance)

        pairs, unmatched_real = match_devices_by_category(template_members, devices, DEVICE_CATEGORIES)

        if unmatched_real:
            unmatched_report.append(
                u"Контроллер {} — не хватило схемных мест для {} устройств.".format(
                    controller_addr, len(unmatched_real)
                )
            )

        controller_schematic_el = None
        controller_categories = [c for c in DEVICE_CATEGORIES if c[0].lower() == u"контроллер"]
        if controller_categories:
            for el in template_members:
                if device_category_key(el, controller_categories):
                    controller_schematic_el = el
                    break

        if controller_schematic_el is not None:
            if set_param_any(controller_schematic_el, SCHEMATIC_ADDRESS_PARAM, controller_addr):
                addresses_copied += 1

        for schematic_el, real_el in pairs:
            real_addr = clean_text_value(get_string_param(real_el, DEVICE_ADDRESS_PARAM))
            if real_addr and set_param_any(schematic_el, SCHEMATIC_ADDRESS_PARAM, real_addr):
                addresses_copied += 1

        if controller_schematic_el is not None:
            controller_schematic_pt = get_point(controller_schematic_el)

            if controller_schematic_pt is not None:
                for schematic_el, _ in pairs:
                    device_pt = get_point(schematic_el)
                    if device_pt is None:
                        continue
                    try:
                        line = Line.CreateBound(controller_schematic_pt, device_pt)
                        doc.Create.NewDetailCurve(view, line)
                        lines_created += 1
                    except:
                        pass


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

if unmatched_report:
    from pyrevit import script as pyrevit_script
    output = pyrevit_script.get_output()
    output.print_md(u"### Не хватило схемных мест ({})".format(len(unmatched_report)))
    for line in unmatched_report:
        output.print_md(u"- {}".format(line))

forms.alert(
    u"Готово.\n\n"
    u"Контроллеров с адресом и устройствами: {}\n"
    u"Групп размещено: {}\n"
    u"Адресов скопировано: {}\n"
    u"Линий создано: {}\n"
    u"Предупреждений (не хватило схемных мест): {}\n\n"
    u"{}".format(
        len(controllers_with_devices),
        groups_placed,
        addresses_copied,
        lines_created,
        len(unmatched_report),
        u"Подробности — в окне вывода pyRevit." if unmatched_report else u""
    )
)
