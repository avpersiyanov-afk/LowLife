# -*- coding: utf-8 -*-
"""Преобразование линейных обобщённых моделей в линии аннотаций."""

try:
    unicode
except NameError:
    unicode = str

from Autodesk.Revit import DB

from lowlife.geometry import get_curve_data
from lowlife.i18n import tr
from lowlife.json_snapshot_common import safe_name, category_name


class LineStyleOption(object):
    """Searchable SelectFromList option for a Revit line style."""

    def __init__(self, style, name=None):
        self.style = style
        self.name = unicode(name if name is not None else safe_name(style) or u"")

    def __str__(self):
        return self.name


def list_line_style_options(doc, keep_source_label=None):
    """Return searchable projection line-style options from the current document."""
    options = []
    if keep_source_label:
        options.append(LineStyleOption(None, keep_source_label))
    try:
        lines = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
        for subcategory in lines.SubCategories:
            style = subcategory.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
            if style is not None:
                options.append(LineStyleOption(style))
    except Exception:
        return options
    return sorted(options, key=lambda option: option.name.lower())


def _is_generic_model(element):
    try:
        return (element.Category is not None and
                element.Category.Id.IntegerValue ==
                int(DB.BuiltInCategory.OST_GenericModel))
    except Exception:
        return False


def _element_label(element):
    try:
        element_id = element.Id.IntegerValue
    except Exception:
        element_id = u"?"
    try:
        category = unicode(category_name(element) or tr(u"без категории", u"no category"))
    except Exception:
        category = tr(u"категория неизвестна", u"unknown category")
    name = unicode(safe_name(element) or u"")
    try:
        type_element = element.Document.GetElement(element.GetTypeId())
        type_name = unicode(safe_name(type_element) or u"") if type_element else u""
    except Exception:
        type_name = u""
    parts = [u"ID {}".format(element_id), category]
    if name:
        parts.append(name)
    if type_name and type_name != name:
        parts.append(tr(u"тип: {}", u"type: {}").format(type_name))
    return u" | ".join(parts)


def _skip(result, element, reason):
    result["skipped"] += 1
    result["skipped_details"].append({
        "element": _element_label(element),
        "reason": reason,
    })


def _line_curve(element, view):
    """Return the placement curve, while rejecting the bounding-box fallback."""
    try:
        if not isinstance(element.Location, DB.LocationCurve):
            return None
    except Exception:
        return None
    curve, _p1, _p2 = get_curve_data(element, view)
    return curve


def convert_to_detail_lines(doc, view, elements, target_style=None):
    """Создаёт DetailCurve для линейных Generic Model и удаляет исходные."""
    result = {"converted": 0, "skipped": 0, "skipped_details": [], "errors": []}
    to_delete = []
    for element in elements:
        if not _is_generic_model(element):
            _skip(result, element, tr(
                u"категория элемента не «Обобщённые модели»",
                u"the element category is not Generic Models"))
            continue
        curve = _line_curve(element, view)
        if curve is None:
            _skip(result, element, tr(
                u"у элемента нет кривой размещения (это не линейное семейство)",
                u"the element has no placement curve (it is not line-based)"))
            continue
        try:
            detail = doc.Create.NewDetailCurve(view, curve)
            try:
                style = target_style if target_style is not None else element.LineStyle
                if style is not None:
                    detail.LineStyle = style
            except Exception:
                pass
            to_delete.append(element.Id)
            result["converted"] += 1
        except Exception as error:
            reason = tr(
                u"Revit не создал линию аннотаций: {}",
                u"Revit could not create the detail line: {}").format(unicode(error))
            _skip(result, element, reason)
            result["errors"].append(reason)
    if to_delete:
        # IronPython binds Document.Delete(ElementId) here and does not
        # convert a native Python list to the ICollection<ElementId> overload.
        for element_id in to_delete:
            doc.Delete(element_id)
    return result
