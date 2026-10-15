# -*- coding: utf-8 -*-

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


__title__ = u"Повернуть\n3D вид"
__doc__ = (
    u"Поворачивает открытый 3D вид под ось: выберите ось сетки из списка "
    u"(оси модели и связей) или кликните на виде прямую линию, стену, лоток, "
    u"и вид развернётся вокруг вертикали вдоль или поперёк этой оси. "
    u"Включённая рамка 3D вида поворачивается так же — её стороны встают "
    u"параллельно оси."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.DB import Transaction
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import revit, forms, script

from lowlife import view_rotate

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

TITLE = u"Повернуть 3D вид"

reason = view_rotate.unsupported_reason(view)
if reason:
    forms.alert(reason, title=TITLE, exitscript=True)


def align(direction):
    t = Transaction(doc, TITLE)
    t.Start()
    try:
        view_rotate.align_view(view, direction)
        t.Commit()
    except Exception:
        t.RollBack()
        forms.alert(u"Не удалось повернуть вид.\n\n" + traceback.format_exc(),
                    title=TITLE, exitscript=True)
    uidoc.RefreshActiveView()


FROM_LIST = u"Ось сетки из списка (модель и связи)"
IN_MODEL = u"Кликнуть линию в модели (ось, стена, лоток, линия…)"
IN_LINK = u"Кликнуть линию в связанном файле"
mode = forms.CommandSwitchWindow.show(
    [FROM_LIST, IN_MODEL, IN_LINK], message=u"Под какую ось повернуть 3D вид?")
if not mode:
    script.exit()

if mode == FROM_LIST:
    axes = view_rotate.list_grid_axes(doc)
    if not axes:
        forms.alert(u"В модели и загруженных связях нет прямых осей сетки.",
                    title=TITLE, exitscript=True)
    by_label = dict(axes)
    picked = forms.SelectFromList.show(
        [label for label, _d in axes], title=TITLE,
        button_name=u"Повернуть", multiselect=False)
    if not picked:
        script.exit()
    direction = by_label[picked]
else:
    # Один выбор — и сразу поворот: выбор после поворота (и Esc в нём)
    # возвращал виду прежнюю ориентацию.
    linked = mode == IN_LINK
    try:
        ref = uidoc.Selection.PickObject(
            ObjectType.LinkedElement if linked else ObjectType.Element,
            view_rotate.make_pick_filter(doc, linked),
            u"Повернуть 3D вид: выберите прямую линию (Esc — отмена)")
    except OperationCanceledException:
        script.exit()
    try:
        direction, _name = view_rotate.picked_direction(doc, ref)
    except ValueError as err:
        forms.alert(unicode(err), title=TITLE, exitscript=True)

align(direction)
