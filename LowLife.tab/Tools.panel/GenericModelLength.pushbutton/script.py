# -*- coding: utf-8 -*-

__title__ = "Длина линий"
__doc__ = "Считает суммарную длину выбранных обобщённых моделей отдельно по типам"
__author__ = "Pipers"
__persistentengine__ = True

from pyrevit import revit, DB, forms

doc = revit.doc


def get_type_element(el):
    type_id = el.GetTypeId()
    if type_id and type_id != DB.ElementId.InvalidElementId:
        return doc.GetElement(type_id)
    return None


def get_type_name(el):
    type_el = get_type_element(el)

    if type_el:
        name_param = type_el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if name_param and name_param.HasValue:
            return name_param.AsString()

        try:
            return type_el.Name
        except:
            return "Тип ID {}".format(type_el.Id.IntegerValue)

    return "Без типа"


def get_double_param_value(el, param_names):
    # Сначала параметр экземпляра
    for name in param_names:
        param = el.LookupParameter(name)
        if param and param.HasValue and param.StorageType == DB.StorageType.Double:
            return param.AsDouble()

    # Потом параметр типа
    type_el = get_type_element(el)
    if type_el:
        for name in param_names:
            param = type_el.LookupParameter(name)
            if param and param.HasValue and param.StorageType == DB.StorageType.Double:
                return param.AsDouble()

    return None


def get_element_length_ft(el):
    location = el.Location

    if isinstance(location, DB.LocationCurve):
        return location.Curve.Length

    return get_double_param_value(
        el,
        [
            "Длина",
            "Length",
            "L",
            "длина"
        ]
    )


selection = revit.get_selection()

try:
    selected_elements = list(selection.elements)
except:
    selected_elements = list(selection)

if not selected_elements:
    forms.alert(
        "Сначала выберите обобщённые модели на виде.",
        title="Нет выбора"
    )
else:
    generic_cat_id = DB.ElementId(DB.BuiltInCategory.OST_GenericModel)

    generic_models = []

    for el in selected_elements:
        if el.Category and el.Category.Id.IntegerValue == generic_cat_id.IntegerValue:
            generic_models.append(el)

    if not generic_models:
        forms.alert(
            "Среди выбранных элементов нет обобщённых моделей.",
            title="Ошибка"
        )
    else:
        type_totals = {}

        for el in generic_models:
            type_name = get_type_name(el)
            length_ft = get_element_length_ft(el)

            if type_name not in type_totals:
                type_totals[type_name] = 0.0

            if length_ft is not None:
                type_totals[type_name] += length_ft

        total_ft = sum(type_totals.values())

        lines = []

        for type_name in sorted(type_totals.keys()):
            length_m = type_totals[type_name] * 0.3048
            lines.append("{} - {:.2f} м".format(type_name, length_m))

        lines.append("")
        lines.append("Общая длина - {:.2f} м".format(total_ft * 0.3048))

        forms.alert("\n".join(lines), title="Результат")
