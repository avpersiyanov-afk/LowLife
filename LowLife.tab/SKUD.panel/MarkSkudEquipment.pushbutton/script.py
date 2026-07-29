# -*- coding: utf-8 -*-
__title__ = "Маркировка СКУД"
__doc__ = (
    "Записывает марку устройств (адрес) и список цепей, проходящих через "
    "каждый узел маршрута СКУД (по уже вычисленному маршруту цепи)."
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
from lowlife.scs_circuits import norm, clean_text_value, make_load_name, build_segment_list_text
from lowlife.skud import is_controller
from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent

doc = revit.doc


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param", "device_address_param", "device_marking_param",
    "route_type_id", "riser_type_id",
    "circuit_route_param", "segment_loads_param"
])

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]

CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]
DEVICE_MARKING_PARAM = settings["device_marking_param"]

ADDR_PARAM = settings["addr_param_name"]
ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))

CIRCUIT_ROUTE_PARAM = settings["circuit_route_param"]
SEGMENT_LOADS_PARAM = settings["segment_loads_param"]


# ------------------------------------------------------------
# УЗЛЫ ТРАССЫ СКУД (по адресу, для записи "Список цепей")
# ------------------------------------------------------------

segments_by_addr = {}

all_generic = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType() \
    .ToElements()

for e in all_generic:
    if e.GetTypeId() not in (ROUTE_TYPE_ID, RISER_TYPE_ID):
        continue

    sid = clean_text_value(get_string_param(e, ADDR_PARAM))
    if not sid:
        continue

    segments_by_addr[sid] = e


# ------------------------------------------------------------
# КОНТРОЛЛЕРЫ И ЦЕПИ
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
# МАРКИРОВКА УСТРОЙСТВ + СПИСОК ЦЕПЕЙ ПО УЗЛАМ
# ------------------------------------------------------------

devices_marked = 0
no_device = 0
segment_info_map = {}

with revit.Transaction("Mark SKUD Equipment"):

    for controller in controllers:
        controller_name = norm(controller.Name)
        controller_circuits = circuits_by_controller_name.get(controller_name, [])

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

            device_addr = clean_text_value(get_string_param(dev, DEVICE_ADDRESS_PARAM))
            if device_addr and set_param_any(dev, DEVICE_MARKING_PARAM, device_addr):
                devices_marked += 1

            route_text = clean_text_value(get_string_param(c, CIRCUIT_ROUTE_PARAM))
            if not route_text:
                continue

            path = [norm(p) for p in route_text.split(u"->")]
            path = [p for p in path if p]

            circuit_label = clean_text_value(norm(c.Name)) or u"Circuit {}".format(c.Id.IntegerValue)

            for sid in path:
                info = segment_info_map.setdefault(sid, {"loads": set(), "fo": 0, "utp": 0})
                info["loads"].add(circuit_label)

    segments_written = 0
    for sid, info in segment_info_map.items():
        el = segments_by_addr.get(sid)
        if not el:
            continue
        value = build_segment_list_text(info["loads"], info["fo"], info["utp"])
        if set_param_any(el, SEGMENT_LOADS_PARAM, value):
            segments_written += 1


forms.alert(
    u"Готово.\n\n"
    u"Контроллеров: {}\n"
    u"Устройств маркировано: {}\n"
    u"Нет устройства в цепи: {}\n"
    u"Узлов со списком цепей записано: {}".format(
        len(controllers),
        devices_marked,
        no_device,
        segments_written
    )
)
