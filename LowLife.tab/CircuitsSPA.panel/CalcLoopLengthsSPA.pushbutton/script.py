# -*- coding: utf-8 -*-
__title__ = u"Длины\nшлейфов СПА"
__doc__ = (
    u"Считает длину каждого шлейфа СПА по координатам устройств (по катетам, "
    u"не по кратчайшему расстоянию), записывает её в цепь, маркирует устройства "
    u"и проставляет им предыдущий адрес — та же логика, что у «Длины шлейфов СПС».\n\n"
    u"Переход между этажами: если у соседних по адресу устройств разный этаж и в "
    u"настройках задано «Ключевое слово стояка», участок считается не напрямую, а "
    u"через ближайший стояк на каждом из двух этажей (устройство -> стояк -> стояк "
    u"-> устройство). Без стояка (или пока он не найден) — как раньше, напрямую.\n\n"
    u"Кольцевой шлейф: если в настройках «Кольцевой шлейф» = «да», магистраль "
    u"(без веток изоляторов — они не удваиваются) замыкается обратно на панель: "
    u"добавляется участок от последнего устройства магистрали до ближайшего стояка "
    u"на его этаже, а если стояк не найден — прямой участок до панели."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import fire_alarm_settings
from lowlife.fire_alarm_buttons import calc_loop_lengths

fire_alarm_settings.set_system("SPA")

doc = revit.doc


def _open_settings():
    edited = fire_alarm_settings.get_settings_interactive(doc, keys=[
        "workset_param_name", "workset_filter_key",
        "designation_param", "device_address_param", "panel_designation_key",
        "excluded_device_keywords",
        "circuit_number_param", "circuit_number_format",
        "length_coef", "wire_length_param", "isolator_keyword",
        "level_param_name", "riser_keyword", "ring_loop",
        "addr_prev_param_name", "device_marking_param",
        "pipe_length_param", "tray_length_param",
        "route_method_param", "route_label_pipe_format",
        "circuit_route_param", "wire_mark_param", "wire_line_family_filter",
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
    "circuit_number_param", "circuit_number_format",
    "length_coef", "wire_length_param",
])

calc_loop_lengths(doc, settings)
