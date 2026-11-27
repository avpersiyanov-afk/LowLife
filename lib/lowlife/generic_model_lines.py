# -*- coding: utf-8 -*-
"""Преобразование линейных обобщённых моделей в линии аннотаций."""

try:
    unicode
except NameError:
    unicode = str

from Autodesk.Revit import DB


def _is_generic_model(element):
    try:
        return (element.Category is not None and
                element.Category.Id.IntegerValue ==
                int(DB.BuiltInCategory.OST_GenericModel))
    except Exception:
        return False


def convert_to_detail_lines(doc, view, elements):
    """Создаёт DetailCurve для линейных Generic Model и удаляет исходные."""
    result = {"converted": 0, "skipped": 0, "errors": []}
    to_delete = []
    for element in elements:
        if not _is_generic_model(element):
            result["skipped"] += 1
            continue
        try:
            curve = element.GeometryCurve
        except Exception:
            curve = None
        if curve is None:
            result["skipped"] += 1
            continue
        try:
            detail = doc.Create.NewDetailCurve(view, curve)
            try:
                style = element.LineStyle
                if style is not None:
                    detail.LineStyle = style
            except Exception:
                pass
            to_delete.append(element.Id)
            result["converted"] += 1
        except Exception as error:
            result["skipped"] += 1
            result["errors"].append(unicode(error))
    if to_delete:
        doc.Delete(to_delete)
    return result
