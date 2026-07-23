# -*- coding: utf-8 -*-

__title__ = "Длина линий"
__doc__ = "Считает суммарную длину выбранных обобщённых моделей"
__author__ = "Pipers"
__persistentengine__ = True

from pyrevit import revit, DB, forms, script

doc = revit.doc
output = script.get_output()


def get_double_param_value(el, param_names):
    """
    Ищет параметр сначала у экземпляра, потом у типа.
    Возвращает значение в футах или None.
    """
    for name in param_names:
        param = el.LookupParameter(name)
        if param and param.HasValue and param.StorageType == DB.StorageType.Double:
            return param.AsDouble()

    type_id = el.GetTypeId()
    if type_id and type_id != DB.ElementId.InvalidElementId:
        type_el = doc.GetElement(type_id)
        if type_el:
            for name in param_names:
                param = type_el.LookupParameter(name)
                if param and param.HasValue and param.StorageType == DB.StorageType.Double:
                    return param.AsDouble()

    return None


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
        total_length_ft = 0.0
        count_with_length = 0
        skipped = []

        for el in generic_models:
            length_ft = None

            location = el.Location

            if isinstance(location, DB.LocationCurve):
                length_ft = location.Curve.Length
            else:
                length_ft = get_double_param_value(
                    el,
                    [
                        "Длина",
                        "Length",
                        "L",
                        "длина"
                    ]
                )

            if length_ft is not None:
                total_length_ft += length_ft
                count_with_length += 1
            else:
                skipped.append(el.Id.IntegerValue)

        total_length_m = total_length_ft * 0.3048

        message = (
            "Выбрано обобщённых моделей: {}\n"
            "Элементов с найденной длиной: {}\n"
            "Без параметра длины: {}\n\n"
            "Суммарная длина: {:.2f} м"
        ).format(
            len(generic_models),
            count_with_length,
            len(skipped),
            total_length_m
        )

        forms.alert(message, title="Результат")

        output.print_md("## Результат")
        output.print_md("Выбрано обобщённых моделей: **{}**".format(len(generic_models)))
        output.print_md("С длиной: **{}**".format(count_with_length))
        output.print_md("Без длины: **{}**".format(len(skipped)))
        output.print_md("Суммарная длина: **{:.2f} м**".format(total_length_m))

        if skipped:
            output.print_md("### Элементы без найденной длины")
            for elid in skipped:
                output.print_md("- ID: `{}`".format(elid))
