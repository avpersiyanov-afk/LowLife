# -*- coding: utf-8 -*-
__title__ = "Длина линий"
__doc__ = "Считает суммарную длину выбранных обобщённых моделей"
__author__ = "Pipers"
__persistentengine__ = True

from pyrevit import revit, DB
from Autodesk.Revit.UI import TaskDialog

doc = revit.doc
selection = revit.get_selection()

if not selection:
    TaskDialog.Show("Нет выбора", "Сначала выберите обобщённые модели на виде!")
else:
    generic_cat_id = DB.ElementId(DB.BuiltInCategory.OST_GenericModel)
    generic_models = [el for el in selection 
                       if el.Category and el.Category.Id == generic_cat_id]

    if not generic_models:
        TaskDialog.Show("Ошибка", "Среди выбранных элементов нет обобщённых моделей!")
    else:
        total_length_ft = 0.0
        count_with_length = 0

        for el in generic_models:
            length_ft = None
            location = el.Location
            if isinstance(location, DB.LocationCurve):
                length_ft = location.Curve.Length
            else:
                param = el.LookupParameter("Длина") or el.LookupParameter("Length")
                if param and param.HasValue:
                    length_ft = param.AsDouble()

            if length_ft:
                total_length_ft += length_ft
                count_with_length += 1

        total_length_m = total_length_ft * 0.3048

        message = "Выбрано элементов: {}\n".format(len(generic_models))
        message += "С определённой длиной: {}\n".format(count_with_length)
        message += "Общая длина: {:.2f} м".format(total_length_m)

        TaskDialog.Show("Длина обобщённых моделей", message)
