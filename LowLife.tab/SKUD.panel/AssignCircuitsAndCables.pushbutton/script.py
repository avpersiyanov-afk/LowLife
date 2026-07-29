# -*- coding: utf-8 -*-
__title__ = "Цепи и кабели"
__doc__ = (
    "Находит контроллеры СКУД и их цепи, назначает подключённым устройствам "
    "адрес по маске \"адрес контроллера.N\", выбирает тип кабеля по словарю "
    "\"тип устройства -> тип кабеля\", пишет имя нагрузки и маркирует контроллеры."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.params import get_string_param, set_param_any
from lowlife.scs import is_excluded_device
from lowlife.scs_circuits import norm, clean_text_value, make_load_name
from lowlife.skud import is_controller, parse_device_cable_map, pick_cable_type
from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent

doc = revit.doc


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword",
    "workset_param_name", "circuit_panel_param",
    "device_address_param", "type_code_param", "load_name_param",
    "controller_marking_param", "cable_type_param", "device_cable_map_text"
])

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]

CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
CIRCUIT_NAME_TYPE_PARAM = settings.get("circuit_name_type_param")
DEVICE_ADDRESS_PARAM = settings["device_address_param"]
TYPE_CODE_PARAM = settings["type_code_param"]
LOAD_NAME_PARAM = settings["load_name_param"]
CONTROLLER_MARKING_PARAM = settings["controller_marking_param"]
CABLE_TYPE_PARAM = settings["cable_type_param"]

CABLE_MAP_PAIRS = parse_device_cable_map(settings["device_cable_map_text"])

if not CABLE_MAP_PAIRS:
    forms.alert(
        u"Словарь «тип устройства : тип кабеля» пуст или не удалось разобрать.\n\n"
        u"Заполните поле в формате «ключевое_слово:тип_кабеля», по одному на строку, "
        u"в настройках СКУД.",
        exitscript=True
    )


# ------------------------------------------------------------
# КОНТРОЛЛЕРЫ
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


# ------------------------------------------------------------
# ОСНОВНОЙ ПРОХОД
# ------------------------------------------------------------

processed_controllers = 0
processed_circuits = 0
no_device = 0
no_controller_addr = 0
addresses_written = 0
load_names_written = 0
cables_written = 0
markings_written = 0
no_cable_match = []

with revit.Transaction("Assign SKUD Circuits And Cables"):

    for controller in sorted(controllers, key=lambda x: (norm(x.Name) or u"", x.Id.IntegerValue)):
        controller_name = norm(controller.Name)

        controller_addr = clean_text_value(get_string_param(controller, DEVICE_ADDRESS_PARAM))
        if not controller_addr:
            no_controller_addr += 1
            continue

        if set_param_any(controller, CONTROLLER_MARKING_PARAM, controller_addr):
            markings_written += 1

        processed_controllers += 1

        controller_circuits = circuits_by_controller_name.get(controller_name, [])
        controller_circuits.sort(key=lambda x: (norm(x.Name) or u"", x.Id.IntegerValue))

        device_index = 1

        for c in controller_circuits:
            try:
                raw_devs = [x for x in c.Elements if x.Id != controller.Id]
            except:
                continue

            normal_devs = [d for d in raw_devs if not is_excluded_device(d, EXCLUDED_DEVICE_KEYWORDS)]

            if not normal_devs:
                no_device += 1
                continue

            dev = normal_devs[0]
            processed_circuits += 1

            device_addr = u"{}.{}".format(controller_addr, device_index)
            device_index += 1

            if set_param_any(dev, DEVICE_ADDRESS_PARAM, device_addr):
                addresses_written += 1

            type_el = None
            try:
                type_el = doc.GetElement(dev.GetTypeId())
            except:
                pass

            type_code = clean_text_value(get_string_param(type_el, TYPE_CODE_PARAM)) if type_el else None
            load_name = make_load_name(type_code, device_addr)

            if load_name and set_param_any(c, LOAD_NAME_PARAM, load_name):
                load_names_written += 1

            cable_value = pick_cable_type(dev, CABLE_MAP_PAIRS)

            if cable_value:
                if set_param_any(c, CABLE_TYPE_PARAM, cable_value):
                    cables_written += 1
            else:
                no_cable_match.append(
                    u"Цепь «{}» (контроллер {}, устройство ID {}) — не найден тип кабеля по словарю.".format(
                        norm(c.Name) or c.Id.IntegerValue, controller_name, dev.Id.IntegerValue
                    )
                )


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

if no_cable_match:
    from pyrevit import script as pyrevit_script
    output = pyrevit_script.get_output()
    output.print_md(u"### Цепи без найденного кабеля по словарю ({})".format(len(no_cable_match)))
    for line in no_cable_match:
        output.print_md(u"- {}".format(line))

forms.alert(
    u"Готово.\n\n"
    u"Контроллеров найдено: {}\n"
    u"Обработано контроллеров (есть адрес): {}\n"
    u"Нет адреса у контроллера: {}\n\n"
    u"Обработано цепей: {}\n"
    u"Нет устройства в цепи: {}\n\n"
    u"Адресов устройств записано: {}\n"
    u"Имён нагрузки записано: {}\n"
    u"Типов кабеля записано: {}\n"
    u"Маркировок контроллеров записано: {}\n"
    u"Не найден кабель по словарю: {}\n\n"
    u"{}".format(
        len(controllers),
        processed_controllers,
        no_controller_addr,
        processed_circuits,
        no_device,
        addresses_written,
        load_names_written,
        cables_written,
        markings_written,
        len(no_cable_match),
        u"Подробности — в окне вывода pyRevit." if no_cable_match else u""
    )
)
