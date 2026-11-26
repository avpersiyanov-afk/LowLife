# -*- coding: utf-8 -*-
"""Размещение линейных обобщённых моделей «Участок трассы»."""

from Autodesk.Revit import DB
from pyrevit import forms

from lowlife.i18n import tr
from lowlife.scs_settings import _safe_element_name, list_generic_model_symbols
from lowlife import route_lines_settings
from lowlife import cable_tray


FAMILY_FILTER = u"Участок трассы"


def _family_name(symbol):
    try:
        return _safe_element_name(symbol.Family) or u""
    except Exception:
        return u""


def find_route_line_symbols(doc, type_name, family_filter=FAMILY_FILTER):
    """Return generic-model symbols matching the route family and exact type."""
    family_filter = (family_filter or u"").strip()
    family_filter_lower = family_filter.lower()
    result = []
    for symbol in list_generic_model_symbols(doc, family_filter):
        if _family_name(symbol).lower().find(family_filter_lower) < 0:
            continue
        if (_safe_element_name(symbol) or u"") == type_name:
            result.append(symbol)
    return sorted(result, key=lambda symbol: (_family_name(symbol), symbol.Id.IntegerValue))


def _activate_symbol(doc, symbol):
    if getattr(symbol, "IsActive", True):
        return
    transaction = DB.Transaction(doc, tr(
        u"Активация типа линии трассы", u"Activate route-line type"
    ))
    transaction.Start()
    try:
        symbol.Activate()
        transaction.Commit()
    except Exception:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        raise


def _activate_workset(doc, workset_filter):
    if not getattr(doc, "IsWorkshared", False):
        forms.alert(
            tr(u"В проекте не включена совместная работа, поэтому рабочий набор выбрать нельзя.",
               u"Worksharing is disabled, so a workset cannot be selected."),
            exitscript=True,
        )
    worksets = cable_tray.find_worksets(doc, workset_filter)
    if not worksets:
        forms.alert(
            tr(u"Не найден рабочий набор, содержащий «{}» в имени.",
               u"No workset containing «{}» in its name was found.").format(workset_filter),
            exitscript=True,
        )
    if len(worksets) > 1:
        forms.alert(
            tr(u"Фильтр «{}» подходит сразу к нескольким рабочим наборам ({}). Уточните его в настройках.",
               u"The filter «{}» matches multiple worksets ({}). Refine it in settings.").format(
                   workset_filter, len(worksets)),
            exitscript=True,
        )
    cable_tray.set_active_workset(doc, worksets[0])


def _ensure_work_plane(doc, view):
    if getattr(view, "SketchPlane", None) is not None:
        return
    try:
        normal, origin = view.ViewDirection, view.Origin
    except Exception:
        normal, origin = DB.XYZ.BasisZ, DB.XYZ.Zero
    transaction = DB.Transaction(doc, tr(
        u"Задать рабочую плоскость линий трассы", u"Set route-line work plane"
    ))
    transaction.Start()
    try:
        view.SketchPlane = DB.SketchPlane.Create(
            doc, DB.Plane.CreateByNormalAndOrigin(normal, origin)
        )
        transaction.Commit()
    except Exception:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        raise


def run_route_line_button(doc, uidoc, panel_key, role_key):
    """Find and start Revit's interactive placement tool for one line type."""
    if doc is None or getattr(doc, "IsFamilyDocument", False):
        forms.alert(
            tr(u"Откройте проект Revit для размещения участка трассы.",
               u"Open a Revit project to place a route segment."),
            exitscript=True,
        )
    settings = route_lines_settings.get_settings_silent()
    _activate_workset(doc, settings[route_lines_settings.WORKSET_KEY])
    family_filter = settings[route_lines_settings.family_key(panel_key)]
    type_name = settings[route_lines_settings.type_key(panel_key, role_key)]

    symbols = find_route_line_symbols(doc, type_name, family_filter)
    if not symbols:
        forms.alert(
            tr(
                u"Не найден тип «{}» в семействе «{}».",
                u"Type «{}» was not found in family «{}».",
            ).format(type_name, family_filter),
            exitscript=True,
        )

    # Several discipline-specific families carry the same type names. Prefer
    # the family already used most often in the model, keeping all five
    # buttons on the same route-segment family.
    symbol = symbols[0]
    _activate_symbol(doc, symbol)

    _ensure_work_plane(doc, uidoc.ActiveView)
    if not hasattr(uidoc, "PostRequestForElementTypePlacement"):
        forms.alert(
            tr(
                u"Эта версия Revit не поддерживает запуск штатной вставки типа из API. "
                u"Выберите «{}» вручную в инструменте размещения обобщённой модели.",
                u"This Revit version cannot start standard type placement through the API. "
                u"Choose «{}» manually in the Generic Model placement tool.",
            ).format(type_name),
            exitscript=True,
        )
    uidoc.PostRequestForElementTypePlacement(symbol)
