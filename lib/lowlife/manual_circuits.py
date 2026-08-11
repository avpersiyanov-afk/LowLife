# -*- coding: utf-8 -*-
"""
Тело кнопок ручного построения цепей «панель -> устройства» на панелях
CircuitsSCS/CircuitsSKUD/CircuitsSPA: пользователь сам выбирает панель и
устройства, кнопка создаёт по одной отдельной цепи на каждое устройство
(аналог «home run» — без промежуточных узлов и адресации).

Логика не зависит от дисциплины — используется кнопками СКС/СКУД/СПА,
различаются только подписи и тип цепи по умолчанию (его в любом случае
можно поменять в диалоге при запуске).
"""

from Autodesk.Revit.DB.Electrical import ElectricalSystemType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.electrical_circuits import create_circuit


class _NotLinkedSelectionFilter(ISelectionFilter):
    """Отсекает элементы связанных файлов — PickObject/PickObjects иначе даёт их выбрать."""

    def AllowElement(self, elem):
        try:
            return not elem.Document.IsLinked
        except:
            return True

    def AllowReference(self, reference, position):
        return True


def pick_panel_and_devices(uidoc, doc, panel_prompt, devices_prompt):
    """
    Просит выбрать одну панель, затем несколько устройств. Останавливает
    скрипт (forms.alert exitscript), если пользователь отменил выбор (Esc)
    или не выбрал ни одного устройства.
    """
    selection_filter = _NotLinkedSelectionFilter()

    try:
        panel_ref = uidoc.Selection.PickObject(ObjectType.Element, selection_filter, panel_prompt)
        device_refs = uidoc.Selection.PickObjects(ObjectType.Element, selection_filter, devices_prompt)
    except OperationCanceledException:
        forms.alert(u"Операция отменена.", exitscript=True)
        return None, None

    device_els = [doc.GetElement(r) for r in device_refs]
    if not device_els:
        forms.alert(u"Не выбрано ни одного устройства.", exitscript=True)

    return doc.GetElement(panel_ref), device_els


def pick_system_type(default_name):
    """
    Даёт выбрать тип электрической цепи Revit из доступных в этой версии
    (значение по умолчанию для дисциплины — первым в списке). Останавливает
    скрипт, если пользователь отменил выбор.
    """
    available = sorted(a for a in dir(ElectricalSystemType) if not a.startswith("_"))

    if not available:
        return default_name

    if default_name in available:
        available = [default_name] + [a for a in available if a != default_name]

    selected = forms.SelectFromList.show(
        available,
        title=u"Тип электрической цепи (по умолчанию для дисциплины — первый в списке)",
        button_name=u"Выбрать",
        multiselect=False
    )

    if not selected:
        forms.alert(u"Операция отменена.", exitscript=True)

    return selected


def build_device_circuits(doc, panel_el, device_els, system_type_name, transaction_name):
    """
    Создаёт по одной электрической цепи на каждое устройство, подключая
    его напрямую к панели.

    Возвращает (created_count, errors) — errors это список текстов ошибок
    по устройствам, которые не удалось подключить.
    """
    created = 0
    errors = []

    with revit.Transaction(transaction_name):
        for dev in device_els:
            circuit, error = create_circuit(doc, panel_el, [dev], system_type_name)

            if circuit is None:
                errors.append(u"Устройство ID {}: {}".format(dev.Id.IntegerValue, error))
                continue

            created += 1

            if error:
                errors.append(u"Устройство ID {}: {}".format(dev.Id.IntegerValue, error))

    return created, errors


def run_manual_circuit_button(discipline_title, default_system_type):
    """Полный сценарий кнопки: выбор панели/устройств, типа цепи, создание."""
    doc = revit.doc
    uidoc = revit.uidoc

    panel_el, device_els = pick_panel_and_devices(
        uidoc, doc,
        u"Выберите панель {}".format(discipline_title),
        u"Выберите устройства {} (подтвердите Enter)".format(discipline_title)
    )

    system_type_name = pick_system_type(default_system_type)

    created, errors = build_device_circuits(
        doc, panel_el, device_els, system_type_name,
        u"Построение цепей {}".format(discipline_title)
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
