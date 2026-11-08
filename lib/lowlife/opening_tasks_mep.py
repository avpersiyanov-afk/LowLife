# -*- coding: utf-8 -*-
"""MEP adapter for the proven tray intersection/box geometry pipeline."""
from Autodesk.Revit.UI.Selection import ISelectionFilter
from Autodesk.Revit.DB import (BuiltInCategory, ConnectorProfileType, InsulationLiningBase,
                                Line, LocationCurve)
from lowlife import tray_boxes as boxes
from lowlife.i18n import tr

CATEGORY_NAMES = ('OST_CableTray', 'OST_DuctCurves', 'OST_PipeCurves', 'OST_Conduit')


def supported(element):
    return (element is not None and element.Category is not None and
            boxes._id_int(element.Category.Id) in [int(getattr(BuiltInCategory, n)) for n in CATEGORY_NAMES])


class Route(object):
    """Section size and connector frame, with insulation, for straight sweeps."""
    def __init__(self, element):
        self.element = element
        if not supported(element):
            raise ValueError(tr(u'Выберите лотки, воздуховоды, трубы или кабельные трубы',u'Select cable trays, ducts, pipes or conduits'))
        if not isinstance(element.Location, LocationCurve) or not isinstance(element.Location.Curve, Line):
            raise ValueError(tr(u'Поддерживаются только прямые участки ВИС',u'Only straight MEP routes are supported'))
        axis = element.Location.Curve
        connectors = [c for c in element.ConnectorManager.Connectors
                      if abs(c.CoordinateSystem.BasisZ.DotProduct(axis.Direction)) > 0.999]
        if not connectors:
            raise ValueError(tr(u'Не найден осевой соединитель',u'No axial connector'))
        connector = connectors[0]
        if connector.Shape == ConnectorProfileType.Round:
            self.Width = self.Height = 2.0 * connector.Radius
        elif connector.Shape in (ConnectorProfileType.Rectangular, ConnectorProfileType.Oval):
            self.Width, self.Height = connector.Width, connector.Height
        else:
            raise ValueError(tr(u'Форма соединителя не поддерживается',u'Unsupported connector shape'))
        basis=connector.CoordinateSystem.BasisX
        self.section_x=(basis.X,basis.Y,basis.Z)
        self.round_section=connector.Shape==ConnectorProfileType.Round
        insulation = 0.0
        insulated = boxes._id_int(element.Category.Id) in [int(BuiltInCategory.OST_DuctCurves), int(BuiltInCategory.OST_PipeCurves)]
        insulation_ids = InsulationLiningBase.GetInsulationIds(element.Document, element.Id) if insulated else []
        for eid in insulation_ids:
            item = element.Document.GetElement(eid)
            insulation = max(insulation, item.Thickness)
        self.Width += 2.0 * insulation
        self.Height += 2.0 * insulation
        if min(self.Width, self.Height) <= 0:
            raise ValueError(tr(u'Некорректный габарит сечения ВИС',u'Invalid MEP cross-section'))

    def __getattr__(self, name):
        return getattr(self.element, name)


class RouteSelectionFilter(ISelectionFilter):
    """Straight supported routes; inclined and rolled sections are geometric inputs."""
    def __init__(self, settings):
        self.settings=settings
        self.cache={}
    def AllowReference(self, reference, point):
        return False
    def AllowElement(self, element):
        if not supported(element):
            return False
        key=boxes._id_int(element.Id)
        if key not in self.cache:
            try:
                route=Route(element)
                z=abs(route.Location.Curve.Direction.Z)
                hosts=self.settings.get('box_hosts','walls_floors')
                self.cache[key]=((hosts in ('walls','walls_floors') and z<1.0-1e-10) or
                                 (hosts in ('floors','walls_floors') and z>1e-6))
            except Exception:
                self.cache[key]=False
        return self.cache[key]
