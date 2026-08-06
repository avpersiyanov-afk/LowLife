# -*- coding: utf-8 -*-

__title__ = "Проложить\nпо трассе"
__doc__ = (
    "Прокладывает кабель по кабеленесущим системам (алгоритм Дейкстры). "
    "Сначала выделите трассу, затем запустите и выберите оборудование."
)
__author__ = "Pipers"

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    BuiltInCategory, CableTray, Conduit, FamilyInstance
)
from Autodesk.Revit.DB.Mechanical import Duct
from Autodesk.Revit.DB.Electrical import ElectricalSystem
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType

from pyrevit import revit, forms

from lowlife.cable_schedule import (
    ElectricalEquipmentSelectionFilter, Dijkstra, order_xyz_list,
    save_route_metadata, get_category_id,
)

doc = revit.doc
uidoc = revit.uidoc

# Соответствует оригинальному C#-плагину: CableTrayFitting, ConduitFitting,
# DuctCurves (не DuctFitting) — так задано в исходном FittingCategories.
FITTING_CATEGORIES = set([
    int(BuiltInCategory.OST_CableTrayFitting),
    int(BuiltInCategory.OST_ConduitFitting),
    int(BuiltInCategory.OST_DuctCurves),
])


class CableCarrierFilter(ISelectionFilter):
    def AllowElement(self, elem):
        if isinstance(elem, (CableTray, Conduit, Duct)):
            return True
        if isinstance(elem, FamilyInstance) and elem.Category is not None:
            return get_category_id(elem) in FITTING_CATEGORIES
        return False

    def AllowReference(self, reference, position):
        return True


try:
    selected_ids = list(uidoc.Selection.GetElementIds())
    carrier_filter = CableCarrierFilter()

    trace_elements = [
        e for e in (doc.GetElement(eid) for eid in selected_ids)
        if carrier_filter.AllowElement(e)
    ]

    if not trace_elements:
        forms.alert(
            u"В текущем выделении не найдено элементов трассы.\n\n"
            u"Выделите лотки, короба или воздуховоды перед запуском команды.",
            title=u"Прокладка кабеля", exitscript=True
        )

    equip_refs = uidoc.Selection.PickObjects(
        ObjectType.Element, ElectricalEquipmentSelectionFilter(),
        u"Трасса: {} эл. Выберите электрооборудование".format(len(trace_elements))
    )
    equip_ids = set(r.ElementId for r in equip_refs)

    routed_count = 0
    skipped_count = 0

    for equip_id in equip_ids:
        circuits = [
            s for s in FilteredElementCollector(doc).OfClass(ElectricalSystem).ToElements()
            if s.BaseEquipment is not None and any(e.Id == equip_id for e in s.Elements)
        ]

        for circuit in circuits:
            try:
                member_ids = set(e.Id for e in circuit.Elements)
                if circuit.BaseEquipment is not None:
                    member_ids.add(circuit.BaseEquipment.Id)

                trace_points = [e for e in trace_elements if e.Id not in member_ids]

                dijkstra = Dijkstra(doc, circuit, trace_points, 10.0)
                path = dijkstra.get_path()

                if not path or len(path) < 2:
                    skipped_count += 1
                    continue

                circuit_path = order_xyz_list(path)

                with revit.Transaction(u"Прокладка кабеля по трассе"):
                    circuit.SetCircuitPath(list(circuit_path))

                with revit.Transaction(u"Сохранение данных цепи"):
                    save_route_metadata(doc, circuit, dijkstra)

                routed_count += 1
            except:
                skipped_count += 1

    forms.alert(
        u"Проложено цепей: {}\nПропущено (нет пути): {}".format(routed_count, skipped_count),
        title=u"Прокладка кабеля"
    )

except OperationCanceledException:
    pass
