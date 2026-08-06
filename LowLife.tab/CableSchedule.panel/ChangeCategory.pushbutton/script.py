# -*- coding: utf-8 -*-

__title__ = "Замена\nкатегории"
__doc__ = "Меняет категорию выбранных элементов на электрооборудование, для дальнейшего подключения в цепь."
__author__ = "Pipers"

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Category, ElementId, FamilyInstance,
    FamilySource, IFamilyLoadOptions, Transaction
)
from Autodesk.Revit.DB.Electrical import MEPSystemClassification, ConnectorElement
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType

from pyrevit import revit, forms

import System

doc = revit.doc
uidoc = revit.uidoc

# BuiltInParameter без официального публичного имени в API этой версии
# Revit (используется тем же raw-значением, что и в оригинальном
# C#-плагине) — параметр "группа параметров" семейства, отвечающий
# за переклассификацию при смене категории.
_FAMILY_CATEGORY_PARAM_GROUP = System.Enum.ToObject(BuiltInParameter, -1114206)


class _FamilyLoadOptions(IFamilyLoadOptions):
    def OnFamilyFound(self, familyInUse):
        return True, False

    def OnSharedFamilyFound(self, sharedFamily, familyInUse):
        return True, FamilySource.Family, False


def set_family_category(family):
    fam_doc = doc.EditFamily(family)
    if fam_doc is None:
        forms.alert(u"Не удалось открыть документ семейства для редактирования.")
        return False

    owner_family = fam_doc.OwnerFamily
    category_type = owner_family.FamilyCategory.CategoryType

    if not any(cat.CategoryType == category_type for cat in fam_doc.Settings.Categories):
        forms.alert(u"Нет доступных категорий для изменения.")
        fam_doc.Close(False)
        return False

    category_param = owner_family.get_Parameter(_FAMILY_CATEGORY_PARAM_GROUP)
    if category_param is not None:
        try:
            category_param.Set(17)
        except:
            pass

    category = Category.GetCategory(fam_doc, ElementId(BuiltInCategory.OST_ElectricalEquipment))
    if category is None:
        forms.alert(u"Новая категория не найдена в документе семейства.")
        fam_doc.Close(False)
        return False

    t = Transaction(fam_doc, u"Изменить категорию и классификацию коннекторов")
    t.Start()
    try:
        owner_family.FamilyCategory = category

        connectors = FilteredElementCollector(fam_doc).OfClass(ConnectorElement).ToElements()
        for connector in connectors:
            try:
                if int(connector.Domain) == 2:  # DomainElectrical
                    connector.SystemClassification = MEPSystemClassification.PowerCircuit
            except Exception as ex:
                forms.alert(u"Ошибка при установке классификации на элемент {}: {}".format(
                    connector.Id, ex
                ))
        t.Commit()
    except:
        t.RollBack()
        raise

    fam_doc.LoadFamily(doc, _FamilyLoadOptions())
    fam_doc.Close(False)
    return True


try:
    refs = uidoc.Selection.PickObjects(ObjectType.Element, "Выберите экземпляры семейств для изменения категории")
except OperationCanceledException:
    refs = []

if refs:
    families = []
    for ref in refs:
        elem = doc.GetElement(ref.ElementId)
        if not isinstance(elem, FamilyInstance):
            forms.alert(u"Один из выбранных элементов не является экземпляром семейства.")
            continue

        symbol = elem.Symbol
        family = symbol.Family if symbol else None
        if family is None:
            forms.alert(u"Не удалось получить семейство из выбранного элемента.")
        else:
            families.append(family)

    unique_families = []
    seen_ids = set()
    for f in families:
        if f.Id not in seen_ids:
            seen_ids.add(f.Id)
            unique_families.append(f)

    if not unique_families:
        forms.alert(u"Не выбрано ни одного корректного семейства.", exitscript=True)

    for family in unique_families:
        set_family_category(family)

    forms.alert(u"Плагин отработал", title=u"Изменение категорий")
