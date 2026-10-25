# -*- coding: utf-8 -*-
"""
Проверка и добавление привязок параметров СКУД из подключённого к проекту
файла общих параметров (ФОП).

Логика привязки (ensure_binding и т.п.) не специфична для СКС — переиспользуется
напрямую из scs_parameters.py. Здесь — только своя таблица параметров СКУД.
"""

from Autodesk.Revit.DB import BuiltInCategory
from lowlife.i18n import N_

from lowlife.scs_parameters import (
    ensure_binding, find_existing_binding, find_shared_definition,
    get_category, binding_has_category, INSTANCE, TYPE, TEXT, NUMBER, FOP, NATIVE
)

CAT_MARKERS = [BuiltInCategory.OST_GenericModel]

CAT_DEVICES_ONLY = [
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_DataDevices,
]

CAT_CONTROLLERS = [BuiltInCategory.OST_ElectricalEquipment]

CAT_DEVICES_AND_CONTROLLERS = CAT_DEVICES_ONLY + CAT_CONTROLLERS

CAT_CIRCUITS = [BuiltInCategory.OST_ElectricalCircuit]

# (ключ настроек, подпись, список ли значений через запятую, категории,
#  instance/type, тип данных для справки, источник)
PARAM_SPECS = [
    ("device_address_param", N_(u"Адрес устройства"),
        False, CAT_DEVICES_AND_CONTROLLERS, INSTANCE, TEXT, FOP),
    ("designation_param", N_(u"Обозначение (тип устройства)"),
        False, CAT_DEVICES_ONLY, TYPE, TEXT, FOP),
    ("controller_marking_param", N_(u"Маркировка контроллера"),
        False, CAT_CONTROLLERS, INSTANCE, TEXT, FOP),
    ("addr_param_name", N_(u"Адрес узла трассы"),
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("addr_prev_param_name", N_(u"Предыдущий адрес узла трассы"),
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("nearest_segment_param", N_(u"Ближайший узел маршрута (контроллер/устройство)"),
        False, CAT_DEVICES_AND_CONTROLLERS, INSTANCE, TEXT, FOP),
    ("cable_param_name", N_(u"Тип прокладки кабеля (узлы трассы)"),
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("wire_length_param", N_(u"Длина проводника"),
        False, CAT_CIRCUITS, INSTANCE, NUMBER, FOP),
    ("tray_length_param", N_(u"Длина проводника в лотке"),
        False, CAT_CIRCUITS, INSTANCE, NUMBER, FOP),
    ("pipe_length_param", N_(u"Длина проводника в трубе"),
        False, CAT_CIRCUITS, INSTANCE, NUMBER, FOP),
    ("route_method_param", N_(u"Способ прокладки"),
        False, CAT_CIRCUITS, INSTANCE, TEXT, FOP),
    ("circuit_route_param", N_(u"Маршрут цепи"),
        False, CAT_CIRCUITS, INSTANCE, TEXT, FOP),
    ("segment_loads_param", N_(u"Список цепей (узел маршрута)"),
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("device_marking_param", N_(u"Марка устройства"),
        False, CAT_DEVICES_ONLY, INSTANCE, TEXT, FOP),
    ("schematic_address_param", N_(u"Адрес устройства (схема)"),
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
]
