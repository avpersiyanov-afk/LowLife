# -*- coding: utf-8 -*-

__title__ = "Удалить\nцепи"
__doc__ = "Удаляет все электрические цепи для выбранного оборудования."
__author__ = "Pipers"

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB.Electrical import ElectricalSystem
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType

from pyrevit import revit, forms

from lowlife.cable_schedule import ElectricalEquipmentSelectionFilter

doc = revit.doc
uidoc = revit.uidoc

try:
    refs = uidoc.Selection.PickObjects(
        ObjectType.Element, ElectricalEquipmentSelectionFilter(),
        u"Выберите электрооборудование для удаления цепей"
    )
    equip_ids = set(r.ElementId for r in refs)

    circuits = [
        s for s in FilteredElementCollector(doc).OfClass(ElectricalSystem).ToElements()
        if (s.BaseEquipment is not None and s.BaseEquipment.Id in equip_ids)
        or any(e.Id in equip_ids for e in s.Elements)
    ]

    if not circuits:
        forms.alert(u"У выбранного оборудования не найдено электрических цепей.", title=u"Удаление цепей", exitscript=True)

    if not forms.alert(
        u"Будет удалено цепей: {}\n\nПродолжить?".format(len(circuits)),
        title=u"Удаление цепей", yes=True, no=True
    ):
        forms.alert(u"Отменено.", exitscript=True)

    deleted_count = 0
    failed_count = 0

    with revit.Transaction(u"Удаление электрических цепей"):
        for circuit in circuits:
            try:
                doc.Delete(circuit.Id)
                deleted_count += 1
            except:
                failed_count += 1

    message = u"Удалено цепей: {}".format(deleted_count)
    if failed_count > 0:
        message += u"\nНе удалось удалить: {}".format(failed_count)

    forms.alert(message, title=u"Удаление цепей")

except OperationCanceledException:
    pass
