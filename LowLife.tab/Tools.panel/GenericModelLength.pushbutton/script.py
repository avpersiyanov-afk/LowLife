# -*- coding: utf-8 -*-

__title__ = "Длина линий"
__doc__ = "Считает суммарную длину выбранных обобщённых моделей отдельно по типам"
__author__ = "Pipers"
__persistentengine__ = True

from pyrevit import revit, DB, forms, script

doc = revit.doc
output = script.get_output()


def get_type_element(el):
    """Возвращает тип элемента."""
    type_id = el.GetTypeId()
    if type_id and type_id != DB.ElementId.InvalidElementId:
        return doc.GetElement(type_id)
    return None


def get_type_name(el):
    """Возвращает имя типа элемента."""
    type_el = get_type_element(el)

    if type_el:
        # Надёжный способ получить имя типа
        name_param = type_el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if name_param and name_param.HasValue:
            return name_param.AsString()

        # Запасной вариант
        try:
            return type_el.Name
        except:
            return "Тип ID {}".format(type_el.Id.IntegerValue)

    return "Без типа"


def get_family_name(el):
    """Возвращает имя семейства, если возможно."""
    type_el = get_type_element(el)

    if type_el:
        family_param = type_el.get_Parameter(DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
        if family_param and family_param.HasValue:
            return family_param.AsString()

    return "Без семейства"


def get_double_param_value(el, param_names):
    """
    Ищет числовой параметр сначала у экземпляра, потом у типа.
    Значение Revit возвращает во внутренних единицах — футах.
    """
    # Параметры экземпляра
    for name in param_names:
        param = el.LookupParameter(name)
        if param and param.HasValue and param.StorageType == DB.StorageType.Double:
            return param.AsDouble()

    # Параметры типа
    type_el = get_type_element(el)
    if type_el:
        for name in param_names:
            param = type_el.LookupParameter(name)
            if param and param.HasValue and param.StorageType == DB.StorageType.Double:
                return param.AsDouble()

    return None


def get_element_length_ft(el):
    """
    Получает длину элемента в футах.
    Сначала пробует LocationCurve, потом параметры длины.
    """
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

    return length_ft


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
        # Данные по типам
        # ключ: имя семейства + имя типа
        # значение: статистика
        type_data = {}

        skipped = []

        for el in generic_models:
            length_ft = get_element_length_ft(el)

            family_name = get_family_name(el)
            type_name = get_type_name(el)

            key = "{} : {}".format(family_name, type_name)

            if key not in type_data:
                type_data[key] = {
                    "family_name": family_name,
                    "type_name": type_name,
                    "count": 0,
                    "count_with_length": 0,
                    "total_length_ft": 0.0
                }

            type_data[key]["count"] += 1

            if length_ft is not None:
                type_data[key]["count_with_length"] += 1
                type_data[key]["total_length_ft"] += length_ft
            else:
                skipped.append(el.Id.IntegerValue)

        # Формируем текст для окна
        lines = []
        lines.append("Выбрано обобщённых моделей: {}".format(len(generic_models)))
        lines.append("Типов найдено: {}".format(len(type_data)))
        lines.append("")

        grand_total_ft = 0.0

        for key in sorted(type_data.keys()):
            data = type_data[key]

            total_m = data["total_length_ft"] * 0.3048
            grand_total_ft += data["total_length_ft"]

            lines.append("{} | Кол-во: {} | С длиной: {} | Сумма: {:.2f} м".format(
                key,
                data["count"],
                data["count_with_length"],
                total_m
            ))

        lines.append("")
        lines.append("Итого по всем типам: {:.2f} м".format(grand_total_ft * 0.3048))

        if skipped:
            lines.append("")
            lines.append("Без найденной длины: {}".format(len(skipped)))

        message = "\n".join(lines)

        forms.alert(message, title="Результат по типам")

        # Дублируем красиво в pyRevit Output
        output.print_md("## Длина обобщённых моделей по типам")
        output.print_md("Выбрано обобщённых моделей: **{}**".format(len(generic_models)))
        output.print_md("Типов найдено: **{}**".format(len(type_data)))
        output.print_md("")

        output.print_md("| Семейство | Тип | Кол-во | С длиной | Сумма, м |")
        output.print_md("|---|---|---:|---:|---:|")

        for key in sorted(type_data.keys()):
            data = type_data[key]
            total_m = data["total_length_ft"] * 0.3048

            output.print_md("| {} | {} | {} | {} | {:.2f} |".format(
                data["family_name"],
                data["type_name"],
                data["count"],
                data["count_with_length"],
                total_m
            ))

        output.print_md("")
        output.print_md("### Итого по всем типам: **{:.2f} м**".format(grand_total_ft * 0.3048))

        if skipped:
            output.print_md("")
            output.print_md("### Элементы без найденной длины")
            for elid in skipped:
                output.print_md("- ID: `{}`".format(elid))
