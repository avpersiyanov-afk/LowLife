# -*- coding: utf-8 -*-
__title__ = "Диагностика\nконнекторов"
__doc__ = (
    "Тестовая кнопка: выберите панель, затем несколько устройств шлейфа. "
    "Показывает категорию и электрические коннекторы каждого элемента "
    "(Domain, ConnectorType) — помогает понять, почему ElectricalSystem.Create "
    "отказывается создавать цепь заданного типа: как правило, среди "
    "переданных элементов должен быть хотя бы один категории "
    "«Электрооборудование» (OST_ElectricalEquipment) — обычные устройства "
    "(датчики и т.п.) сами по себе цепь создать не могут, только быть "
    "нагрузкой в ней."
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

    try:
        cat_name = el.Category.Name if el.Category else u"?"
        is_equipment = bool(el.Category and el.Category.Id == ElementId(BuiltInCategory.OST_ElectricalEquipment))
        output.print_md(
            u"Категория: **{}**{}".format(
                cat_name,
                u" — «Электрооборудование», может быть источником цепи" if is_equipment else u""
            )
        )
    except Exception as ex:
        output.print_md(u"Не удалось получить категорию: {}".format(ex))

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
            sys_type = c.MEPSystem.SystemType if c.MEPSystem else None
        except Exception as ex:
            sys_type = u"(ошибка: {})".format(ex)

        # ElectricalSystemType самого коннектора (для Domain=DomainElectrical) —
        # под какой(ие) тип(ы) системы он сконфигурирован в семействе
        # (Data/Power/Telephone/Communication и т.п.), а не то, к какой
        # системе он ФАКТИЧЕСКИ подключён сейчас (это MEPSystem.SystemType
        # выше — None, пока цепь не создана). ElectricalSystem.Create(...,
        # type) требует среди элементов хотя бы один коннектор,
        # сконфигурированный под именно ЭТОТ system type — несовпадение
        # даёт ту же ошибку electComponents, что и отсутствие коннектора
        # вообще.
        try:
            electrical_system_type = c.ElectricalSystemType
        except Exception as ex:
            electrical_system_type = u"(нет/ошибка: {})".format(ex)

        output.print_md(
            u"- Коннектор {}: Domain=`{}`, ConnectorType=`{}`, "
            u"ElectricalSystemType=`{}`, MEPSystem.SystemType=`{}`".format(
                i, domain, conn_type, electrical_system_type, sys_type
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
    real_values = [
        a for a in dir(ElectricalSystemType)
        if not a.startswith("_") and isinstance(getattr(ElectricalSystemType, a, None), ElectricalSystemType)
    ]
    output.print_md(u", ".join(sorted(real_values)))

except OperationCanceledException:
    pass
