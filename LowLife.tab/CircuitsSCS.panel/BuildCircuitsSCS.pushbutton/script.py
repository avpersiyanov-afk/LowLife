# -*- coding: utf-8 -*-
__title__ = "Цепи\nСКС"
__doc__ = (
    "Строит электрические цепи СКС между панелью и устройствами. Нажмите "
    "кнопку, выберите тип проводника (кабеля) из справочника — он "
    "проставится в параметр «Проводник» всех созданных цепей, — затем "
    "выберите панель, затем выберите все устройства. На каждое устройство "
    "создаётся отдельная электрическая цепь типа Data, подключённая "
    "напрямую к панели («домашний прогон», без промежуточных узлов и "
    "адресации). Тип цепи всегда Data — у СКС других не бывает."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script as pyrevit_script

from lowlife import scs_settings
from lowlife.manual_circuits import pick_panel_and_devices
from lowlife.scs_manual_circuits import pick_wire_type, build_scs_manual_circuits

doc = revit.doc
uidoc = revit.uidoc

settings = scs_settings.get_settings_silent()

scs_settings.require(settings, ["cable_type_param", "wire_catalog_marker_param"])

wire_type_el = pick_wire_type(doc, settings["wire_catalog_marker_param"])

panel_el, device_els = pick_panel_and_devices(
    uidoc, doc,
    u"Выберите панель СКС",
    u"Выберите устройства СКС (подтвердите Enter)"
)

created, errors = build_scs_manual_circuits(
    doc, panel_el, device_els, wire_type_el, settings["cable_type_param"]
)

if errors:
    output = pyrevit_script.get_output()
    output.print_md(u"### Ошибки ({})".format(len(errors)))
    for line in errors[:200]:
        output.print_md(u"- {}".format(line))

forms.alert(
    u"Готово.\n\nУстройств выбрано: {}\nЦепей создано: {}\nОшибок: {}\n\n{}".format(
        len(device_els), created, len(errors),
        u"Подробности — в окне вывода pyRevit." if errors else u""
    )
)
