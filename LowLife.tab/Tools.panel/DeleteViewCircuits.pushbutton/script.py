# -*- coding: utf-8 -*-

__title__ = "Удалить\nцепи на виде"
__doc__ = (
    u"Удаляет все электрические цепи, у которых хотя бы один элемент "
    u"(устройство или панель-источник) виден на активном виде.\n\n"
    u"Полезно для очистки тестовых/лишних цепей — например, оставшихся от "
    u"ручной проверки в Revit UI или от кнопки «Цепи изолятор-устройства». "
    u"Revit не даёт добавить элемент, уже состоящий в одной цепи, ещё в "
    u"одну (ошибка electComponents при построении цепей шлейфов/СКС/СКУД), "
    u"поэтому такие лишние цепи нужно сначала удалить.\n\n"
    u"Перед удалением показывает список цепей (по «Номеру цепи», если "
    u"задан) в окне вывода и спрашивает подтверждение."
)
__author__ = "Pipers"

from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory

from pyrevit import revit, forms, script as pyrevit_script

doc = revit.doc
view = doc.ActiveView
output = pyrevit_script.get_output()


def circuit_label(circuit):
    try:
        p = circuit.LookupParameter(u"Номер цепи")
        if p and p.HasValue:
            value = p.AsString()
            if value:
                return value
    except:
        pass
    return u"без номера"


try:
    visible_ids = set(
        el.Id.IntegerValue
        for el in FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType().ToElements()
    )
except Exception as ex:
    forms.alert(u"Не удалось получить элементы активного вида: {}".format(ex), exitscript=True)

circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()

to_delete = []

for circuit in circuits:
    member_ids = set()

    try:
        for m in circuit.Elements:
            member_ids.add(m.Id.IntegerValue)
    except:
        pass

    try:
        if circuit.BaseEquipment:
            member_ids.add(circuit.BaseEquipment.Id.IntegerValue)
    except:
        pass

    if member_ids & visible_ids:
        to_delete.append(circuit)

if not to_delete:
    forms.alert(u"На активном виде не найдено устройств, входящих в электрические цепи.", exitscript=True)

output.print_md(u"### Цепи для удаления ({})".format(len(to_delete)))
for c in to_delete:
    output.print_md(u"- «{}» (ID {})".format(circuit_label(c), c.Id.IntegerValue))

confirmed = forms.alert(
    u"Будет удалено цепей: {}\n\nПодробности — в окне вывода pyRevit.\n\nПродолжить?".format(len(to_delete)),
    ok=False, yes=True, no=True
)

if confirmed:
    deleted = 0
    errors = []

    with revit.Transaction(u"Удалить цепи на виде"):
        for c in to_delete:
            try:
                doc.Delete(c.Id)
                deleted += 1
            except Exception as ex:
                errors.append(u"ID {}: {}".format(c.Id.IntegerValue, ex))

    if errors:
        output.print_md(u"### Ошибки удаления ({})".format(len(errors)))
        for line in errors:
            output.print_md(u"- {}".format(line))

    forms.alert(u"Готово.\n\nУдалено цепей: {}\nОшибок: {}".format(deleted, len(errors)))
