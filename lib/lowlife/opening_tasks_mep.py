# -*- coding: utf-8 -*-
"""MEP adapter for the proven tray intersection/box geometry pipeline."""
from Autodesk.Revit.DB import (BuiltInCategory, ConnectorProfileType, InsulationLiningBase,
                                Line, LocationCurve)
from lowlife import tray_boxes as boxes
from lowlife.i18n import tr

CATEGORY_NAMES = ('OST_CableTray', 'OST_DuctCurves', 'OST_PipeCurves', 'OST_Conduit')


def supported(element):
    return (element is not None and element.Category is not None and
            boxes._id_int(element.Category.Id) in [int(getattr(BuiltInCategory, n)) for n in CATEGORY_NAMES])


class Route(object):
    """Rectangular envelope, with insulation. Unsupported shapes are explicit errors."""
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
            # tray_boxes assumes an unrolled rectangular cross-section.
            if abs(axis.Direction.Z) < 0.01 and abs(connector.CoordinateSystem.BasisX.Z) > 0.01:
                raise ValueError(tr(u'Повёрнутое сечение требует ручной проверки',u'Rolled cross-sections require manual review'))
        else:
            raise ValueError(tr(u'Форма соединителя не поддерживается',u'Unsupported connector shape'))
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
