# -*- coding: utf-8 -*-
__title__ = "Цепи\nизолятор-устройства СПС"
__doc__ = (
    "Строит электрическую цепь между изолятором и выбранными устройствами "
    "пожарной сигнализации: сначала выберите устройства (только категория "
    "«Пожарная сигнализация»), затем изолятор (только «Электрооборудование»). "
    "Устройства ручного пуска (с «ручной» в имени типа — ИПР) получают "
    "каждое свою отдельную цепь, остальные выбранные устройства — одну "
    "общую. У изолятора не может быть больше 2 цепей — если по этим "
    "правилам получилось бы больше, кнопка ничего не создаёт и показывает "
    "предупреждение."
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

device_els, isolator_el = pick_devices_and_isolator(uidoc, doc)

created, error = build_isolator_device_circuits(doc, device_els, isolator_el, settings)

if error and not created:
    forms.alert(error, exitscript=True)
elif error:
    forms.alert(u"Часть цепей создана, но есть ошибки:\n\n{}".format(error))
else:
    forms.alert(u"Готово. Создано цепей: {}.".format(len(created)))
