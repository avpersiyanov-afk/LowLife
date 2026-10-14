# -*- coding: utf-8 -*-

__title__ = u"Повернуть\n3D вид"
__doc__ = (
    u"Поворачивает 3D вид вокруг оси на точный угол — в Revit 3D вид "
    u"вращается только мышью и видовым кубом. Выберите 3D вид (по умолчанию "
    u"— активный), ось поворота — X, Y или Z модели (проходят через центр "
    u"рамки 3D вида, без рамки — через центр вида) или ось сетки — и угол в "
    u"градусах. Модель в кадре поворачивается против часовой стрелки, если "
    u"смотреть с конца оси (минус — по часовой). Окно не закрывается после "
    u"поворота — вид можно доворачивать по шагам."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.DB import Transaction, View3D
from pyrevit import revit, forms

from lowlife import view_rotate, view_rotate_dialog

doc = revit.doc
uidoc = revit.uidoc

TITLE = u"Повернуть 3D вид"


def _zoom_to_fit(view):
    for uiview in uidoc.GetOpenUIViews():
        if uiview.ViewId == view.Id:
            uiview.ZoomToFit()
            return True
    return False


views = view_rotate.list_3d_views(doc)
if not views:
    forms.alert(u"В проекте нет 3D видов.", title=TITLE, exitscript=True)

active = doc.ActiveView
active_id = active.Id if isinstance(active, View3D) else None

# Неоткрытый вид нельзя вписать, пока окно открыто, — открываем его после.
pending = {"view": None}


def apply(view, axis, angle, grid, fit):
    reason = view_rotate.unsupported_reason(view)
    if reason:
        return reason
    t = Transaction(doc, TITLE)
    t.Start()
    try:
        view_rotate.rotate_view(view, axis, angle, grid)
        t.Commit()
    except Exception:
        t.RollBack()
        return u"Не удалось повернуть вид.\n\n" + traceback.format_exc()
    if view.Id == doc.ActiveView.Id:
        pending["view"] = None
        if fit:
            _zoom_to_fit(view)
        uidoc.RefreshActiveView()
    else:
        pending["view"] = view if fit else None
    return None


view_rotate_dialog.show(views, view_rotate.list_grids(doc), active_id, apply)

if pending["view"] is not None:
    try:
        uidoc.ActiveView = pending["view"]
        _zoom_to_fit(pending["view"])
    except Exception:
        pass
