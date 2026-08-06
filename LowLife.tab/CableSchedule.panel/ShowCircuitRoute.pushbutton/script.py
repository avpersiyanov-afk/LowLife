# -*- coding: utf-8 -*-

__title__ = "Показать\nтрассу"
__doc__ = (
    "Временно изолирует в активном виде трассу цепи выбранного прибора. "
    "Для сброса: кнопка «очков» в строке вида → «Сбросить временное скрытие/изоляцию»."
)
__author__ = "Pipers"

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from System.Collections.Generic import IList, List
from Autodesk.Revit.DB import ElementId, UnitTypeId, XYZ, Transaction
from Autodesk.Revit.DB.Electrical import ElectricalSystem
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType

from pyrevit import revit, forms

from lowlife.cable_schedule import ElectricalEquipmentSelectionFilter, get_route_entity

doc = revit.doc
uidoc = revit.uidoc


def collect_segment_ids(route_entity):
    seg_elements = list(route_entity.Get[IList[ElementId]]("segmentWayElement"))
    seg_lengths = list(route_entity.Get[IList[float]]("segmentWayLength", UnitTypeId.Millimeters))

    result = set()
    for i in range(len(seg_elements)):
        eid = seg_elements[i]
        if seg_lengths[i] > 0.0 and eid != ElementId.InvalidElementId and doc.GetElement(eid) is not None:
            result.add(eid)
    return result


def zoom_to_elements(ids):
    bbox_min = None
    bbox_max = None

    for eid in ids:
        elem = doc.GetElement(eid)
        bbox = elem.get_BoundingBox(None) if elem else None
        if bbox is None:
            continue

        if bbox_min is None:
            bbox_min, bbox_max = bbox.Min, bbox.Max
        else:
            bbox_min = XYZ(min(bbox_min.X, bbox.Min.X), min(bbox_min.Y, bbox.Min.Y), min(bbox_min.Z, bbox.Min.Z))
            bbox_max = XYZ(max(bbox_max.X, bbox.Max.X), max(bbox_max.Y, bbox.Max.Y), max(bbox_max.Z, bbox.Max.Z))

    if bbox_min is None:
        return

    margin = XYZ(1, 1, 1)
    for uiview in uidoc.GetOpenUIViews():
        if uiview.ViewId == doc.ActiveView.Id:
            uiview.ZoomAndCenterRectangle(bbox_min - margin, bbox_max + margin)
            break


try:
    ref = uidoc.Selection.PickObject(
        ObjectType.Element, ElectricalEquipmentSelectionFilter(),
        u"Выберите прибор для показа трассы его цепи"
    )
    equipment = doc.GetElement(ref)

    circuits = [
        s for s in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalCircuit)
            .WhereElementIsNotElementType().ToElements()
        if s.BaseEquipment is not None and s.BaseEquipment.Id != equipment.Id
        and any(e.Id == equipment.Id for e in s.Elements)
    ]

    if not circuits:
        forms.alert(u"Выбранный прибор не является нагрузкой ни в одной цепи.", title=u"Показ трассы", exitscript=True)

    circuit = circuits[0]
    route_entity = get_route_entity(circuit)

    if route_entity is None:
        forms.alert(
            u"Данные маршрута не найдены.\n\nСначала проложите трассу командой «Проложить по трассе».",
            title=u"Показ трассы", exitscript=True
        )

    ids_to_isolate = collect_segment_ids(route_entity)
    ids_to_isolate.add(circuit.BaseEquipment.Id)
    ids_to_isolate.add(equipment.Id)

    if not ids_to_isolate:
        forms.alert(
            u"Маршрут не содержит элементов кабеленесущей системы.\n\n"
            u"Цепь проложена «по конструкциям» без КНС — нечего изолировать.",
            title=u"Показ трассы", exitscript=True
        )

    t = Transaction(doc, u"Показ трассы цепи")
    t.Start()
    try:
        id_list = List[ElementId](ids_to_isolate)
        doc.ActiveView.IsolateElementsTemporary(id_list)
    except Exception as ex:
        t.RollBack()
        forms.alert(u"Не удалось применить изоляцию в текущем виде:\n{}".format(ex), title=u"Показ трассы", exitscript=True)
    else:
        t.Commit()
        zoom_to_elements(ids_to_isolate)

except OperationCanceledException:
    pass
