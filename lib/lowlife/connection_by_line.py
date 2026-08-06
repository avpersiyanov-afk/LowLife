# -*- coding: utf-8 -*-
"""
Хелперы кнопки Tools/ConnectionByLine — подключение выделенных приборов
в последовательную цепь в порядке их расположения вдоль эскизной линии
(Detail или Model Curve).

Перенесено из C#-плагина CableSchedule (namespace СableSchedule,
класс ConnectionByLine) — единственная часть того плагина, оставленная
в LowLife: остальное (смена категории семейства, авто-трассировка по
Дейкстре, экспорт CSV-журнала) дублирует или не подходит под уже
принятые в проекте подходы (адресация узлов, свой расчёт длин).
"""

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter
from Autodesk.Revit.UI.Selection import ISelectionFilter


def _has_electrical_connector(elem):
    try:
        mep_model = getattr(elem, "MEPModel", None)
        connector_mgr = mep_model.ConnectorManager if mep_model else None
        if connector_mgr is None:
            return False
        return any(int(c.Domain) == 2 for c in connector_mgr.Connectors)
    except:
        return False


class ElectricalConnectableSelectionFilter(ISelectionFilter):
    """
    Фильтр выбора нагрузок: любая категория (не ограничиваем
    «Электрооборудованием»), но только экземпляры семейств с электрическим
    коннектором — иначе их физически не получится включить в
    ElectricalSystem — и не из связанного файла.
    """

    def AllowElement(self, elem):
        try:
            if elem is None or elem.Document.IsLinked:
                return False
            return _has_electrical_connector(elem)
        except:
            return False

    def AllowReference(self, reference, position):
        return True


class ElectricalPanelSelectionFilter(ISelectionFilter):
    """
    Фильтр выбора щита/панели — именно то, что Revit допускает как базовое
    оборудование цепи в ElectricalSystem.SelectPanel: категория
    «Электрооборудование» (OST_ElectricalEquipment) с электрическим
    коннектором, не из связанного файла. В отличие от нагрузок, здесь
    категория намеренно фиксирована — Revit жёстко требует именно её.
    """

    def AllowElement(self, elem):
        try:
            if elem is None or elem.Document.IsLinked or elem.Category is None:
                return False
            if elem.Category.Id.IntegerValue != int(BuiltInCategory.OST_ElectricalEquipment):
                return False
            return _has_electrical_connector(elem)
        except:
            return False

    def AllowReference(self, reference, position):
        return True


def get_mark(elem):
    """BuiltInParameter.ALL_MODEL_MARK элемента, либо его имя, либо '?'."""
    if elem is None:
        return u"?"
    try:
        p = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except:
        pass
    try:
        return elem.Name or u"?"
    except:
        return u"?"
