# -*- coding: utf-8 -*-
__title__ = "Цепи\nизолятор-устройства СПС"
__doc__ = (
    "Строит электрические цепи между изолятором и выбранными устройствами "
    "пожарной сигнализации: выберите устройства и изолятор («Электрооборудование») "
    "вместе одним выбором — среди выбранного должен быть ровно один изолятор. "
    "После подтверждения (Enter/«Готово») цепи строятся сразу, и кнопка тут же "
    "предлагает выбрать следующий набор — повторный запуск кнопки не нужен, "
    "выбор заканчивается по Esc. "
    "Устройства ручного пуска (с «ручной» в имени типа — ИПР) получают "
    "каждое свою отдельную цепь, остальные выбранные устройства — одну "
    "общую. У изолятора не может быть больше 2 цепей — если по этим "
    "правилам получилось бы больше, кнопка ничего не создаёт для этого "
    "набора и показывает предупреждение."
)
__author__ = "Pipers"

from pyrevit import revit, forms

from lowlife import fire_alarm_settings
from lowlife.fire_alarm_isolator_circuits import (
    pick_devices_and_isolator, build_isolator_device_circuits
)

fire_alarm_settings.set_system("SPS")

doc = revit.doc
uidoc = revit.uidoc

settings = fire_alarm_settings.get_settings_silent()

fire_alarm_settings.require(settings, [
    "designation_param", "device_address_param",
    "circuit_panel_param", "load_name_param", "circuit_system_type",
])

all_created = []
all_errors = []

device_els, isolator_el = pick_devices_and_isolator(uidoc, doc)

while device_els is not None:
    created, error = build_isolator_device_circuits(doc, device_els, isolator_el, settings)
    all_created.extend(created)
    if error:
        all_errors.append(error)

    device_els, isolator_el = pick_devices_and_isolator(uidoc, doc)

if not all_created and not all_errors:
    forms.alert(u"Операция отменена. Цепи не созданы.")
elif all_errors and not all_created:
    forms.alert(u"\n\n".join(all_errors), exitscript=True)
elif all_errors:
    forms.alert(u"Создано цепей: {}. Есть ошибки:\n\n{}".format(len(all_created), u"\n\n".join(all_errors)))
else:
    forms.alert(u"Готово. Создано цепей: {}.".format(len(all_created)))
