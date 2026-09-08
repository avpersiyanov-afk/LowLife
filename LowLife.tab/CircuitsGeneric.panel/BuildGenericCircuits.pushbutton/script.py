# -*- coding: utf-8 -*-
__title__ = u"Цепь\n(общее)"
__doc__ = (
    u"Строит произвольные электрические цепи «панель → устройства» по "
    u"настройкам «Параметры цепей (общее)» — ничего не зашито в код. Выберите "
    u"панель и все устройства вместе, одним выбором (рамкой и/или кликами, "
    u"без порядка; панель определяется автоматически по категории "
    u"«Электрооборудование», среди выбранного она должна быть ровно одна). "
    u"Выбор отфильтрован — нельзя случайно захватить аннотации, связанные "
    u"файлы, оси, уровни, текст, линии детализации и обобщённые модели.\n\n"
    u"Тип цепи берётся из настроек (а если там пусто — по коннектору "
    u"устройства, запасной вариант Data). Кабель (строка справочника) "
    u"проставляется в параметр цепи из настроек, если он там выбран "
    u"(необязательно). Параметру цепи «Имя нагрузки» присваивается значение, "
    u"собранное из параметров подключаемого устройства по списку имён через "
    u"разделитель (один параметр в списке = одиночный источник; для каждого "
    u"имени сначала берётся параметр экземпляра, затем — типа).\n\n"
    u"Режим — в настройках: либо отдельная цепь на каждое устройство (у "
    u"каждой своё имя нагрузки), либо все устройства в одну общую цепь (имя "
    u"нагрузки при этом не заполняется)."
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
    u"без порядка (подтвердите Enter/«Готово»)",
    strict=True
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
