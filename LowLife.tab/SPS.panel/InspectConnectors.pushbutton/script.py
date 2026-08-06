# -*- coding: utf-8 -*-
__title__ = "Диагностика\nконнекторов"
__doc__ = (
    "Тестовая кнопка: выберите панель, затем несколько устройств шлейфа. "
    "Показывает электрические коннекторы каждого элемента (Domain, "
    "SystemClassification, ConnectorType) — помогает понять, почему "
    "ElectricalSystem.Create отказывается создавать цепь заданного типа."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Electrical import ElectricalSystemType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, script as pyrevit_script

doc = revit.doc
uidoc = revit.uidoc
output = pyrevit_script.get_output()


def describe_element(el, label):
    output.print_md(u"### {} — ID {}".format(label, el.Id.IntegerValue))

    try:
        type_el = doc.GetElement(el.GetTypeId())
        fam_name = type_el.Family.Name if type_el and type_el.Family else u"?"
        type_name = Element.Name.GetValue(type_el) if type_el else u"?"
        output.print_md(u"Семейство: **{}** / Типоразмер: **{}**".format(fam_name, type_name))
    except Exception as ex:
        output.print_md(u"Не удалось получить семейство/тип: {}".format(ex))

    mep_model = getattr(el, "MEPModel", None)
    connector_mgr = mep_model.ConnectorManager if mep_model else None

    if connector_mgr is None:
        output.print_md(u"**MEPModel/ConnectorManager отсутствует — у элемента нет коннекторов вообще.**")
        return

    connectors = list(connector_mgr.Connectors)
    if not connectors:
        output.print_md(u"ConnectorManager есть, но коннекторов 0.")
        return

    output.print_md(u"Коннекторов: {}".format(len(connectors)))

    for i, c in enumerate(connectors):
        try:
            domain = c.Domain
        except:
            domain = u"?"
        try:
            conn_type = c.ConnectorType
        except:
            conn_type = u"?"
        try:
            sys_class = c.MEPSystem.SystemType if c.MEPSystem else None
        except Exception as ex:
            sys_class = u"(ошибка: {})".format(ex)

        try:
            sys_classification = c.SystemClassification
        except Exception as ex:
            sys_classification = u"(ошибка: {})".format(ex)

        output.print_md(
            u"- Коннектор {}: Domain=`{}`, ConnectorType=`{}`, SystemClassification=`{}`, MEPSystem.SystemType=`{}`".format(
                i, domain, conn_type, sys_classification, sys_class
            )
        )


class NotLinkedSelectionFilter(ISelectionFilter):
    """Отсекает элементы связанных файлов — PickObject/PickObjects иначе даёт их выбрать."""

    def AllowElement(self, elem):
        try:
            return not elem.Document.IsLinked
        except:
            return True

    def AllowReference(self, reference, position):
        return True


try:
    not_linked = NotLinkedSelectionFilter()

    panel_ref = uidoc.Selection.PickObject(ObjectType.Element, not_linked, u"Выберите панель (в текущем документе, не в связанном файле)")
    panel_el = doc.GetElement(panel_ref)

    device_refs = uidoc.Selection.PickObjects(ObjectType.Element, not_linked, u"Выберите устройства шлейфа (подтвердите Enter)")
    device_els = [doc.GetElement(r) for r in device_refs]

    describe_element(panel_el, u"Панель")

    for d in device_els:
        describe_element(d, u"Устройство")

    output.print_md(u"---")
    output.print_md(u"### Доступные ElectricalSystemType в этой версии Revit")
    output.print_md(u", ".join(sorted(a for a in dir(ElectricalSystemType) if not a.startswith("_"))))

except OperationCanceledException:
    pass
