# -*- coding: utf-8 -*-
__title__ = "Цепь\n(общее)"
__doc__ = (
    "Строит произвольные электрические цепи «панель → устройства» по "
    "настройкам «Параметры (общее)» — ничего не зашито в код. Выберите "
    "панель и все устройства вместе, одним выбором (рамкой и/или кликами, "
    "без порядка; панель определяется автоматически по категории "
    "«Электрооборудование», среди выбранного она должна быть ровно одна).\n\n"
    "Тип цепи берётся из настроек (а если там пусто — по коннектору "
    "устройства, запасной вариант Data). Кабель (строка справочника) "
    "проставляется в параметр цепи из настроек, если он там выбран "
    "(необязательно). Параметру цепи «Имя нагрузки» присваивается значение, "
    "собранное из параметров подключаемого устройства по списку имён через "
    "разделитель (один параметр в списке = одиночный источник; для каждого "
    "имени сначала берётся параметр экземпляра, затем — типа).\n\n"
    "Режим — в настройках: либо отдельная цепь на каждое устройство (у "
    "каждой своё имя нагрузки), либо все устройства в одну общую цепь (имя "
    "нагрузки при этом не заполняется)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.manual_circuits import pick_panel_and_devices
from lowlife import generic_circuits_settings
from lowlife.generic_circuits_settings import get_settings_silent
from lowlife.generic_circuits import get_conductor_id, build_generic_circuits

doc = revit.doc
uidoc = revit.uidoc

settings = get_settings_silent()

generic_circuits_settings.require(settings, [
    "circuit_system_type", "conductor_param_name", "load_name_param"
])

conductor_id = get_conductor_id(doc, settings)

panel_el, device_els = pick_panel_and_devices(
    uidoc, doc,
    u"Выберите панель и устройства вместе — рамкой и/или кликами, "
    u"без порядка (подтвердите Enter/«Готово»)"
)

created, errors = build_generic_circuits(doc, panel_el, device_els, conductor_id, settings)

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
