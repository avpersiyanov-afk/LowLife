# -*- coding: utf-8 -*-

__title__ = "Соединение\nпо линии"
__doc__ = "Подключает выбранные элементы (любой категории, с электрическим коннектором) в последовательную цепь в порядке их расположения вдоль выбранной линии."
__author__ = "Pipers"

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    BuiltInParameter, DetailCurve, ModelCurve, CurveElement, Transaction, XYZ, ElementId
)
from Autodesk.Revit.DB.Electrical import ElectricalSetting, ElectricalSystem, ElectricalSystemType
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType

from pyrevit import revit, forms

import System
from System.Collections.Generic import List

from lowlife.connection_by_line import (
    ElectricalConnectableSelectionFilter, ElectricalPanelSelectionFilter, get_mark
)

doc = revit.doc
uidoc = revit.uidoc

# BuiltInParameter без официального публичного имени в API этой версии
# Revit — параметр "Имя нагрузки" электрической цепи.
_CIRCUIT_LOAD_NAME_PARAM = System.Enum.ToObject(BuiltInParameter, -1140089)


class CurveElementSelectionFilter(ISelectionFilter):
    def AllowElement(self, elem):
        return isinstance(elem, DetailCurve) or isinstance(elem, ModelCurve)

    def AllowReference(self, reference, position):
        return True


def segment_intersects_bbox(p, q, bbox):
    x_min, x_max = min(bbox.Min.X, bbox.Max.X), max(bbox.Min.X, bbox.Max.X)
    y_min, y_max = min(bbox.Min.Y, bbox.Max.Y), max(bbox.Min.Y, bbox.Max.Y)

    t0, t1 = 0.0, 1.0
    dx = q.X - p.X

    if abs(dx) < 1e-9:
        if p.X < x_min or p.X > x_max:
            return False
    else:
        tx1, tx2 = (x_min - p.X) / dx, (x_max - p.X) / dx
        if tx1 > tx2:
            tx1, tx2 = tx2, tx1
        t0, t1 = max(t0, tx1), min(t1, tx2)
        if t0 > t1:
            return False

    dy = q.Y - p.Y
    if abs(dy) < 1e-9:
        if p.Y < y_min or p.Y > y_max:
            return False
    else:
        ty1, ty2 = (y_min - p.Y) / dy, (y_max - p.Y) / dy
        if ty1 > ty2:
            ty1, ty2 = ty2, ty1
        t0, t1 = max(t0, ty1), min(t1, ty2)
        if t0 > t1:
            return False

    return True


def ask_height_mm(current_mm):
    def validate(s):
        try:
            int(s)
            return True
        except:
            return False

    value = forms.ask_for_string(
        default=str(current_mm),
        prompt=u"Высота прокладки, мм:",
        title=u"Высота прокладки"
    )
    if value is None:
        return None
    if not validate(value):
        forms.alert(u"Введите целое число.", exitscript=True)
    return int(value)


try:
    electrical_settings = ElectricalSetting.GetElectricalSettings(doc)
    current_height_mm = int(round(electrical_settings.CircuitPathOffset * 304.8))

    height_mm = ask_height_mm(current_height_mm)
    if height_mm is None:
        forms.alert(u"Отменено.", exitscript=True)

    panel_ref = uidoc.Selection.PickObject(
        ObjectType.Element, ElectricalPanelSelectionFilter(),
        u"Выберите щит/панель (категория «Электрооборудование»)"
    )
    panel = doc.GetElement(panel_ref)

    curve_filter = CurveElementSelectionFilter()
    ref = uidoc.Selection.PickObject(ObjectType.Element, curve_filter, u"Выберите линию (Detail или Model)")
    curve_elem = doc.GetElement(ref)

    if not isinstance(curve_elem, CurveElement):
        forms.alert(u"Выбранный элемент не является линией.", exitscript=True)

    end0_connected = len(curve_elem.GetAdjoinedCurveElements(0)) > 0
    end1_connected = len(curve_elem.GetAdjoinedCurveElements(1)) > 0

    if end0_connected and end1_connected:
        forms.alert(
            u"Оба конца выбранного отрезка подключены к другим отрезкам.\n\n"
            u"Выберите первый отрезок цепи — тот у которого один конец свободен.",
            title=u"Неправильный отрезок", exitscript=True
        )

    if end0_connected and not end1_connected:
        with revit.Transaction(u"Переориентация начального отрезка"):
            reversed_curve = curve_elem.GeometryCurve.CreateReversed()
            if isinstance(curve_elem, DetailCurve):
                new_curve = doc.Create.NewDetailCurve(doc.ActiveView, reversed_curve)
            else:
                new_curve = doc.FamilyCreate.NewModelCurve(reversed_curve, curve_elem.SketchPlane)
            doc.Delete(curve_elem.Id)
            curve_elem = new_curve

    chain = [curve_elem]
    visited_ids = set([curve_elem.Id])
    current = curve_elem

    growing = True
    while growing:
        growing = False
        for i in (0, 1):
            for adj_id in current.GetAdjoinedCurveElements(i):
                if adj_id in visited_ids:
                    continue

                adj_elem = doc.GetElement(adj_id)
                if not isinstance(adj_elem, (DetailCurve, ModelCurve)):
                    continue

                for j in (0, 1):
                    if current.Id not in adj_elem.GetAdjoinedCurveElements(j):
                        continue

                    if i == j:
                        with revit.Transaction(u"Переориентация кривой"):
                            reversed_curve = adj_elem.GeometryCurve.CreateReversed()
                            if isinstance(adj_elem, DetailCurve):
                                new_curve = doc.Create.NewDetailCurve(doc.ActiveView, reversed_curve)
                            else:
                                new_curve = doc.FamilyCreate.NewModelCurve(reversed_curve, adj_elem.SketchPlane)
                            doc.Delete(adj_elem.Id)
                            adj_elem = new_curve

                    chain.append(adj_elem)
                    visited_ids.add(adj_elem.Id)
                    current = adj_elem
                    growing = True
                    break
                if growing:
                    break
            if growing:
                break

    forms.alert(u"Внимание! Выберите приборы для подключения, затем подтвердите выбор", title=u"Выбор элементов")
    equip_refs = uidoc.Selection.PickObjects(
        ObjectType.Element, ElectricalConnectableSelectionFilter(),
        u"Выберите элементы для подключения"
    )
    equip_ids = [r.ElementId for r in equip_refs]

    chain_segments = []
    running_len = 0.0
    for c in chain:
        chain_segments.append((c.GeometryCurve, running_len))
        running_len += c.GeometryCurve.Length

    ordered = []
    for eid in equip_ids:
        elem = doc.GetElement(eid)
        bbox = elem.get_BoundingBox(doc.ActiveView)
        if bbox is None:
            continue

        matched = False
        dist_along_chain = 0.0

        for curve, offset in chain_segments:
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
            if segment_intersects_bbox(p0, p1, bbox):
                center = (bbox.Min + bbox.Max) / 2.0
                probe = XYZ(center.X, center.Y, p0.Z)
                try:
                    proj = curve.Project(probe)
                    dist_along_chain = offset + p0.DistanceTo(proj.XYZPoint)
                except:
                    dist_along_chain = offset
                matched = True
                break

        if matched:
            ordered.append((elem.Id, dist_along_chain))

    ordered_ids = [eid for eid, _ in sorted(ordered, key=lambda t: t[1])]

    if not ordered_ids:
        forms.alert(u"Ни один из выбранных элементов не пересекает линию.", exitscript=True)

    with revit.Transaction(u"Подключение приборов по линии"):
        electrical_settings.CircuitPathOffset = height_mm / 304.8

        # Одна цепь: щит (BaseEquipment) + все устройства по порядку вдоль
        # линии — так же, как обычное выделение всех элементов шлейфа сразу
        # и "Create System" на ленте Revit. Топологию (кто к кому физически
        # подключён) Revit строит сам по геометрической близости коннекторов.
        element_ids = List[ElementId]([panel.Id] + ordered_ids)

        existing_systems = FilteredElementCollector(doc).OfClass(ElectricalSystem).ToElements()
        for s in existing_systems:
            base_eq = s.BaseEquipment
            if base_eq is not None and base_eq.Id == panel.Id:
                if any(e.Id in ordered_ids for e in s.Elements):
                    doc.Delete(s.Id)

        new_system = ElectricalSystem.Create(doc, element_ids, ElectricalSystemType.PowerCircuit)
        if new_system is None:
            forms.alert(u"Не удалось создать цепь.", exitscript=True)

        new_system.SelectPanel(panel)

        last_load = doc.GetElement(ordered_ids[-1])
        panel_mark = get_mark(panel) or u"Без_марки_панели"
        load_mark = get_mark(last_load) or u"Без_марки_нагрузки"
        load_name = panel_mark + u"/" + load_mark

        load_name_param = new_system.get_Parameter(_CIRCUIT_LOAD_NAME_PARAM)
        if load_name_param is not None and not load_name_param.IsReadOnly:
            load_name_param.Set(load_name)

    forms.alert(u"Плагин отработал", title=u"Подключение по линии")

except OperationCanceledException:
    pass
