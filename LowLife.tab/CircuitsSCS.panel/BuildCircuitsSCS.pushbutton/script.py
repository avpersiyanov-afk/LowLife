# -*- coding: utf-8 -*-
__title__ = "Цепи\nСКС"
__doc__ = (
    "Строит электрические цепи СКС между панелью и устройствами. Выберите "
    "панель и все устройства вместе, одним выбором — рамкой и/или кликами, "
    "без определённого порядка (панель определяется автоматически по "
    "категории «Электрооборудование», среди выбранного должна быть ровно "
    "одна). На каждое устройство создаётся отдельная электрическая цепь, "
    "подключённая напрямую к панели («домашний прогон», без промежуточных "
    "узлов и адресации). Тип цепи определяется автоматически по "
    "электрическому коннектору устройства (как при ручном создании цепи в "
    "Revit), Data — только запасной вариант, если определить не удалось. "
    "Проводнику каждой цепи проставляется значение, выбранное заранее в "
    "настройках («Параметры СКС», раздел «Проводник для цепей СКС»), а "
    "параметру «Имя нагрузки» — «Обозначение» типа устройства + «Адрес "
    "устройства»."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.manual_circuits import pick_panel_and_devices
from lowlife.scs_manual_circuits import get_conductor_id, build_scs_manual_circuits
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent

doc = revit.doc
uidoc = revit.uidoc

settings = get_settings_silent()

scs_settings.require(settings, [
    "conductor_type_id", "type_code_param", "device_address_param", "load_name_param"
])

conductor_id = get_conductor_id(doc, settings)

panel_el, device_els = pick_panel_and_devices(
    uidoc, doc,
    u"Выберите панель и устройства СКС вместе — рамкой и/или кликами, "
    u"без порядка (подтвердите Enter/«Готово»)"
)

created, errors = build_scs_manual_circuits(doc, panel_el, device_els, conductor_id, settings)

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
