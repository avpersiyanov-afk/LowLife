# -*- coding: utf-8 -*-
__title__ = "Помещение\nточек прохода"
__doc__ = (
    "Проставляет всем устройствам СКУД параметр имени помещения (как "
    "«Помещение из связи» в СПС/СОТ), но по каждой точке прохода берёт "
    "ОДНО значение — самое частое среди её устройств — и назначает его "
    "всем устройствам этой точки прохода. Контроллерам — помещение "
    "индивидуально. Имена параметров берутся из «Параметры помещений»."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms, script as pyrevit_script

from lowlife.params import set_param_any
from lowlife.skud import collect_controller_devices
from lowlife.skud_schematic import passage_points_of
from lowlife.skud_room_info import assign_rooms_by_passage_point, device_room_value
from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent
from lowlife import room_info_settings

doc = revit.doc
output = pyrevit_script.get_output()

settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param", "device_address_param",
])

room_settings = room_info_settings.load_saved_values()
room_info_settings.require(room_settings, ["target_param_name", "room_number_param_name"])

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]
PASSAGE_POINT_PARAM = settings.get("passage_point_param") or u""

TARGET_PARAM = room_settings["target_param_name"]
ROOM_NUMBER_PARAM = room_settings["room_number_param_name"]


# ------------------------------------------------------------
# СБОР КОНТРОЛЛЕРОВ И УСТРОЙСТВ
# ------------------------------------------------------------

controller_devices = collect_controller_devices(
    doc, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD,
    CIRCUIT_PANEL_PARAM, EXCLUDED_DEVICE_KEYWORDS
)

if not controller_devices:
    forms.alert(u"Не найдено ни одного контроллера СКУД.", exitscript=True)

passage_point_device_lists = []
controllers_with_room = []
skipped_controllers = 0

for controller, devices in controller_devices:
    if not devices:
        skipped_controllers += 1
        continue

    controllers_with_room.append(controller)
    for _key, pp_devices in passage_points_of(
        devices, PASSAGE_POINT_PARAM, DEVICE_ADDRESS_PARAM
    ).items():
        passage_point_device_lists.append(pp_devices)

if not passage_point_device_lists:
    forms.alert(u"Ни у одного контроллера нет подключённых устройств.", exitscript=True)


# ------------------------------------------------------------
# ЗАПИСЬ
# ------------------------------------------------------------

controllers_written = 0

with revit.Transaction("Assign SKUD rooms"):
    results = assign_rooms_by_passage_point(
        doc, passage_point_device_lists, TARGET_PARAM, ROOM_NUMBER_PARAM
    )

    for controller in controllers_with_room:
        if controller.LookupParameter(TARGET_PARAM) is None:
            continue
        value = device_room_value(doc, controller, ROOM_NUMBER_PARAM)
        if value and set_param_any(controller, TARGET_PARAM, value):
            controllers_written += 1


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

written_pp = [r for r in results if r[3] == "written"]
no_room_pp = [r for r in results if r[3] == "no_room"]
devices_written = sum(r[2] for r in written_pp)

if no_room_pp:
    output.print_md(u"### Точки прохода без помещения ({})".format(len(no_room_pp)))
    output.print_md(u"Ни у одного устройства точки прохода не нашлось помещения в связях.")

forms.alert(
    u"Готово.\n\n"
    u"Точек прохода обработано: {}\n"
    u"Точек прохода с помещением: {}\n"
    u"Устройствам записано: {}\n"
    u"Контроллерам записано: {}\n"
    u"Точек прохода без помещения: {}\n"
    u"Контроллеров без устройств (пропущено): {}".format(
        len(results),
        len(written_pp),
        devices_written,
        controllers_written,
        len(no_room_pp),
        skipped_controllers,
    )
)
