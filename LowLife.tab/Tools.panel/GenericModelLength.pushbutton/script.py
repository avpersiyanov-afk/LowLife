# -*- coding: utf-8 -*-

__title__ = "Длина линий"
__doc__ = "Сумма длин выбранных обобщённых моделей по типам"
__author__ = "Pipers"

from pyrevit import revit, DB, forms

doc = revit.doc
selection = revit.get_selection()

generic_cat_id = DB.ElementId(DB.BuiltInCategory.OST_GenericModel)


def get_type_name(el):
    type_el = doc.GetElement(el.GetTypeId())
    if type_el:
        p = type_el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.HasValue:
            return p.AsString()
        return type_el.Name
    return "Без типа"


def get_length(el):
    loc = el.Location

    if isinstance(loc, DB.LocationCurve):
        return loc.Curve.Length

    p = el.LookupParameter("Длина") or el.LookupParameter("Length")
    if p and p.HasValue:
        return p.AsDouble()

    return 0.0


selected = list(selection.elements)

if not selected:
    forms.toast("Нет выбора", title="Длина линий")
else:
    totals = {}

    for el in selected:
        if not el.Category:
            continue

        if el.Category.Id.IntegerValue != generic_cat_id.IntegerValue:
            continue

        type_name = get_type_name(el)
        length = get_length(el)

        totals[type_name] = totals.get(type_name, 0.0) + length

    if not totals:
        forms.toast("Нет обобщённых моделей", title="Длина линий")
    else:
        total = sum(totals.values())

        result = " | ".join(
            ["{}: {:.2f} м".format(name, value * 0.3048)
             for name, value in sorted(totals.items())]
        )

        result += " | Итого: {:.2f} м".format(total * 0.3048)

        forms.alert(result, title="Длина по типам")
