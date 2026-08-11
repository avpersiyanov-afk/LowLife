# -*- coding: utf-8 -*-
__title__ = "Цепи\nСКС"
__doc__ = (
    "Строит электрические цепи СКС между панелью и устройствами. Нажмите "
    "кнопку, выберите проводник (кабель) из списка — он проставится в "
    "параметр «Проводник» всех созданных цепей, — затем выберите панель, "
    "затем выберите все устройства. На каждое устройство создаётся "
    "отдельная электрическая цепь типа Data, подключённая напрямую к "
    "панели («домашний прогон», без промежуточных узлов и адресации). Тип "
    "цепи всегда Data — у СКС других не бывает. Список проводников — это "
    "варианты, уже выбранные хотя бы в одной цепи проекта (Revit не даёт "
    "получить список строк справочника кабелей напрямую)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.manual_circuits import pick_panel_and_devices
from lowlife.scs_manual_circuits import pick_conductor, build_scs_manual_circuits

doc = revit.doc
uidoc = revit.uidoc

conductor_id = pick_conductor(doc)

panel_el, device_els = pick_panel_and_devices(
    uidoc, doc,
    u"Выберите панель СКС",
    u"Выберите устройства СКС (подтвердите Enter)"
)

created, errors = build_scs_manual_circuits(doc, panel_el, device_els, conductor_id)

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
