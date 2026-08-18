# -*- coding: utf-8 -*-
"""Cable tray placement — shared by every "Лоток ..." button on the
Tray*.panel panels: resolve a CableTrayType by a substring in its name,
resolve a Workset by a substring in its name, switch the active workset,
then start Revit's own interactive cable tray sketch tool for that type.

Cable tray is a system family (Autodesk.Revit.DB.Electrical.CableTray),
not a loadable FamilySymbol — types are listed via
FilteredElementCollector(doc).OfClass(CableTrayType), not through
Family.GetFamilySymbolIds() (that path is for loadable families, see
scs_settings.list_generic_model_symbols).

UIDocument.PostRequestForElementTypePlacement(element_type) is the Revit
API's own way to start the correct in-canvas placement tool for a given
ElementType from an external command — it is what lets a button "call the
create cable tray command with this type already selected" without
simulating clicks in the Type Selector.
"""

from Autodesk.Revit.DB import Element, FilteredElementCollector, FilteredWorksetCollector, WorksetKind
from Autodesk.Revit.DB.Electrical import CableTrayType
from pyrevit import forms

DEFAULT_WORKSET_FILTER = u"КНК"


def _safe_type_name(el):
    # Element.Name.GetValue(el) avoids the ambiguous-binding error some
    # element types throw on plain el.Name under IronPython (see
    # scs_settings._safe_element_name).
    try:
        return Element.Name.GetValue(el)
    except:
        try:
            return el.Name
        except:
            return u""


def find_cable_tray_types(doc, name_filter):
    """CableTrayType elements whose name contains name_filter."""
    return [
        t for t in FilteredElementCollector(doc).OfClass(CableTrayType).ToElements()
        if name_filter in _safe_type_name(t)
    ]


def find_worksets(doc, name_filter):
    """User-created Workset objects whose name contains name_filter."""
    return [
        w for w in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
        if name_filter in w.Name
    ]


def set_active_workset(doc, workset):
    doc.GetWorksetTable().SetActiveWorksetId(workset.Id)


def run_create_cable_tray_button(doc, uidoc, tray_type_filter, workset_filter=DEFAULT_WORKSET_FILTER):
    """Full flow for a "Лоток ..." button: resolve the CableTrayType and
    Workset by name filter, switch the active workset to it, and start the
    native cable tray placement tool for that type. Alerts and stops the
    script (exitscript) if the type or workset can't be resolved to exactly
    one match.
    """
    if not doc.IsWorkshared:
        forms.alert(
            u"В проекте не включена совместная работа — рабочие наборы недоступны.",
            exitscript=True
        )

    tray_types = find_cable_tray_types(doc, tray_type_filter)
    if not tray_types:
        forms.alert(
            u"Не найден тип лотка, содержащий «{}» в имени.".format(tray_type_filter),
            exitscript=True
        )
    if len(tray_types) > 1:
        forms.alert(
            u"Найдено несколько типов лотка с «{}» в имени ({} шт.) — "
            u"уточните имена типов в проекте, чтобы подстрока совпадала "
            u"ровно с одним.".format(tray_type_filter, len(tray_types)),
            exitscript=True
        )
    tray_type = tray_types[0]

    worksets = find_worksets(doc, workset_filter)
    if not worksets:
        forms.alert(
            u"Не найден рабочий набор, содержащий «{}» в имени.".format(workset_filter),
            exitscript=True
        )
    if len(worksets) > 1:
        forms.alert(
            u"Найдено несколько рабочих наборов с «{}» в имени ({} шт.) — "
            u"уточните имена рабочих наборов в проекте.".format(workset_filter, len(worksets)),
            exitscript=True
        )
    workset = worksets[0]

    set_active_workset(doc, workset)

    if not hasattr(uidoc, "PostRequestForElementTypePlacement"):
        forms.alert(
            u"Эта версия Revit не поддерживает запуск инструмента вставки типа "
            u"из API (UIDocument.PostRequestForElementTypePlacement).\n\n"
            u"Активный рабочий набор уже переключён на «{}» — запустите "
            u"инструмент «Лоток» вручную и выберите тип «{}».".format(
                workset.Name, _safe_type_name(tray_type)
            ),
            exitscript=True
        )

    uidoc.PostRequestForElementTypePlacement(tray_type)
