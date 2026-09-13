# -*- coding: utf-8 -*-
__title__ = u"Цепи\nшлейфов СПС"
__doc__ = (
    u"Создаёт по одной электрической цепи на каждый шлейф СПС и подключает "
    u"её к своей панели. Шлейф определяется по адресу устройства вида "
    u"\"панель.шлейф.номер\" (например 3.1.2). Каждой созданной цепи сразу "
    u"проставляется режим траектории «Все устройства» и, по получившейся "
    u"длине (Revit Length x коэффициент запаса, округление до целого), "
    u"«Длина проводника» и «Способ прокладки»."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import fire_alarm_settings
from lowlife.fire_alarm_buttons import build_loop_circuits

fire_alarm_settings.set_system("SPS")

doc = revit.doc


def _open_settings():
    edited = fire_alarm_settings.get_settings_interactive(doc, keys=[
        "workset_param_name", "workset_filter_key",
        "designation_param", "device_address_param", "panel_designation_key",
        "excluded_device_keywords", "isolator_keyword",
        "circuit_panel_param", "circuit_number_param", "circuit_number_format",
        "circuit_system_type",
        "load_name_param", "cable_type_param", "wire_length_param", "length_coef",
        "route_method_param", "route_label_pipe_format",
        "wire_catalog_marker_param", "category_wire_type_ids",
    ])
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    _open_settings()
    script.exit()


settings = fire_alarm_settings.get_settings_silent()

fire_alarm_settings.require(settings, [
    "workset_param_name", "workset_filter_key",
    "designation_param", "device_address_param", "panel_designation_key",
    "circuit_panel_param", "circuit_number_param", "circuit_number_format",
    "circuit_system_type",
    "load_name_param",
])

build_loop_circuits(doc, settings)
