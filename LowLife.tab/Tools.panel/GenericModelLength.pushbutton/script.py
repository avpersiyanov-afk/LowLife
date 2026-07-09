# -*- coding: utf-8 -*-
__title__ = "Длина\nобобщ. моделей"
__doc__ = "Считает суммарную длину выбранных обобщённых моделей"
__author__ = "Pipers"

from pyrevit import revit, DB, forms

doc = revit.doc
selection = revit.get_selection()

if not selection:
    forms.alert("Сначала выберите обобщённые модели на виде!", 
                title="Нет выбора")
else:
    generic_cat_id = DB.ElementId(DB.BuiltInCategory.OST_GenericModel)
    
    generic_models = [el for el in selection 
                       if el.Category and el.Category.Id == generic_cat_id]

    if not generic_models:
        forms.alert("Среди выбранных элементов нет обобщённых моделей!", 
                    title="Ошибка")
    else:
        total_length_ft = 0.0
        count_with_length = 0

        for el in generic_models:
            length_ft = None

            # Способ 1: если семейство построено на линии
            location = el.Location
            if isinstance(location, DB.LocationCurve):
                length_ft = location.Curve.Length
            else:
                # Способ 2: ищем параметр "Длина" или "Length"
                param = el.LookupParameter("Длина") or el.LookupParameter("Length")
                if param and param.HasValue:
                    length_ft = param.AsDouble()

            if length_ft:
                total_length_ft += length_ft
                count_with_length += 1

        total_length_m = total_length_ft * 0.3048

        message = "Обобщённые модели:\n\n"
        message += "Выбрано элементов: {}\n".format(len(generic_models))
        message += "С определённой длиной: {}\n".format(count_with_length)
        message += "Общая длина: {:.2f} м".format(total_length_m)

        forms.alert(message, title="Длина обобщённых моделей")
